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
_DEFAULT_CDN_BASE = "https://www.awesomenovel.com/knowledge/baseline"
_DEFAULT_CDN_BASE_FALLBACK = (
    "https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/knowledge/baseline"
)

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ai-novel/kb-baseline")
# {kid: 32B raw}——非空即优先（测试/联调注入）；否则 CLIENT_KB_PUBKEYS →
# CLIENT_PACK_PUBKEYS（**与提示词包共用 pack-k1 同一把钥**）→ 生产默认。
_TRUST_PUBKEYS: dict[str, bytes] = {}
_PROD_PUBKEYS_JSON = '{"pack-k1":"UaJFasM5PBIB3Tg1o03cjG6Opeq5CaKtPv2ooLyNPPM="}'

_syncing = False


def proxy_id(src_key: str) -> str:
    """基线条目确定性代理主键：uuid5(NS, src_key)——跨包/跨设备/跨备份恢复稳定。"""
    return str(uuid.uuid5(_NS, src_key))


def _cdn_base() -> str:
    import os

    return (os.environ.get("KNOWLEDGE_CDN_BASE") or _DEFAULT_CDN_BASE).strip().rstrip("/")


def _cdn_bases() -> list[str]:
    """主域→兜底域（与 prompt_pack/update_check 同源模式）；env 覆盖时只走覆盖值。"""
    import os

    if (os.environ.get("KNOWLEDGE_CDN_BASE") or "").strip():
        return [_cdn_base()]
    out = [_cdn_base()]
    fb = _DEFAULT_CDN_BASE_FALLBACK.strip().rstrip("/")
    if fb and fb != out[0]:
        out.append(fb)
    return out


def _trust_keys() -> dict[str, bytes]:
    import base64
    import os

    if _TRUST_PUBKEYS:
        return _TRUST_PUBKEYS
    for name in ("CLIENT_KB_PUBKEYS", "CLIENT_PACK_PUBKEYS"):
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            keys = {str(k): base64.b64decode(str(v)) for k, v in parsed.items()}
        except (ValueError, TypeError, AttributeError):
            continue
        if keys and all(len(v) == 32 for v in keys.values()):
            return keys
    try:
        parsed = json.loads(_PROD_PUBKEYS_JSON)
        return {str(k): base64.b64decode(str(v)) for k, v in parsed.items()}
    except (ValueError, TypeError):
        return {}


def _trusted_hosts() -> set[str]:
    hosts = set()
    for base in _cdn_bases():
        host = urlparse(base).hostname
        if host:
            hosts.add(host.lower())
    return hosts


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
    """基址即发布目录（…/knowledge/baseline）：latest 与 vN/ 同级（与内容仓
    publish 落盘布局一致；不采信 manifest 里出现的任何 URL）。"""
    p = urlparse(base)
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}/{name}"


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
    """entries.jsonl → (合格条目, 违规跳过计数)。同步端逐条复验。

    判据集＝`kb.gates.check_baseline_entry`（与内容仓 validate 同集，fixture 双端
    parity）；instruction 归一为 strip 后原文（存储与 content_sha256 同字节口径）；
    src_key 包内重复按违规跳过，不让单条脏数据把整层事务炸掉。
    """
    from kb.gates import check_baseline_entry

    ok: list[dict] = []
    seen: set[str] = set()
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
        if check_baseline_entry(e) is not None:
            bad += 1
            continue
        src_key = e["src_key"]
        if src_key in seen:
            bad += 1
            continue
        seen.add(src_key)
        e["instruction"] = e["instruction"].strip()
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


def content_sha(instruction: str) -> str:
    """条目内容指纹（双哈希之一）——与 overlay.base_content_sha256 同一口径。

    D0-7：同步时对原文算 content_sha256；edit 物化时对当时原件算
    base_content_sha256；读时两值不等＝「官方有新版」。口径必须与同步端逐字节
    一致（strip 后 UTF-8），否则每次同步都会误报新版本。
    """
    return hashlib.sha256((instruction or "").strip().encode("utf-8")).hexdigest()


