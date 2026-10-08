# backend/update_check.py
"""C端 版本自报与新版本检测（client-update-notify）。

- 版本与检测地址来自打包期 release.json 烘焙（pywebview_app.start_server 注入
  env：CLIENT_VERSION / CLIENT_UPDATE_URL / CLIENT_UPDATE_URL_FALLBACK）；
  本地开发无烘焙 → 版本 dev → 检测跳过，行为与历史一致。
- 外呼目标锁定静态托管 latest.json（www / 云托管直连域），禁止改走 S端 /api/*：
  云托管容器按需拉起即计费且冷启动 503，静态托管 COS 直出无容器成本。
- 出站校验（每个候选地址逐一适用）：仅 https + host 命中烘入可信域集合
  （主/兜底两域）+ DNS 解析结果拒绝非公网地址（环回/私网/保留）。
  主域失败自动切兜底；全部失败静默降级，绝不向用户呈现错误。
- 节流：data/update-check.json 记 last_check_at / cached / dismissed_version，
  真实外呼最多每小时一次（启动检测与会话内复查共用同一把尺）。
"""

import asyncio
import ipaddress
import json
import os
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from build_info import get_build_info
from config import DATA_ROOT
from http_client import build_async_client
from schema_version import app_version, is_newer, is_valid_version

router = APIRouter(tags=["update-check"])

# 与 CI Generate release.json 的默认值同源（仅 release.json 缺键时兜底；
# 真实安装包的值永远来自烘焙，换域名走仓库 Variables 零代码）
_DEFAULT_UPDATE_URL = "https://www.awesomenovel.com/download/latest.json"
_DEFAULT_UPDATE_URL_FALLBACK = (
    "https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/download/latest.json"
)

# 真实外呼的最小间隔（秒）：启动检测与会话内复查共用
_CHECK_INTERVAL = 3600
_FETCH_TIMEOUT = 6.0

_state_path = Path(DATA_ROOT) / "update-check.json"


def get_client_version() -> str:
    """本机版本：env（打包态由 release.json 注入）> dev。

    c-db-per-version：委托 `schema_version.app_version()`——库文件名与更新检测
    必须共用同一份版本口径（否则两处会各自漂）。
    """
    return app_version()


def _candidate_urls() -> list[str]:
    urls = []
    for name, default in (
        ("CLIENT_UPDATE_URL", _DEFAULT_UPDATE_URL),
        ("CLIENT_UPDATE_URL_FALLBACK", _DEFAULT_UPDATE_URL_FALLBACK),
    ):
        u = (os.environ.get(name) or "").strip() or default
        if u not in urls:
            urls.append(u)
    return urls


def _trusted_hosts() -> set[str]:
    hosts = set()
    for u in _candidate_urls():
        h = urlparse(u).hostname
        if h:
            hosts.add(h.lower())
    return hosts


async def _validate_outbound_url(url: str) -> bool:
    """仅 https + 可信域 + 解析结果全为公网地址；任一不满足即拒绝。

    DNS 解析走事件循环的 getaddrinfo（内部线程池）——本端点与整个 SPA 共享
    同一 uvicorn 事件循环，同步 socket.getaddrinfo 会在解析器挂起时把应用
    整体冻结到 DNS 超时，绝不可同步调用。
    """
    try:
        p = urlparse(url)
        if p.scheme != "https" or not p.hostname:
            return False
        host = p.hostname.lower()
        if host not in _trusted_hosts():
            return False
        # host 本身是 IP 字面量的情况：非公网直接拒
        try:
            literal = ipaddress.ip_address(host)
            if not literal.is_global:
                return False
        except ValueError:
            pass
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(p.hostname, 443, proto=socket.IPPROTO_TCP)
    except (OSError, ValueError):
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        # is_global=False 覆盖环回/私网/链路本地/保留地址
        if not ip.is_global:
            return False
    return True


def _has_newer(latest: str, current: str) -> bool:
    """版本比较委托单源（c-db-per-version）：逐段数值、右侧补零、**永不抛异常**。

    旧实现在非纯数字段（如 `0.11-beta`）抛 ValueError，调用点无保护 → 装带后缀
    版本的包点开更新检测即 500。现在非法/带后缀一律给出确定序。
    """
    return is_newer(latest, current)


