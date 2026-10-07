"""提示词包同步器（c-prompt-pack-client 3.x）。

登录成功／启动补偿／档位变化／手动触发四钩子 → 静默 daemon 线程：
    GET latest.json（CDN，SSRF 防线照抄 update_check：https＋烘焙可信域＋DNS 拒非公网）
    → 闸门（min_client_version／已最新／版本高水位防旧版重放／min_pack_version 召回底线）
    → 按档下载 v{N}/{tier}.bin＋v{N}/manifest.json
    → S端 POST prompt-pack/key 换 CEK（403 按档降序重试一次；404 重取 latest）
    → 七道校验（Ed25519 验签／latest↔manifest 自洽／bundle sha256＋size／key_id 匹配／
       AEAD 解密／模板级 sha256＋白名单＋分层标记一致性／版本单调）
    → 原子安装（.staging-v{N} → rename v{N} → receipt 原子写 → 清理旧版，失败 defer）

失败一律静默沿用已装版本（评审失败矩阵）；状态经 get_status() 供 /auth/verify 与
前端四态卡消费。

**bundle 与 manifest 格式契约（与 prompts 仓 publish.py 对齐）**：
- `{tier}.bin` = `nonce(12 bytes) || AES-256-GCM ciphertext`；明文 = JSON
  `{"version": str, "tier": str, "templates": {名: 文本}}`。
- manifest 签名 = Ed25519 over `json.dumps(manifest_without_signature, sort_keys=True,
  separators=(",", ":"))`；`signer_key_id` 选钥（信任钥集合，支持轮换）。
- CEK 由 S端 `/api/prompt-pack/key` 下发（base64，32 字节）。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import threading
import time
from urllib.parse import urlparse

import httpx

from prompt_pack import (
    STAGING_PREFIX,
    clear_receipt,
    container,
    migrate_plaintext,
    pack_root,
    read_highwatermark,
    read_receipt,
    resolve_dir,
    verify_text,
    write_highwatermark,
    write_receipt,
)
from schema_version import app_version, is_newer

logger = logging.getLogger(__name__)

# ── 配置（烘焙优先，缺省走静态托管主/兜底域——与 update_check 同源模式） ─────────
_DEFAULT_PACK_URL = "https://www.awesomenovel.com/prompts/latest.json"
_DEFAULT_PACK_URL_FALLBACK = (
    "https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/prompts/latest.json"
)

_FETCH_TIMEOUT = 6.0          # CDN 静态托管无冷启动（update_check 口径）
_MAX_BUNDLE_BYTES = 8 * 1024 * 1024  # 包体上限（防内存炸弹；现网 ~300KB/档）
_TIER_ORDER = ("free", "standard", "pro", "max")
_ALIASES = {"monthly": "pro", "quarterly": "pro", "yearly": "pro", "lifetime": "max", "trial": "pro"}
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

# ── 状态（供 /auth/verify 与前端四态卡） ─────────────────────────────────────
_state: dict = {"phase": "missing", "reason": "", "tier": "", "version": "", "step": "",
                "updated_at": 0.0}
_lock = threading.Lock()
_syncing = False
# c-prompt-pack-onboard-modal：在途触发的待重跑档位（只排一级）。None＝无排队；
# 手动触发不带档位（None 语义=由本地配置解析）与「无排队」用哨兵区分
_PENDING_FROM_CONFIG = object()
_pending_tier: object | None = None


def get_status() -> dict:
    """包状态快照：phase ∈ syncing/ready/missing/failed/tier_denied；step 为同步分步进度
    （probe/download/install，c-prompt-pack-onboard-modal：引导弹窗消费，非同步期恒空）。

    口径（失败矩阵＋dev 兜底，2026-10-05 评审修正）：**有可用模板来源即 ready
    （全静默）**——①已装包（resolve_dir）②开发/测试态的包内目录（frozen 发布包
    无此目录，故生产不受影响）。更新失败但旧包能写、或 dev 直读仓库单源时，都给
    用户零打扰；reason 保留为诊断字段（AcctMenu 诊断串）。两来源皆无时按最近一次
    尝试结果落 missing/syncing/failed/tier_denied（前端四态卡据此分派）。
    """
    with _lock:
        st = dict(_state)
    if resolve_dir() or _dev_fallback_available():
        st["phase"] = "ready"
    return st


def _dev_fallback_available() -> bool:
    """包内开发目录是否可用（dev/测试态直读仓库单源）。

    PROMPT_PACK_MODE=force 时禁用（e2e 强制包模式）；frozen 发布包内无该目录
    （build.spec 已摘）→ 恒 False，生产永远走已装包判定。
    """
    if os.environ.get("PROMPT_PACK_MODE") == "force":
        return False
    bundled = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")
    try:
        return any(n.endswith(".prompt") for n in os.listdir(bundled))
    except OSError:
        return False


def reset_state() -> None:
    """把模块级状态复位（**测试夹具用**）。

    为什么需要显式复位：发布态本模块是编译扩展，`importlib.reload()` 对扩展模块
    不会重跑初始化，模块级状态（`_state`/`_syncing`/`_pending_tier`）因此会跨用例
    残留——夹具靠 reload 复位的老写法在编译形态下失效。显式复位两态通吃
    （.py 与 .so 同一套测试）。
    """
    global _syncing, _pending_tier  # noqa: PLW0603 — 模块级单例状态，复位即其用途
    with _lock:
        _state.update(phase="missing", reason="", tier="", version="", step="", updated_at=0.0)
        _syncing = False
        _pending_tier = None


def _set_state(phase: str, reason: str = "", tier: str = "", version: str = "") -> None:
    with _lock:
        # step 随任意相位迁移清空：终态（ready/failed）不该残留进行中分步；
        # 同步中的分步由 _set_step 显式推进
        _state.update(phase=phase, reason=reason, step="", updated_at=time.time())
        if tier:
            _state["tier"] = tier
        if version:
            _state["version"] = version


def _set_step(step: str) -> None:
    """同步分步进度（probe/download/install）——只推进不迁相位，弹窗轮询消费。"""
    with _lock:
        _state["step"] = step


# ── URL 与信任根 ─────────────────────────────────────────────────────────────


def _candidate_urls() -> list[str]:
    urls = []
    for name, default in (
        ("CLIENT_PROMPT_PACK_URL", _DEFAULT_PACK_URL),
        ("CLIENT_PROMPT_PACK_URL_FALLBACK", _DEFAULT_PACK_URL_FALLBACK),
    ):
        u = (os.environ.get(name) or "").strip() or default
        if u not in urls:
            urls.append(u)
    return urls


def _trusted_hosts() -> set[str]:
    return {h for h in (urlparse(u).hostname for u in _candidate_urls()) if h}


def _validate_outbound(url: str) -> bool:
    """仅 https＋可信域＋解析结果全公网。同步实现——本函数只在 daemon 线程跑，
    不占用 uvicorn 事件循环（update_check 的异步版约束不适用于此）。"""
    try:
        p = urlparse(url)
        if p.scheme != "https" or not p.hostname:
            return False
        host = p.hostname.lower()
        if host not in _trusted_hosts():
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
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


def _derive(url: str, path: str) -> str:
    """从已过校验的基址派生资源 URL——manifest 内出现的 URL 一律不采信。"""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}{p.path.rsplit('/', 1)[0]}"
    return f"{base}/{path.lstrip('/')}"


def _pubkeys() -> dict[str, bytes]:
    """信任钥集合 {kid: 公钥 bytes}——发布构建经 release.json 烘焙注入；
    测试/联调经 CLIENT_PACK_PUBKEYS（JSON {kid: b64}）注入。"""
    raw = (os.environ.get("CLIENT_PACK_PUBKEYS") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {k: base64.b64decode(v) for k, v in data.items() if isinstance(v, str)}
    except (ValueError, TypeError):
        return {}


# ── 闸门与校验 ───────────────────────────────────────────────────────────────


def _normalize_tier(tier: str) -> str:
    t = (tier or "").strip().lower()
    if t in _TIER_ORDER:
        return t
    if t in _ALIASES:
        return _ALIASES[t]
    return "free"


def _tier_candidates(local_tier: str) -> list[str]:
    """从本地档位向下的降档重试序列（403 时用）：max→pro→standard→free。"""
    t = _normalize_tier(local_tier)
    i = _TIER_ORDER.index(t)
    return list(reversed(_TIER_ORDER[: i + 1]))


def _verify_manifest_signature(manifest: dict, keys: dict[str, bytes]) -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        kid = manifest.get("signer_key_id", "")
        sig_b64 = manifest.get("signature", "")
        pub = keys.get(kid)
        if not pub or not sig_b64:
            return False
        payload = {k: v for k, v in manifest.items() if k != "signature"}
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        Ed25519PublicKey.from_public_bytes(pub).verify(base64.b64decode(sig_b64), blob)
        return True
    except Exception:
        return False


def _template_marks_ok(name: str, text: str) -> bool:
    """分层标记一致性：<<system>>/<<user>> 要么都有要么都无（片段资产无标记合法）。"""
    has_sys = "<<system>>" in text
    has_usr = "<<user>>" in text
    return has_sys == has_usr


def _decrypt_bundle(bin_bytes: bytes, cek: bytes) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce, ct = bin_bytes[:12], bin_bytes[12:]
    plain = AESGCM(cek).decrypt(nonce, ct, None)
    return json.loads(plain.decode("utf-8"))


# ── 下载与 S端 换钥 ──────────────────────────────────────────────────────────


def _fetch_json(client: httpx.Client, url: str) -> dict | None:
    if not _validate_outbound(url):
        return None
    try:
        r = client.get(url)
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except (httpx.HTTPError, ValueError):
        return None


def _fetch_bytes(client: httpx.Client, url: str) -> bytes | None:
    if not _validate_outbound(url):
        return None
    try:
        with client.stream("GET", url) as r:
            if r.status_code != 200:
                return None
            chunks, total = [], 0
            for chunk in r.iter_bytes():
                total += len(chunk)
                if total > _MAX_BUNDLE_BYTES:
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
    except httpx.HTTPError:
        return None


def _exchange_cek(key_id: str, version: str) -> tuple[dict | None, int]:
    """S端 换钥（复用 call_server_api：主/兜底基址＋60s 冷启动口径）。
    返回 (value|None, code)——code 透传 S端 信封（0 成功／403 档位／404 退役／-1 不可达）。
    """
    from auth_local.service import call_server_api

    async def _go() -> dict:
        return await call_server_api(
            "prompt-pack/key",
            method="POST",
            json_body={"key_id": key_id, "version": version},
            with_token=True,  # 换钥端点需登录态（Bearer）
        )

    try:
        resp = asyncio.run(_go())
    except Exception as e:  # pragma: no cover - 防御
        logger.warning("event=pack_cek_exchange_error err=%s", e)
        return None, -1
    code = resp.get("code", -1)
    if code == 0:
        value = resp.get("data") if isinstance(resp.get("data"), dict) else resp.get("value")
        return (value if isinstance(value, dict) else None), 0
    return None, code


# ── 安装 ─────────────────────────────────────────────────────────────────────


def _install(version: str, tier: str, key_id: str, min_client_version: str | None,
             templates: dict[str, str], manifest: dict) -> bool:
    root = pack_root()
    os.makedirs(root, exist_ok=True)
    staging = os.path.join(root, f"{STAGING_PREFIX}v{version}")
    target = os.path.join(root, f"v{version}")
    try:
        if os.path.exists(staging):
            shutil.rmtree(staging)
        os.makedirs(staging)
        # c-prompt-pack-hardening：模板**只以容器形态落盘**（明文仅在内存，D1/D3）
        hashes = {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in templates.items()}
        with open(os.path.join(staging, container.CONTAINER_NAME), "wb") as f:
            f.write(container.seal(templates, version))
        with open(os.path.join(staging, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)
        if os.path.exists(target) and resolve_dir() == target:
            # 同版本换档（tier 升级）：容器在用不可整删——合并「旧容器表 ∪ 新包表」后
            # 整体重封再原子替换（旧容器解不开时以新包为准：换机/被改场景整体重写）。
            shutil.rmtree(staging)
            existing = read_receipt() or {}
            merged: dict[str, str] = {}
            try:
                with open(os.path.join(target, container.CONTAINER_NAME), "rb") as f:
                    merged = container.open_container(f.read(), version)
            except (OSError, container.ContainerInvalid):
                merged = {}
            merged.update(templates)
            tmp = os.path.join(target, container.CONTAINER_NAME + ".tmp")
            with open(tmp, "wb") as f:
                f.write(container.seal(merged, version))
            os.replace(tmp, os.path.join(target, container.CONTAINER_NAME))
            hashes2 = {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in merged.items()}
            with open(os.path.join(target, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False)
            receipt2 = dict(existing)
            receipt2.update(
                version=version, tier=tier, key_id=key_id,
                installed_at=time.time(), templates=hashes2,
            )
            if min_client_version:
                receipt2["min_client_version"] = min_client_version
            write_receipt(receipt2)
            _set_state("ready", tier=tier, version=version)
            return True
        if os.path.exists(target):
            shutil.rmtree(target)
        os.rename(staging, target)
        receipt = {
            "version": version,
            "tier": tier,
            "key_id": key_id,
            "installed_at": time.time(),
            "templates": hashes,
        }
        if min_client_version:
            receipt["min_client_version"] = min_client_version
        write_receipt(receipt)
        write_highwatermark(version)
        _set_state("ready", tier=tier, version=version)
        _cleanup_old(root, keep={"v" + version})
        return True
    except (OSError, container.ContainerInvalid) as e:
        # 含「本地包密钥不可用」（container 侧统一转 ContainerInvalid）：安装失败即沿用现态，
        # 不得把异常抛到调用栈外（后台同步线程/启动钩子都必须静默降级）
        logger.warning("event=pack_install_error err=%s", e)
        shutil.rmtree(staging, ignore_errors=True)
        return False


def _cleanup_old(root: str, keep: set[str]) -> None:
    """清理旧版本目录：保留当前＋前一版；本进程启动时 receipt 指向版永不删；
    失败一律 defer（Windows 句柄竞态——下轮再试）。"""
    from schema_version import version_sort_key

    try:
        dirs = sorted(
            (d for d in os.listdir(root) if d.startswith("v") and os.path.isdir(os.path.join(root, d))),
            key=lambda d: version_sort_key(d[1:]),
            reverse=True,
        )
    except OSError:
        return
    protected = set(keep)
    protected |= set(dirs[:2])  # 当前＋前一版
    for d in dirs:
        if d in protected:
            continue
        try:
            shutil.rmtree(os.path.join(root, d))
        except OSError:
            pass  # defer：下轮再试，不阻塞安装


def _installed_pack_intact(receipt: dict | None) -> bool:
    """按 receipt 复核已装目录全部模板哈希（评审 P1 修复）。

    spec（prompt-pack-delivery）：读时校验失败须能自愈——loader 只能拒绝读取，
    修复动作必须在同步器侧有触发器。本函数即该触发器：任一模板缺失/被改即
    False，sync_once 据此跳过「已最新」短路，走同版本重装修复。
    """
    if not receipt:
        return False
    vdir = os.path.join(pack_root(), f"v{receipt.get('version')}")
    templates = receipt.get("templates")
    if not isinstance(templates, dict) or not templates:
        return False
    # 旧版明文包先就地迁移（幂等）：迁移成功即按新形态继续复核，用户无需重下（保离线）
    migrate_plaintext(vdir)
    try:
        with open(os.path.join(vdir, container.CONTAINER_NAME), "rb") as f:
            actual = container.open_container(f.read(), str(receipt.get("version")))
    except (OSError, container.ContainerInvalid):
        return False
    for name, expect in templates.items():
        if not isinstance(expect, str) or not expect:
            return False
        text = actual.get(name)
        if not isinstance(text, str) or not verify_text(text, expect):
            return False
    return True


# ── 主流程 ───────────────────────────────────────────────────────────────────


def probe_latest() -> dict:
    """版本探测（c-prompt-pack-onboard-modal：只探测不安装）。

    取 latest.json（验签＋min_client_version 闸）与已装 receipt 版本比较；不下载、
    不装、不调 S端、不触碰状态机（探测不得把 ready 抖成 syncing）。任何不可得
    （CDN 不可达/验签失败/无信任钥）＝无更新静默返回。dev 态（非 force 且包内目录
    可用、且无已装包）恒无更新——存量 e2e 零改动的关键。
    """
    receipt = read_receipt()
    installed_version = str(receipt.get("version") or "") if receipt else ""
    no_update = {"installed_version": installed_version, "latest_version": "",
                 "update_available": False, "source": "pack"}
    if not installed_version and _dev_fallback_available():
        # dev/测试态：包内目录可用即视为已就绪（source=dev，前端据此静默，
        # 不弹首装窗——存量 e2e 与书架请求预算零扰动）
        return {**no_update, "source": "dev"}
    keys = _pubkeys()
    if not keys:
        return no_update
    with httpx.Client(timeout=_FETCH_TIMEOUT, follow_redirects=False) as client:
        latest = None
        for url in _candidate_urls():
            latest = _fetch_json(client, url)
            if latest:
                break
    if not latest or not _verify_manifest_signature(latest, keys):
        return {**no_update, "reason": "probe_unavailable"}
    version = str(latest.get("version") or "")
    min_client = latest.get("min_client_version")
    if isinstance(min_client, str) and min_client and app_version() not in ("dev",) and is_newer(min_client, app_version()):
        return {**no_update, "reason": "min_client_version"}
    update_available = bool(version and installed_version and is_newer(version, installed_version))
    return {"installed_version": installed_version, "latest_version": version,
            "update_available": update_available}


def sync_once(
    local_tier: str | None = None,
    _retry: bool = False,
    _latest: tuple[dict, str] | None = None,
) -> dict:
    """执行一次同步（幂等、可重入保护在 trigger 侧）。返回最终状态快照。

    `_retry`/`_latest`：404（密钥退役）自愈路径内部使用——重取 latest 后重试
    **恰好一次**；`_latest` 直接携带 cache-bust 取回的新指针，避免重试时又被
    CDN 缓存的陈旧指针挡回。
    """
    if local_tier is None:
        try:
            from auth_local.service import get_local_config

            local_tier = (get_local_config().get("tier") or "").strip()
        except Exception:
            local_tier = ""
    tier = _normalize_tier(local_tier)
    keys = _pubkeys()
    if not keys:
        # 无信任钥（开发态未注入）＝不可验签，不假装成功；保持现状静默
        logger.info("event=pack_sync_skip reason=no_trusted_keys")
        return get_status()

    _set_state("syncing", tier=tier)
    _set_step("probe")
    hw = read_highwatermark()
    receipt = read_receipt()
    # 本地完整性预检（评审 P1）：版本已最新也要先验已装文件——损坏/被改时不得短路，
    # 走同版本重装修复（spec：读时校验失败须可自愈）
    intact = _installed_pack_intact(receipt)

    with httpx.Client(timeout=_FETCH_TIMEOUT, follow_redirects=False) as client:
        if _latest is not None:
            latest, latest_url = _latest
        else:
            latest = None
            latest_url = ""
            for url in _candidate_urls():
                latest = _fetch_json(client, url)
                if latest:
                    latest_url = url
                    break
        if not latest:
            _set_state("failed", reason="cdn_unreachable")
            return get_status()

        # 信任链前置（2026-10-05 评审 P1）：latest 的控制字段（min_client_version/
        # min_pack_version/tiers 摘要）驱动「跳过更新/清回执/下载校验」——必须先验签
        # 再消费，否则 CDN 侧篡改可冻结全量更新或伪造召回。验签不过＝该源不可信。
        if not _verify_manifest_signature(latest, keys):
            logger.warning("event=pack_sync_fail reason=latest_signature")
            _set_state("failed", reason="latest_signature")
            return get_status()

        # 闸门：min_client_version（新包+旧客户端）／高水位（旧版重放）／min_pack_version（召回）
        min_client = latest.get("min_client_version")
        if isinstance(min_client, str) and min_client and app_version() not in ("dev",) and is_newer(min_client, app_version()):
            logger.info("event=pack_sync_skip reason=min_client_version need=%s", min_client)
            # 须落终态（评审 P1-2）：不写回状态时未装包场景 phase 永停 syncing、
            # step 永停 probe——前端弹窗会锁着轮询到 180s 假失败。已装包时
            # get_status 的 resolve_dir 覆盖照常回 ready（现网静默语义不变）。
            _set_state("missing", reason="min_client_version")
            return get_status()
        version = str(latest.get("version") or "")
        current = str(receipt.get("version") or "") if receipt else ""
        if not version:
            _set_state("failed", reason="bad_latest")
            return get_status()
        min_pack = str(latest.get("min_pack_version") or "")
        if min_pack and current and is_newer(min_pack, current):
            # 已装版低于召回底线：停用已装版（resolve_dir 会回落或 none），继续装新的
            clear_receipt()
        # 同版本换档（升级套餐后 receipt 仍是旧档）：不短路，走补写路径
        same_version_new_tier = bool(
            current
            and version == current
            and _normalize_tier(str(receipt.get("tier") or "")) != tier
        )
        repair_same_version = bool(current) and version == current and not intact
        if current and version == current and not same_version_new_tier and not repair_same_version:
            _set_state("ready", tier=tier, version=current)
            return get_status()
        if hw and not is_newer(version, hw) and not (
            version == hw and (same_version_new_tier or repair_same_version)
        ):
            logger.info("event=pack_sync_skip reason=highwatermark cur=%s hw=%s", version, hw)
            _set_state("ready", tier=tier, version=current)
            return get_status()

        tiers = latest.get("tiers") if isinstance(latest.get("tiers"), dict) else {}
        if tier not in tiers:
            _set_state("failed", reason="tier_not_in_latest")
            return get_status()

        # 下载 manifest ＋按档 bundle；403 降档重试一次
        _set_step("download")
        manifest = None
        for u in (latest_url,):
            m = _fetch_json(client, _derive(u, f"v{version}/manifest.json"))
            if m:
                manifest = m
        if not manifest or not _verify_manifest_signature(manifest, keys):
            _set_state("failed", reason="signature")
            return get_status()
        # latest↔manifest 自洽
        if str(manifest.get("version") or "") != version:
            _set_state("failed", reason="mismatch")
            return get_status()

        last_reason = "exchange"
        for cand in _tier_candidates(tier):
            entry = tiers.get(cand)
            if not isinstance(entry, dict):
                continue
            key_id = str(entry.get("key_id") or "")
            value, code = _exchange_cek(key_id, version)
            if code == 403:
                last_reason = "tier"
                continue
            if code == 404:
                # 设计口径（D1）：404=密钥退役信号——重取 latest（绕 CDN 缓存）
                # 后重试恰好一次；版本没变则落 failed 由下次触发/手动重试兜底。
                if not _retry:
                    fresh = _fetch_json(client, f"{latest_url}?cb={int(time.time())}")
                    if fresh and str(fresh.get("version") or "") not in ("", version):
                        return sync_once(local_tier, _retry=True, _latest=(fresh, latest_url))
                _set_state("failed", reason="key_retired")
                return get_status()
            if code != 0 or not value:
                last_reason = "exchange" if code != 403 else "tier"
                continue

            if str(value.get("key_id") or "") != key_id:
                _set_state("failed", reason="key_mismatch")
                return get_status()
            try:
                cek = base64.b64decode(str(value.get("cek") or ""))
                if len(cek) not in (16, 24, 32):
                    raise ValueError("bad cek length")
            except (ValueError, TypeError):
                _set_state("failed", reason="bad_cek")
                return get_status()

            # 评审 P3：同版本换档/降档收敛探测——S 判档仍等于已装档且本地完好时，
            # 无需重下重装（无损语义：升档仍会走下方下载安装）
            if (
                version == current
                and intact
                and cand == _normalize_tier(str((receipt or {}).get("tier") or ""))
            ):
                _set_state("ready", tier=cand, version=version)
                return get_status()

            bin_bytes = _fetch_bytes(client, _derive(latest_url, f"v{version}/{cand}.bin"))
            if not bin_bytes:
                _set_state("failed", reason="download")
                return get_status()
            expect = entry.get("sha256")
            if expect and hashlib.sha256(bin_bytes).hexdigest() != expect:
                _set_state("failed", reason="bundle_hash")
                return get_status()
            expect_size = entry.get("size")
            if isinstance(expect_size, int) and expect_size != len(bin_bytes):
                _set_state("failed", reason="bundle_size")
                return get_status()

            try:
                payload = _decrypt_bundle(bin_bytes, cek)
            except Exception:
                _set_state("failed", reason="decrypt")
                return get_status()

            templates = payload.get("templates") if isinstance(payload.get("templates"), dict) else {}
            tpl_hashes = manifest.get("templates") if isinstance(manifest.get("templates"), dict) else {}
            ok = bool(templates)
            for name, text in templates.items():
                if not _SAFE_NAME_RE.match(name) or not isinstance(text, str) or not text:
                    ok = False
                    break
                if not _template_marks_ok(name, text):
                    ok = False
                    break
                expect_h = tpl_hashes.get(name)
                if expect_h and hashlib.sha256(text.encode("utf-8")).hexdigest() != expect_h:
                    ok = False
                    break
            if not ok:
                _set_state("failed", reason="template_check")
                return get_status()

            min_client_manifest = manifest.get("min_client_version")
            _set_step("install")
            got = _install(
                version, cand, key_id,
                min_client_manifest if isinstance(min_client_manifest, str) else None,
                templates, manifest,
            )
            if got:
                logger.info("event=pack_sync_ok version=%s tier=%s n=%d", version, cand, len(templates))
                return get_status()
            _set_state("failed", reason="install")
            return get_status()

        phase = "tier_denied" if last_reason == "tier" else "failed"
        _set_state(phase, reason=last_reason, tier=tier)
        return get_status()


def trigger_sync(local_tier: str | None = None) -> bool:
    """后台触发一次同步（重入保护）；返回是否新起了线程。

    c-prompt-pack-onboard-modal：在途时新触发排队（后到覆盖先到），工作线程循环
    消费到空。**退出判定与 `_syncing` 复位在同一次加锁内完成**——触发方若在「本
    线程最后一次消费为空」与「线程退出」之间到达，必见 `_syncing=True` 而排队，
    该排队随后被本线程同一临界区内的下一次检查消费；不存在「返回 False 却被收尾
    清空」的丢弃窗口（spec：在途触发不吞；review-agent 轮 P2）。首装竞态主成因
    即「未登录启动同步占锁挂在 S端 冷启动上、登录触发被吞」，与 `maybe_after_auth`
    未登录早退同批收口。
    """
    global _syncing, _pending_tier
    with _lock:
        if _syncing:
            _pending_tier = local_tier if local_tier is not None else _PENDING_FROM_CONFIG
            return False
        _syncing = True

    def _run() -> None:
        global _syncing, _pending_tier
        try:
            sync_once(local_tier)
            # 消费到空（评审 P2-1）：重跑本身也是在途同步——期间到达的新触发同样
            # SHALL NOT 被丢弃。同步幂等（版本闸＋七道校验），连续重跑至多多耗一次
            # CDN/S端往返；后到覆盖先到，不会无限排队。
            while True:
                with _lock:
                    if _pending_tier is None:
                        # 退出与复位同锁（review-agent 轮 P2）：此后到达的触发
                        # 必见 _syncing=False → 起新线程，绝无被丢的排队
                        _syncing = False
                        return
                    nxt, _pending_tier = _pending_tier, None
                sync_once(None if nxt is _PENDING_FROM_CONFIG else nxt)
        except Exception as e:  # pragma: no cover - 后台线程兜底（sync_once 按契约不抛）
            logger.warning("event=pack_sync_unexpected err=%s", e)
            _set_state("failed", reason="unexpected")
            with _lock:
                # 异常路径接受丢弃：防御分支，与正常退出路径不复用（其复位已在锁内）
                _pending_tier = None
                _syncing = False

    t = threading.Thread(target=_run, name="prompt-pack-sync", daemon=True)
    t.start()
    return True


def maybe_after_auth() -> None:
    """登录/校验成功钩子：未装包或档位与已装不一致时触发同步（静默）。

    c-prompt-pack-onboard-modal：未登录（本地无令牌）早退——无令牌换钥必然 401，
    且 30-60s 冷启动占锁窗口会吞掉真正的登录触发。
    """
    try:
        from auth_local.service import get_local_config

        cfg = get_local_config()
        if not (cfg.get("token") or "").strip():
            logger.info("event=pack_sync_skip reason=not_logged_in")
            return
        local_tier = _normalize_tier(cfg.get("tier") or "")
        receipt = read_receipt()
        # 早退三条件：档位一致＋目录可解析＋**完整性复核通过**（评审 P1：损坏/被改
        # 的已装包也是「需要同步」的一种状态——启动/登录钩子即触发同版本重装修复）
        if (
            receipt
            and _normalize_tier(str(receipt.get("tier") or "")) == local_tier
            and resolve_dir()
            and _installed_pack_intact(receipt)
        ):
            return
        trigger_sync(local_tier)
    except Exception:  # pragma: no cover - 钩子绝不阻塞登录
        pass