def _too_old(min_client: object) -> bool:
    """min_client_version 闸：新包＋旧客户端＝静默跳过（保持旧层）。dev 不拦。"""
    from schema_version import app_version, is_newer

    cur = app_version()
    if not isinstance(min_client, str) or not min_client or cur in ("dev", "", None):
        return False
    try:
        return bool(is_newer(min_client, cur))
    except Exception:  # noqa: BLE001 — 版本串非法＝不拦（交由验签/格式闸兜底）
        return False


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

    keys = _trust_keys()
    if not keys:
        return {"status": "skipped", "reason": "not_configured"}

    async with httpx.AsyncClient() as client:
        # 主域→兜底域逐个探 latest.json（签名有效才算命中；静态托管与更新/提示词包同域）
        base = ""
        latest = None
        for candidate in _cdn_bases():
            latest_url = _derive(candidate, "latest.json")
            if not _validate_outbound(latest_url):
                continue
            probe = await _fetch_json(client, latest_url)
            if probe is not None and verify_manifest(probe, keys):
                base, latest = candidate, probe
                break
        if latest is None:
            return {"status": "failed", "reason": "latest_invalid"}
        version = int(latest.get("version") or 0)
        if _too_old(latest.get("min_client_version")):
            return {"status": "skipped", "reason": "min_client_version", "version": version}
        current = await _current_version()
        if version and version == current:
            return {"status": "current", "version": current}

        manifest_url = _derive(base, f"v{version}/manifest.json")
        if not _validate_outbound(manifest_url):
            return {"status": "failed", "reason": "unsafe_url"}
        manifest_raw = await _fetch_bytes(client, manifest_url)
        try:
            manifest = json.loads(manifest_raw) if manifest_raw is not None else None
        except ValueError:
            manifest = None
        if not isinstance(manifest, dict) or not verify_manifest(manifest, keys):
            return {"status": "failed", "reason": "manifest_invalid"}
        # 清单内声明优先（latest 是「有没有新版」的门，manifest 是「本包能不能装」的门）
        if _too_old(manifest.get("min_client_version")):
            return {"status": "skipped", "reason": "min_client_version", "version": version}
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

    # 整层替换＝单事务：留档旧层（下架孤儿提升要用）→ 清旧层 → 批插条目/标签 →
    # 记 pack_version → 清孤儿 hide → 提升孤儿 edit。中途任何异常都不 commit，
    # 会话关闭即回滚（旧层原样）。
    old_rows = {
        r.src_key: r
        for r in (await db.execute(select(KbBaselineEntry))).scalars().all()
    }
    await db.execute(_del(KbBaselineTag))
    await db.execute(_del(KbBaselineEntry))
    published = str(manifest.get("generated_at") or "")
    try:
        published_at = datetime.fromisoformat(published)
    except (ValueError, TypeError):
        published_at = datetime.now(UTC).replace(tzinfo=None)

    rows: list[dict] = []
    tag_rows: list[dict] = []
    for e in entries:
        src_key = e["src_key"]
        entry_id = proxy_id(src_key)
        when = e.get("when") or {}
        instruction = str(e.get("instruction") or "")
        payload = e.get("payload") or {}
        rows.append(
            {
                "entry_id": entry_id,
                "src_key": src_key,
                "pack_version": version,
                "genre": str(e.get("genre") or ""),
                "concept": str(e.get("concept") or ""),
                "title": str(e.get("title") or "")[:40],
                "instruction": instruction,
                "when_json": json.dumps(when, ensure_ascii=False),
                "payload_json": json.dumps(payload, ensure_ascii=False),
                "scope": "scene" if when else "base",
                "slot": str(payload.get("slot") or ""),
                "content_sha256": content_sha(instruction),
                "published_at": published_at,
            }
        )
        for dim, value in _tags_for(e):
            tag_rows.append({"entry_id": entry_id, "dim": dim, "value": value})
    if rows:
        await db.execute(_ins(KbBaselineEntry), rows)
    if tag_rows:
        await db.execute(_ins(KbBaselineTag), tag_rows)

    meta = await db.get(AppMeta, VERSION_KEY)
    if meta is None:
        db.add(AppMeta(key=VERSION_KEY, value=str(version)))
    else:
        meta.value = str(version)
    # hide 孤儿清理（src_key 不在新包）；edit 孤儿提升为用户自有条目（D0-6）
    new_keys = {e["src_key"] for e in entries}
    overlays = (await db.execute(select(KbBaselineOverlay))).scalars().all()
    promoted = 0
    for ov in overlays:
        if ov.src_key in new_keys:
            continue
        if ov.action == "hide":
            await db.delete(ov)  # 下架条目的 hide 记录已无意义
            continue
        # edit 副本＝用户的话，官方下架不得蒸发：提升为账号自有条目后删覆盖
        old = old_rows.get(ov.src_key)
        if old is None:
            continue  # 旧层本来就没有这条（跨两版下架）：覆盖留着，不臆造条目
        await _promote_overlay(db, ov, old)
        await db.delete(ov)
        promoted += 1
    await db.commit()
    return {
        "status": "synced",
        "version": version,
        "entries": len(rows),
        "tags": len(tag_rows),
        "skipped": skipped,
        "promoted": promoted,
    }


async def _promote_overlay(
    db: AsyncSession, ov: KbBaselineOverlay, old: KbBaselineEntry
) -> None:
    """孤儿 edit 副本 → 用户自有条目（D0-6：写时复制的副本本就是用户的话）。

    src_kind SHALL NOT 落 "baseline"（delta 硬约束）——提升件记 manual，
    来源信息留在 src_novel_name；标签索引同事务物化（选择器读标签不扫 JSON）。
    """
    from sqlalchemy import insert as _ins

    from kb.service import _tags_for  # 物化标签单源（与手录/导入同口径）
    from models.kb import KbEntry, KbEntryTag

    text = (ov.content or "").strip() or (old.instruction or "")
    if not text:
        return
    try:
        payload = json.loads(old.payload_json or "{}")
        when = json.loads(old.when_json or "{}")
    except ValueError:
        payload, when = {}, {}
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(when, dict):
        when = {}

    entry = KbEntry(
        user_id=ov.user_id,
        genre=old.genre or "",
        concept=old.concept or "",
        concept_id=f"{old.genre}:{old.concept}",
        title=(old.title or "")[:40],
        payload_json=json.dumps(payload, ensure_ascii=False),
        instruction=text,
        when_json=json.dumps(when, ensure_ascii=False),
        status="active",
        src_kind="manual",
        src_ref="",
        src_key="",
        src_novel_name="官方精选（已下架）",
    )
    db.add(entry)
    await db.flush()
    tag_rows = [
        {"entry_id": entry.id, "user_id": ov.user_id, "dim": dim, "value": value}
        for dim, value in _tags_for(entry, payload, when)
    ]
    if tag_rows:
        await db.execute(_ins(KbEntryTag), tag_rows)


async def _current_version() -> int:
    from db import async_session

    try:
        async with async_session() as db:
            meta = await db.get(AppMeta, VERSION_KEY)
            return int(meta.value) if meta else 0
    except Exception:  # noqa: BLE001
        return 0