def _load_state() -> dict:
    try:
        raw = json.loads(_state_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        _state_path.parent.mkdir(parents=True, exist_ok=True)
        _state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        # 状态文件写失败不影响主流程：下次检测重来一次而已
        pass


async def _fetch_one(url: str) -> dict | None:
    """抓取并解析单个 latest.json；任何失败返回 None（调用方负责切兜底）。"""
    try:
        async with build_async_client(timeout=_FETCH_TIMEOUT) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        latest = str(data.get("version") or "").strip()
        if not is_valid_version(latest):
            return None  # 格式非法按本次失败处理（载荷校验边界）
        notes = data.get("notes")
        return {
            "latest": latest,
            "notes": notes.strip() if isinstance(notes, str) else "",
        }
    except (httpx.HTTPError, ValueError):
        return None


async def _fetch_latest() -> dict | None:
    """主域 → 兜底逐个尝试（每个地址先过出站校验）；全部失败返回 None。

    结果带 source_url = 实际成功的地址：下游推导说明页/官网入口用它，
    主域坏配置（校验不过、靠兜底成功）时不连坐。
    """
    for url in _candidate_urls():
        if not await _validate_outbound_url(url):
            continue
        got = await _fetch_one(url)
        if got is not None:
            got["source_url"] = url
            return got
    return None


def _derived_urls(source_url: str, latest: str) -> tuple[str, str]:
    """由实际成功的检测地址推导：更新说明页（版本化目录）与官网下载入口。"""
    base = source_url.removesuffix("latest.json")
    p = urlparse(source_url)
    return f"{base}v{latest}/notes.html", f"{p.scheme}://{p.netloc}"


async def get_update_state() -> dict:
    """检测入口：dev 跳过；节流内吃缓存；真实外呼每小时至多一次。"""
    current = get_client_version()
    if current == "dev":
        return _payload(current=current, latest=None)

    state = _load_state()
    cached = state.get("cached") if isinstance(state.get("cached"), dict) else None
    now = time.time()
    last = float(state.get("last_check_at") or 0)

    # 节流只看 last_check_at（成败都记时）：失败后 cached 为空也占节流窗，
    # 弱网下 15 分钟轮询不会连打外呼
    if (now - last) >= _CHECK_INTERVAL:
        fetched = await _fetch_latest()
        if fetched is not None:
            cached = fetched
        state["last_check_at"] = now
        state["cached"] = cached or {}
        _save_state(state)

    if not cached or not cached.get("latest"):
        return _payload(current=current, latest=None)

    latest = cached["latest"]
    dismissed = state.get("dismissed_version")
    has_update = _has_newer(latest, current) and latest != dismissed
    # 旧状态文件（无 source_url）回退主地址；正常路径取实际成功的地址
    source = str(cached.get("source_url") or "").strip() or _candidate_urls()[0]
    notes_url, download_url = _derived_urls(source, latest)
    return {
        "current": current,
        "latest": latest,
        "has_update": has_update,
        "notes": cached.get("notes") or "",
        "notes_url": notes_url if has_update else "",
        "download_url": download_url if has_update else "",
        # c-version-build-info：与 _payload 同批装配，两条返回路径 shape 一致
        # （tag 构建 get_build_info 自回 None——dev 总闸）
        "build": get_build_info(current),
    }


def _payload(*, current: str, latest: str | None) -> dict:
    return {
        "current": current,
        "latest": latest,
        "has_update": False,
        "notes": "",
        "notes_url": "",
        "download_url": "",
        "build": get_build_info(current),
    }


class DismissIn(BaseModel):
    version: str


@router.get("/api/update-check")
async def read_update_check():
    return await get_update_state()


@router.post("/api/update-check/dismiss")
async def dismiss_update(payload: DismissIn):
    version = payload.version.strip()
    if not is_valid_version(version):
        raise HTTPException(status_code=422, detail="invalid version format")
    state = _load_state()
    state["dismissed_version"] = version
    _save_state(state)
    return {"dismissed": version}
