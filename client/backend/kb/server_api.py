"""C 端 → S 端知识库签名/下载客户端（s-kb-signed-delivery）。

- `sign(scope, ...)`：带登录态向 S 端换短时 COS 签名 URL；无 token 不联网。
- `fetch_signed(url, max_bytes)`：出站守卫（COS 桶域白名单 + fake-ip 逃生）后下载。
- 只读客户端：不写任何配置、不缓存签名 URL。
"""
from __future__ import annotations

import asyncio
import logging
import os

import outbound_guard
from http_client import build_async_client

logger = logging.getLogger(__name__)

# 生产 COS 桶域名（预检确认后随 C 端发版烘焙）；env KB_STORAGE_HOSTS 可覆盖。
_DEFAULT_STORAGE_HOSTS = (
    "ai-novel-knowledge-1468883265.cos.ap-shanghai.myqcloud.com",
)


def storage_hosts() -> set[str]:
    raw = (os.environ.get("KB_STORAGE_HOSTS") or "").strip()
    if raw:
        return {part.strip().lower() for part in raw.split(",") if part.strip()}
    return {host.lower() for host in _DEFAULT_STORAGE_HOSTS}


def _validate_download(url: str) -> tuple[bool, str]:
    return outbound_guard.validate_outbound(
        url,
        storage_hosts(),
        allow_dev_loopback=True,
        trusted_required=True,
    )


def _has_token() -> bool:
    try:
        from auth_local.service import load_or_create_config

        return bool(str(load_or_create_config().get("token") or "").strip())
    except Exception:  # noqa: BLE001 —— 配置读失败按未登录
        return False


async def sign(
    scope: str,
    *,
    version: int | None = None,
    path: str = "",
    genre: str = "",
) -> dict:
    """S 端 /api/kb/sign 封装；返回 body 信封（code=0 成功，-2=未登录）。"""
    if not _has_token():
        return {"code": -2, "msg": "not_logged_in"}
    body: dict = {"scope": scope}
    if version is not None:
        body["version"] = int(version)
    if path:
        body["path"] = path
    if genre:
        body["genre"] = genre
    try:
        from auth_local.service import call_server_api

        return await call_server_api(
            "kb/sign", method="POST", json_body=body, with_token=True
        )
    except Exception as exc:  # noqa: BLE001 —— 网络/序列化异常统一 sign_error
        logger.warning("event=kb_sign_client_error err=%s", exc)
        return {"code": -1, "msg": "sign_error"}


async def fetch_signed(url: str, max_bytes: int) -> tuple[bytes | None, str]:
    """下载 S 端签发的 COS URL；返回 (bytes|None, verdict)。

    verdict ∈ ok/fakeip/blocked——fakeip 且下载失败时调用方记 proxy_fake_ip
    （与旧 CDN 链路同诊断口径）；blocked 由出站守卫拒绝。
    """
    if not url:
        return None, "blocked"
    try:
        ok, verdict = await asyncio.to_thread(_validate_download, url)
    except Exception:  # noqa: BLE001 —— 解析失败按 blocked
        return None, "blocked"
    if not ok:
        logger.info("event=kb_download_blocked verdict=%s", verdict)
        return None, verdict or "blocked"
    try:
        async with build_async_client(timeout=20.0) as client:
            resp = await client.get(url, follow_redirects=False)
            if resp.status_code != 200 or len(resp.content) > max_bytes:
                return None, verdict
            return resp.content, verdict
    except Exception:  # noqa: BLE001 —— 下载失败＝保持旧层
        return None, verdict
