"""官方基线知识包同步（c-kb-baseline 批A）——overlay 只读 lower 层。

- 官方基线＝只读 lower 层：同步＝整层事务替换（清旧插新＋记 pack_version），
  客户端任何路径 SHALL NOT 对其做单条修改。
- 用户改/藏基线＝upper 层写时复制（kb_baseline_overlays：edit 物化副本/hide whiteout），
  基线原件永不改变；恢复默认＝删覆盖记录。
- 同步挂启动补偿：静默、失败可重试、不阻断启动与写法块（未就绪＝不出现）。
- 信任模型：latest/manifest Ed25519 验签（manifest_crypto 同源）＋manifest sha256
  ＋format_version 闸＋包体上限＋https/可信域/公网 SSRF 防线（照 prompt_pack）。
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import socket
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.app_meta import AppMeta
from models.kb import KbBaselineEntry, KbBaselineOverlay, KbBaselineTag

logger = logging.getLogger(__name__)

VERSION_KEY = "kb_baseline_version"
SUPPORTED_FORMAT_VERSION = 1
_MAX_PACK_BYTES = 16 * 1024 * 1024
_FETCH_TIMEOUT = 8.0
_DEFAULT_CDN_BASE = ""  # CDN 接入后烘焙；未配置＝同步静默跳过（库空写法块不出现，同级降级）

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ai-novel/kb-baseline")
_TRUST_PUBKEYS: dict[str, bytes] = {}  # {kid: base64(32B raw)}——打包期烘焙（同 CLIENT_PACK_PUBKEYS 先例）

_syncing = False


def proxy_id(src_key: str) -> str:
    """基线条目确定性代理主键：uuid5(NS, src_key)——跨包/跨设备/跨备份恢复稳定。"""
    return str(uuid.uuid5(_NS, src_key))


def _cdn_base() -> str:
    import os

    return (os.environ.get("KNOWLEDGE_CDN_BASE") or _DEFAULT_CDN_BASE).strip().rstrip("/")


def _trusted_hosts() -> set[str]:
    base = _cdn_base()
    return {urlparse(base).hostname.lower()} if base and urlparse(base).hostname else set()


def _validate_outbound(url: str) -> bool:
    """https＋可信域＋解析结果全公网（照 prompt_pack sync 同款防线）。"""
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        if p.scheme == "https":
            pass  # https 一律放行进域校验
        elif p.scheme == "http" and host in ("127.0.0.1", "localhost"):
            pass  # 本地测试
        else:
            return False
        trusted = _trusted_hosts()
        if trusted and host not in trusted:
            return False
        infos = socket.getaddrinfo(p.hostname, 443, proto=socket.IPPROTO_TCP)
    except (OSError, ValueError):
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global and host not in ("127.0.0.1", "localhost"):
            return False
    return True


def _derive(base: str, name: str) -> str:
    p = urlparse(base)
    return f"{p.scheme}://{p.netloc}{p.path.rsplit('/', 1)[0]}/{name}"


async def _fetch_json(client, url: str) -> dict | None:

    try:
        r = await client.get(url, timeout=_FETCH_TIMEOUT, follow_redirects=False)
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


async def _fetch_bytes(client, url: str) -> bytes | None:

    try:
        r = await client.get(url, timeout=_FETCH_TIMEOUT, follow_redirects=False)
        if r.status_code != 200 or len(r.content) > _MAX_PACK_BYTES:
            return None
        return r.content
    except Exception:  # noqa: BLE001
        return None


def _parse_entries(raw: bytes) -> tuple[list[dict], int]:
    """entries.jsonl → (合格条目, 违规跳过计数)。同步端逐条复验（闸门子集）。"""
    ok: list[dict] = []
    bad = 0
    for raw_line in raw.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            bad += 1
            continue
        src_key = str(e.get("src_key") or "")
        ins = str(e.get("instruction") or "").strip()
        if not src_key.startswith("baseline:") or "\n" in ins or not (6 <= len(ins) <= 240):
            bad += 1
            continue
        if "【本章写法指引】" in ins:
            bad += 1
            continue
        ok.append(e)
    return ok, bad


def _tags_for(e: dict) -> list[tuple[str, str]]:
    tags = [("concept", str(e.get("concept") or "")), ("genre", str(e.get("genre") or ""))]
    payload = e.get("payload") or {}
    slot = str(payload.get("slot") or "")
    if slot:
        tags.append(("slot", slot))
    when = e.get("when") or {}
    if when:
        tags.append(("scope", "scene"))
        for k in ("scene", "emotion", "chapter_pos"):
            if when.get(k):
                tags.append((k, str(when[k])))
    else:
        tags.append(("scope", "base"))
    return [(d, v) for d, v in tags if v]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def schedule_sync() -> None:
    """启动补偿：后台任务执行同步（CDN 等待不挡启动）；无事件循环＝静默跳过。"""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_sync_with_logging())


async def _sync_with_logging() -> None:
    result = await sync_baseline()
    if result.get("status") in ("synced", "failed"):
        logger.info("event=kb_baseline_sync %s", json.dumps(result, ensure_ascii=False))


async def sync_baseline(db: AsyncSession | None = None) -> dict:
    """同步入口（幂等）。返回 {status: synced|current|skipped|failed, ...}。"""
    global _syncing
    if _syncing:
        return {"status": "skipped", "reason": "syncing"}
    _syncing = True
    try:
        return await _sync_impl(db)
    except Exception:  # noqa: BLE001 — 任何异常＝保持旧层，静默可重试
        logger.warning("event=kb_baseline_sync_failed", exc_info=True)
        return {"status": "failed"}
    finally:
        _syncing = False


async def _sync_impl(db: AsyncSession | None) -> dict:
    import httpx

    from manifest_crypto import verify_manifest

    base = _cdn_base()
    if not base or not _TRUST_PUBKEYS:
        return {"status": "skipped", "reason": "not_configured"}

    async with httpx.AsyncClient() as client:
        latest_url = _derive(base, "latest.json")
        if not _validate_outbound(latest_url):
            return {"status": "failed", "reason": "unsafe_url"}
        latest = await _fetch_json(client, latest_url)
        if latest is None or not verify_manifest(latest, _TRUST_PUBKEYS):
            return {"status": "failed", "reason": "latest_invalid"}
        version = int(latest.get("version") or 0)
        current = await _current_version()
        if version and version == current:
            return {"status": "current", "version": current}

        manifest_url = _derive(base, f"v{version}/manifest.json")
        if not _validate_outbound(manifest_url):
            return {"status": "failed", "reason": "unsafe_url"}
        manifest_raw = await _fetch_bytes(client, manifest_url)
        if manifest_raw is None or not verify_manifest(json.loads(manifest_raw), _TRUST_PUBKEYS):
            return {"status": "failed", "reason": "manifest_invalid"}
        manifest = json.loads(manifest_raw)
        fmt = int(manifest.get("format_version") or 0)
        if fmt > SUPPORTED_FORMAT_VERSION:
            return {"status": "skipped", "reason": "format_newer", "version": version}

        files = {f["path"]: f for f in manifest.get("files", []) if isinstance(f, dict)}
        entries_bytes = await _fetch_bytes(client, _derive(base, f"v{version}/entries.jsonl"))
        if entries_bytes is None or sha256_hex(entries_bytes) != files.get("entries.jsonl", {}).get("sha256"):
            return {"status": "failed", "reason": "entries_hash"}
        entries, skipped = _parse_entries(entries_bytes)
        if len(entries) != manifest.get("entry_count"):
            return {"status": "failed", "reason": "entry_count"}

        if db is None:
            from db import async_session as _session

            async with _session() as session:
                return await _replace_layer(session, version, entries, skipped, manifest)
        return await _replace_layer(db, version, entries, skipped, manifest)


async def _replace_layer(
    db: AsyncSession, version: int, entries: list[dict], skipped: int, manifest: dict
) -> dict:
    from sqlalchemy import delete as _del
    from sqlalchemy import insert as _ins

    await db.execute(_del(KbBaselineTag))
    await db.execute(_del(KbBaselineEntry))
    published = str(manifest.get("generated_at") or "")
    try:
        published_at = datetime.fromisoformat(published)
    except (ValueError, TypeError):
        published_at = datetime.now(UTC).replace(tzinfo=None)
    for e in entries:
        src_key = e["src_key"]
        entry_id = proxy_id(src_key)
        when = e.get("when") or {}
        db.execute(
            _ins(KbBaselineEntry).values(
                entry_id=entry_id,
                src_key=src_key,
                pack_version=version,
                genre=str(e.get("genre") or ""),
                concept=str(e.get("concept") or ""),
                title=str(e.get("title") or "")[:40],
                instruction=str(e.get("instruction") or ""),
                when_json=json.dumps(when or {}, ensure_ascii=False),
                payload_json=json.dumps(e.get("payload") or {}, ensure_ascii=False),
                scope="scene" if when else "base",
                slot=str((e.get("payload") or {}).get("slot") or ""),
                content_sha256=hashlib.sha256(
                    str(e.get("instruction") or "").encode("utf-8")
                ).hexdigest(),
                published_at=published_at,
            )
        )
        for dim, value in _tags_for(e):
            db.execute(_ins(KbBaselineTag).values(entry_id=entry_id, dim=dim, value=value))
    meta = await db.get(AppMeta, VERSION_KEY)
    if meta is None:
        db.add(AppMeta(key=VERSION_KEY, value=str(version)))
    else:
        meta.value = str(version)
    # hide 孤儿清理（src_key 不在新包）——edit 副本保留（用户资产）
    new_keys = {e["src_key"] for e in entries}
    overlays = (
        await db.execute(select(KbBaselineOverlay).where(KbBaselineOverlay.action == "hide"))
    ).scalars().all()
    for ov in overlays:
        if ov.src_key not in new_keys:
            await db.delete(ov)
    await db.commit()
    return {"status": "synced", "version": version, "entries": len(entries), "skipped": skipped}


async def _current_version() -> int:
    from db import async_session

    try:
        async with async_session() as db:
            meta = await db.get(AppMeta, VERSION_KEY)
            return int(meta.value) if meta else 0
    except Exception:  # noqa: BLE001
        return 0
