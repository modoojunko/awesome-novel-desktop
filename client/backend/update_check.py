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
import hashlib
import ipaddress
import json
import logging
import os
import shutil
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from build_info import get_build_info
from config import DATA_ROOT
from http_client import build_async_client
from schema_version import app_version, is_newer, is_release_version, is_valid_version

logger = logging.getLogger(__name__)

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


# 全部状态文件读写收口到这把锁（评审 P1-3：写者不再只有事件循环——下载线程、
# 各端点都会碰 update-check.json；RMW 必须整段持锁，且**锁内不得 await**）。
_state_lock = threading.Lock()


def _save_state(state: dict) -> None:
    """tmp＋os.replace 原子写（评审 P1-3：截断的 JSON 会让全部记忆归零）。"""
    try:
        _state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = _state_path.with_name(_state_path.name + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, _state_path)
    except OSError:
        # 状态文件写失败不影响主流程：下次检测重来一次而已
        pass


def _mutate_state(mutate) -> dict:
    """持锁读-改-写；mutate 就地改 dict，返回改后全文（调用方不得再持有引用跨锁）。"""
    with _state_lock:
        state = _load_state()
        mutate(state)
        _save_state(state)
        return state


async def _fetch_one(url: str) -> dict | None:
    """抓取并解析单个 latest.json；任何失败返回 None（调用方负责切兜底）。

    v2 增量（silent-upgrade P1）：`platforms`（各平台包 url/sha256/size）与
    `auto_enabled`（发布侧总闸，缺省 true）可选透传——旧格式（仅 version/notes）
    照常工作，platforms=None 即自动下载链关闭，手动链不受影响。
    """
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
        platforms = data.get("platforms")
        return {
            "latest": latest,
            "notes": notes.strip() if isinstance(notes, str) else "",
            "platforms": platforms if isinstance(platforms, dict) else None,
            "auto_enabled": data.get("auto_enabled", True),
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
            logger.info("update-check: channel=%s latest=%s（本机 %s）",
                        url, got.get("latest"), get_client_version())
            return got
    logger.warning("update-check: 渠道全部不可达（candidates=%s）", _candidate_urls())
    return None


def _derived_urls(source_url: str, latest: str) -> tuple[str, str]:
    """由实际成功的检测地址推导：更新说明页（版本化目录）与官网下载入口。"""
    base = source_url.removesuffix("latest.json")
    p = urlparse(source_url)
    return f"{base}v{latest}/notes.html", f"{p.scheme}://{p.netloc}"


# ── silent-upgrade P1 第二片：后台自动下载（staged → 用户点「重启更新」）───────
# 暂存目录 = DATA_ROOT/updates（评审 P2-6：后端零新路径逻辑；安装器覆写清单不含
# data\，暂存件天然在保护区）。状态机落 update-check.json 的 auto 键：
#   idle → downloading → staged（→ applied，由壳层尾部写的 applied.json 认定）。
# 并发纪律（评审 P1-3/P1-4）：状态 RMW 全走 _mutate_state；下载单飞锁＋代际号＋
# 取消位——新版本检出/闸翻 false/用户「暂不」都让旧线程在下个检查点自尽。
# 签名：manifest 的 Ed25519 顶层签名待 update-k1 钥与 CI 发布链就位后强制（本片
# 实验期仅 sha256 双验，出站仍锁烘焙可信域——风险面＝CDN 写权限，记录在案）。

_UPDATES_DIR = Path(DATA_ROOT) / "updates"
_PENDING_PATH = _UPDATES_DIR / "pending.json"
_APPLIED_PATH = _UPDATES_DIR / "applied.json"
_PLATFORM_KEY = {"win32": "win", "darwin": "mac"}.get(sys.platform)
_DOWNLOAD_TIMEOUT = 60.0
_MAX_ATTEMPTS = 5
_DISK_FACTOR = 2.5

_dl_lock = threading.Lock()
_dl_thread: threading.Thread | None = None
_dl_cancel = threading.Event()
_dl_epoch = 0


def _staged_path(platform: dict) -> Path:
    name = Path(urlparse(str(platform.get("url") or "")).path).name or "update.pkg"
    return _UPDATES_DIR / name


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _set_auto_state(state: str, version: str, error: str = "",
                    received: int | None = None, total: int | None = None) -> None:
    def _mut(st: dict) -> None:
        block = {"state": state, "version": version, "last_error": error,
                 "updated_at": time.time()}
        if received is not None:
            block["received"] = received
        if total is not None:
            block["total"] = total
        st["auto"] = block

    _mutate_state(_mut)


def _validate_outbound_url_sync(url: str) -> bool:
    """线程版出站校验：与 async 版同规则（https＋可信域＋解析结果全公网）。

    评审 P2-7：async 版走事件循环线程池解析是为防 DNS 冻共享循环；下载线程里
    同步解析只阻塞自己，不构成冻结面。
    """
    try:
        p = urlparse(url)
        if p.scheme != "https" or not p.hostname:
            return False
        if p.hostname.lower() not in _trusted_hosts():
            return False
        infos = socket.getaddrinfo(p.hostname, 443, proto=socket.IPPROTO_TCP)
    except (OSError, ValueError):
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def _download_worker(version: str, platform: dict, epoch: int) -> None:
    """同步下载线程：.part 原子落盘 → sha256 复验 → staged。

    失败矩阵（评审 §4.2）：传输类（超时/断连/非 200）线程内退避重试 ≤5；
    环境类（磁盘不足）直接 failed 等下窗；sha 不符＝隔离重试；取消/换代即自尽。
    """
    url = str(platform.get("url") or "")
    want = str(platform.get("sha256") or "").lower()
    size = int(platform.get("size") or 0)
    dest = _staged_path(platform)
    part = dest.with_name(dest.name + ".part")
    attempts = 0
    try:
        while attempts < _MAX_ATTEMPTS:
            if _dl_cancel.is_set() or epoch != _dl_epoch:
                return
            attempts += 1
            try:
                free = shutil.disk_usage(Path(DATA_ROOT)).free
                need = int(size * _DISK_FACTOR) if size else 200 * 1024 * 1024
                if free < need:
                    _set_auto_state("failed", version, "disk full")
                    return
            except OSError:
                pass  # 预检本身失败不拦路：让下载去撞真实错误
            _set_auto_state("downloading", version, received=0, total=size or None)
            try:
                with (
                    httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client,
                    client.stream("GET", url) as resp,
                ):
                    if resp.status_code != 200:
                        raise OSError(f"http {resp.status_code}")
                    _UPDATES_DIR.mkdir(parents=True, exist_ok=True)
                    got_size = int(resp.headers.get("content-length") or 0) or size
                    received = 0
                    last_progress = 0.0
                    with open(part, "wb") as fh:
                        for chunk in resp.iter_bytes(512 * 1024):
                            if _dl_cancel.is_set() or epoch != _dl_epoch:
                                return
                            fh.write(chunk)
                            received += len(chunk)
                            now = time.time()
                            if now - last_progress >= 1.0:
                                last_progress = now
                                _set_auto_state("downloading", version,
                                                received=received,
                                                total=got_size or None)
                if _dl_cancel.is_set() or epoch != _dl_epoch:
                    return
                os.replace(part, dest)
            except (httpx.HTTPError, OSError):
                part.unlink(missing_ok=True)
                time.sleep(min(30, 2 * attempts))
                continue
            if _dl_cancel.is_set() or epoch != _dl_epoch:
                return
            got = _sha256_of(dest)
            if want and got != want:
                dest.rename(dest.with_name(f"{dest.name}.quarantine-{int(time.time())}"))
                _set_auto_state("downloading", version, "sha mismatch")
                time.sleep(min(30, 2 * attempts))
                continue
            _set_auto_state("staged", version)
            return
        _set_auto_state("failed", version, "attempts exhausted")
    finally:
        part.unlink(missing_ok=True)


def maybe_start_auto_download(fetched: dict, current: str) -> None:
    """自动下载触发闸：与 has_update/dismissed 解耦（评审 P2-11——「知道了」只关
    横幅，不停下载）。闸＝is_newer × auto_enabled × 本平台包在册 × 未「暂不」；
    已 staged 同版本不重下；单飞＝新触发使旧线程作废（epoch 递增）。
    """
    global _dl_thread, _dl_epoch
    if not is_release_version(current):
        return  # dev/冒烟无版本语义：手动检查可答真相，但自动链一票否决（R7）
    latest = str(fetched.get("latest") or "")
    if not latest or not is_newer(latest, current):
        return
    if fetched.get("auto_enabled") is False:
        return
    platforms = fetched.get("platforms")
    if not isinstance(platforms, dict):
        logger.info("update-check: manifest v1 (no platforms), auto chain disabled")
        return
    if _PLATFORM_KEY is None:
        logger.info("update-check: platform %s not supported by auto chain", sys.platform)
        return
    platform = platforms.get(_PLATFORM_KEY)
    if not isinstance(platform, dict) or not platform.get("url"):
        logger.info("update-check: no package for platform %s in manifest", _PLATFORM_KEY)
        return
    if not _validate_outbound_url_sync(str(platform["url"])):
        return
    with _state_lock:
        st = _load_state()
    if st.get("skipped_version") == latest:
        return
    auto = st.get("auto") if isinstance(st.get("auto"), dict) else {}
    if auto.get("state") == "staged" and auto.get("version") == latest:
        return
    with _dl_lock:
        _dl_epoch += 1
        _dl_cancel.set()
        if _dl_thread is not None and _dl_thread.is_alive():
            _dl_thread.join(timeout=5)
            if _dl_thread.is_alive():
                # 旧线程未在时限内自尽：放弃本轮触发（下个检测窗再来）——
                # 宁可不下载，也绝不出现两个写者写同一暂存文件
                _dl_cancel.clear()
                return
        _dl_cancel.clear()
        epoch = _dl_epoch
        _dl_thread = threading.Thread(
            target=_download_worker, args=(latest, platform, epoch),
            daemon=True, name=f"update-download-{latest}",
        )
        _dl_thread.start()


def auto_public_state() -> dict:
    """GET 载荷里的 auto 块（前端三态横幅唯一事实源）；壳层 applied 记录优先。"""
    with _state_lock:
        st = _load_state()
    auto = st.get("auto") if isinstance(st.get("auto"), dict) else {}
    out = {"state": str(auto.get("state") or "idle"), "version": auto.get("version") or None}
    if out["state"] == "downloading":
        out["received"] = int(auto.get("received") or 0)
        out["total"] = int(auto.get("total") or 0) or None
    marker_version = None
    try:
        marker = json.loads(_APPLIED_PATH.read_text(encoding="utf-8"))
        if isinstance(marker, dict):
            marker_version = marker.get("version") or None
    except (OSError, ValueError):
        pass
    # applied 记账只在「没有更新的 staged」时生效——10-15 真机实锤：marker 永久
    # 压住新 staged（「已就绪」按钮永不可见，升级链卡死在新版已备好却无入口）。
    if marker_version is not None:
        if out["state"] == "staged" and out["version"] and out["version"] != marker_version:
            pass  # staged 比已记账版本新 → staged 优先（就绪按钮可见）
        else:
            out = {"state": "applied", "version": marker_version}
    return out


async def get_update_state() -> dict:
    """检测入口：dev 跳过；节流内吃缓存；真实外呼每小时至多一次。"""
    current = get_client_version()
    if current == "dev":
        return _payload(current=current, latest=None)

    now = time.time()
    with _state_lock:
        state = _load_state()
    cached = state.get("cached") if isinstance(state.get("cached"), dict) else None
    last = float(state.get("last_check_at") or 0)

    # 节流只看 last_check_at（成败都记时）：失败后 cached 为空也占节流窗，
    # 弱网下 15 分钟轮询不会连打外呼
    if (now - last) >= _CHECK_INTERVAL:
        fetched = await _fetch_latest()
        if fetched is not None:
            cached = fetched

        def _record(st: dict) -> None:
            st["last_check_at"] = now
            st["cached"] = cached or {}

        state = _mutate_state(_record)
        if fetched is not None:
            # 自动下载触发（fire-and-forget；闸门与单飞见 maybe_start_auto_download）。
            # to_thread：触发段含同步 DNS 解析与 join，MUST NOT 跑在共享事件循环上。
            await asyncio.to_thread(maybe_start_auto_download, fetched, current)

    if not cached or not cached.get("latest"):
        return _payload(current=current, latest=None)

    latest = cached["latest"]
    dismissed = state.get("dismissed_version")
    # 「暂不」与「知道了」同权关闭横幅面（自动下载闸已在触发段单查 skipped_version）；
    # 手动检查（refresh）照答真相，不受两者约束
    skipped = state.get("skipped_version")
    has_update = _has_newer(latest, current) and latest != dismissed and latest != skipped
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
        "auto": auto_public_state(),
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
        "auto": auto_public_state(),
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
    _mutate_state(lambda st: st.__setitem__("dismissed_version", version))
    return {"dismissed": version}


@router.post("/api/update-check/refresh")
async def refresh_update_check():
    """手动「检查更新」入口（P1 首片）：绕过节流做一次真实外呼取真相。

    口径：
    - 外呼仍走 `_fetch_latest` 单源（出站校验/兜底域/载荷校验全复用），只绕节流节奏；
    - dev 构建的周期横幅照旧整体跳过（无版本语义），本端点是**人 explicit 点击**——
      dev 排序恒最低，任何官方版都判「更新可用」，测试包可当场验入口通不通；
    - 不查 dismissed_version：手动点击＝要看真相，不因先前关过横幅而吞提示；
    - 成功顺带回写缓存（小时节流窗内后续 GET 直接吃新鲜结果），失败不动缓存。
    """
    current = get_client_version()
    fetched = await _fetch_latest()
    if fetched is None:
        return {"current": current, "latest": None, "has_update": False,
                "notes": "", "checked": False, "build": get_build_info(current)}

    def _record(st: dict) -> None:
        st["last_check_at"] = time.time()
        st["cached"] = fetched

    _mutate_state(_record)
    await asyncio.to_thread(maybe_start_auto_download, fetched, current)
    latest = fetched["latest"]
    return {"current": current, "latest": latest,
            "has_update": _has_newer(latest, current),
            "notes": fetched.get("notes") or "", "checked": True,
            "auto": auto_public_state(),
            "build": get_build_info(current)}


class SkipIn(BaseModel):
    version: str


@router.post("/api/update-check/auto-skip")
async def auto_skip_update(payload: SkipIn):
    """「暂不」（P1 第二片）：本版本不再自动（取消在途下载＋删暂存件）；手动
    「检查更新」不受影响（换回该版本只消把 skip 记忆清掉——暂只随版本升级自然失效）。
    """
    version = payload.version.strip()
    if not is_valid_version(version):
        raise HTTPException(status_code=422, detail="invalid version format")
    def _cancel_and_join() -> None:
        global _dl_epoch
        # 同步段（含 join）MUST 卸出事件循环——本模块自己的禁令（与触发段同修）
        with _dl_lock:
            _dl_epoch += 1
            _dl_cancel.set()
            # 与 worker 收尾段（sha 复验→staged 写入）串行：否则 skip 先落盘、
            # worker 后收尾时 staged 状态与暂存件双双复活，「本版本不再自动」被绕过
            if _dl_thread is not None and _dl_thread.is_alive():
                _dl_thread.join(timeout=15)

    await asyncio.to_thread(_cancel_and_join)

    def _mut(st: dict) -> None:
        st["skipped_version"] = version
        auto = st.get("auto") if isinstance(st.get("auto"), dict) else {}
        if auto.get("version") == version:
            st["auto"] = {"state": "idle", "version": None}

    _mutate_state(_mut)
    if _UPDATES_DIR.is_dir():
        for p in _UPDATES_DIR.iterdir():
            try:
                if p.is_file() and p.name != "applied.json":
                    p.unlink(missing_ok=True)
            except OSError:
                pass
    return {"skipped": version}


@router.post("/api/update-check/apply")
async def apply_update():
    """「重启更新」点击（P1 第二片）：复验就位包 → 落一次性 pending（壳层退出链消费）。

    闸（评审 P2-5）：即时重取 manifest——auto_enabled 翻 false / 版本已换代 /
    暂存件缺失 → 一律 409 拒绝，**不落标记不关窗**（前端提示走手动链）。
    pending 唯一属主＝后端写、壳层只读（评审 P1-3）；TTL 与壳层同值 10 分钟。

    ⚠️ 性能契约（10-15 真机复盘实锤）：本端点必须**秒回**——首次上线把 34MB 完整
    sha256 复验也放在这里（to_thread 也要 1-3s），叠加 manifest 重取后用户点下
    「重启更新」窗口 3-5 秒没动静＝被当成没反应手动关窗，链条中断（V 系现场：
    第一次点击 pending 未落盘，退出链无活可干）。完整复验的职责本来就在壳层
    退出链 apply 段（关窗之后用户不再盯屏）——此处只做闸门＋存在性检查。
    """
    with _state_lock:
        st = _load_state()
    auto = st.get("auto") if isinstance(st.get("auto"), dict) else {}
    if auto.get("state") != "staged" or not auto.get("version"):
        raise HTTPException(status_code=409, detail="no staged update")
    version = str(auto["version"])
    fetched = await _fetch_latest()
    if fetched is None:
        # 渠道瞬时抖动 ≠ 总闸关闭：降级消费缓存清单（≤1h 新鲜度）——真机复盘：
        # 弱网下把暂态抖动变成用户意图失败（409）会中断链条；安全裕度由退出链
        # 的完整 sha 复验兜底。显式 auto_enabled=False / 版本换代仍硬拒。
        with _state_lock:
            cached = st.get("cached") if isinstance(st.get("cached"), dict) else {}
        fetched = cached or None
        if fetched is None:
            raise HTTPException(status_code=409, detail="update channel unavailable")
    if fetched.get("auto_enabled") is False:
        raise HTTPException(status_code=409, detail="auto updates disabled")
    if str(fetched.get("latest") or "") != version:
        raise HTTPException(status_code=409, detail="staged version stale")
    platforms = fetched.get("platforms") or {}
    platform = platforms.get(_PLATFORM_KEY) if _PLATFORM_KEY else None
    if not isinstance(platform, dict):
        raise HTTPException(status_code=409, detail="no package for this platform")
    dest = _staged_path(platform)
    if not dest.exists():
        raise HTTPException(status_code=409, detail="staged file missing")
    pending = {"version": version, "file": str(dest),
               "sha256": str(platform.get("sha256") or "").lower(),
               "relaunch": True, "issued_at": time.time()}
    try:
        _UPDATES_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _PENDING_PATH.with_name("pending.json.tmp")
        tmp.write_text(json.dumps(pending, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _PENDING_PATH)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"cannot write pending marker: {exc}")
    return {"ok": True, "version": version}
