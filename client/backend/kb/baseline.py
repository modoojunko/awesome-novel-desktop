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
# 格式代＝**引入它的客户端版本**（boss 拍板：格式随客户端版本走）。新增不兼容代际时
# 加一行映射（如 "0.50.0": 2）并把 SUPPORTED_FORMAT_VERSION 抬到该代；整数只是给
# 只认整数的老包/老读法用的等价编码，不是独立的编号体系。
FORMAT_CLIENT = "0.45.0"
_FORMAT_INT_BY_CLIENT = {FORMAT_CLIENT: 1}
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


def _format_ok(manifest: dict) -> bool:
    """格式闸：**格式代以客户端版本表达**（format_client），整数是等价老读法。

    - 新包（build 双写）：`format_client` 命中本端映射 → 等价整数比大小；
      映射里没有＝比本端更新的代际 → 不认识，静默跳过保旧层。
    - 老包（v1 已发，只有 `format_version`）：按整数比。
    """
    fc = manifest.get("format_client")
    if isinstance(fc, str) and fc.strip():
        mapped = _FORMAT_INT_BY_CLIENT.get(fc.strip())
        return mapped is not None and mapped <= SUPPORTED_FORMAT_VERSION
    try:
        return int(manifest.get("format_version") or 0) <= SUPPORTED_FORMAT_VERSION
    except (TypeError, ValueError):
        return False


def schedule_sync() -> None:
    """启动补偿：后台任务执行同步（CDN 等待不挡启动）；无事件循环＝静默跳过。

    `KB_BASELINE_SYNC=0` 关闭（测试/诊断用）：lifespan 在测试进程里也会跑，
    不关掉就会真联网并抢共享 SQLite 写锁（CI 实锤 database is locked）。
    手动 `sync_baseline()` 不受此闸影响。
    """
    import asyncio
    import os

    if (os.environ.get("KB_BASELINE_SYNC") or "").strip() == "0":
        return
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
    import asyncio

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
            # DNS 解析是同步调用：丢线程，别让慢解析卡住整个事件循环（启动期尤甚）
            if not await asyncio.to_thread(_validate_outbound, latest_url):
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
        if not await asyncio.to_thread(_validate_outbound, manifest_url):
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
        if not _format_ok(manifest):
            return {"status": "skipped", "reason": "format_newer", "version": version}

        files = {f["path"]: f for f in manifest.get("files", []) if isinstance(f, dict)}
        entries_bytes = await _fetch_bytes(client, _derive(base, f"v{version}/entries.jsonl"))
        if entries_bytes is None or sha256_hex(entries_bytes) != files.get("entries.jsonl", {}).get("sha256"):
            return {"status": "failed", "reason": "entries_hash"}
        entries, skipped = _parse_entries(entries_bytes)
        # 向前兼容（c-kb-forward-compat）：包里的条目按本端「看得懂的那一子集」落层——
        # 新增概念/新维度的条目由老客户端整条跳过，其余照收，绝不因此整包拒收。
        # 只有「一条都读不懂」才视为代际不兼容，保旧层（免得把用户现有基线清空）。
        expected = manifest.get("entry_count")
        if isinstance(expected, int) and expected > 0 and not entries:
            return {"status": "failed", "reason": "entry_count", "skipped": skipped}

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
            # 下架条目的 hide 记录：无副本正文＝已无意义，删；有正文＝用户写过的
            # 话，保留（再上架时仍可还原，符合 D1「edit→hide 保留 content」）
            if (ov.content or "").strip():
                continue
            await db.delete(ov)
            continue
        # edit 副本＝用户的话，官方下架不得蒸发：提升为账号自有条目后删覆盖
        old = old_rows.get(ov.src_key)
        if old is None:
            continue  # 旧层本来就没有这条（跨两版下架）：覆盖留着，不臆造条目
        existing = await find_promoted_copy(db, user_id=ov.user_id, src_key=ov.src_key)
        if existing is not None and getattr(existing, "status", "active") == "active":
            # 已有「在用」的提升副本（导入/前一轮下架留下的）：原地更新为用户最新正文，
            # 不再新建第二份（提升件无唯一约束，不查就重复）。archive 副本不算——
            # 用户删过的不可见，本次下架应重新提升一份 active 的
            text = (ov.content or "").strip()
            if text:
                existing.instruction = text
            await db.delete(ov)
            promoted += 1
            continue
        await _promote_overlay(db, ov, old)
        await db.delete(ov)
        promoted += 1
    # 只在「本次重新上架」的迁移上补 hide（new_keys − old_rows）：否则每次版本升级都会
    # 把用户手动「恢复官方版」后的状态再盖回去（用户选择必须胜过一次性去重）
    readded = new_keys - set(old_rows)
    await _hide_radded_promoted(db, readded)
    await db.commit()
    return {
        "status": "synced",
        "version": version,
        "entries": len(rows),
        "tags": len(tag_rows),
        "skipped": skipped,
        "promoted": promoted,
    }


_PROMOTED_SRC = "官方精选（已下架）"


def _promoted_key(row) -> str:
    """提升件的溯源键（evidence_json.promoted_from）——两处判定共用单源。"""
    try:
        return str(json.loads(row.evidence_json or "{}").get("promoted_from") or "")
    except ValueError:
        return ""


async def find_promoted_copy(
    db: AsyncSession, *, user_id: str, src_key: str
) -> object | None:
    """按溯源标记找该用户的「提升副本」（导入/再同步的幂等键）。

    提升件没有天然唯一约束（src_ref='' 不进 uq_kb_entries_src），只能靠
    evidence_json.promoted_from 认亲；重复导入同一包不得再建一份。
    """
    from models.kb import KbEntry

    rows = (
        await db.execute(
            select(KbEntry).where(
                KbEntry.user_id == user_id,
                KbEntry.src_novel_name == _PROMOTED_SRC,
            )
        )
    ).scalars().all()
    for r in rows:
        if _promoted_key(r) == src_key:
            return r
    return None


async def _hide_radded_promoted(db: AsyncSession, readded: set[str]) -> None:
    """回退/重新上架去重：官方条目复活而用户已有「提升副本」时，给该用户补 hide。

    否则 merged 视图会同时出现「用户副本」与「复活的原件」两份近乎相同的内容。
    `readded` 只含「本次从无到有」的 src_key——版本升级里一直存在的条目不再处理，
    用户手动「恢复官方版」（删 hide）后的选择因此不会被下一次升级覆盖。
    """
    from models.kb import KbEntry

    rows = (
        await db.execute(select(KbEntry).where(KbEntry.src_novel_name == _PROMOTED_SRC))
    ).scalars().all()
    if not rows:
        return
    existing = {
        (o.user_id, o.src_key)
        for o in (await db.execute(select(KbBaselineOverlay))).scalars().all()
    }
    for row in rows:
        key = _promoted_key(row)
        if not key or key not in readded or (row.user_id, key) in existing:
            continue
        db.add(
            KbBaselineOverlay(
                user_id=row.user_id, src_key=key, action="hide", content="",
                base_content_sha256="",
            )
        )
        existing.add((row.user_id, key))


async def _promote_overlay(
    db: AsyncSession, ov: KbBaselineOverlay, old: KbBaselineEntry
) -> None:
    """孤儿 edit 副本 → 用户自有条目（D0-6：写时复制的副本本就是用户的话）。

    src_kind SHALL NOT 落 "baseline"（delta 硬约束）——提升件记 manual，
    来源信息留在 src_novel_name；标签索引同事务物化（选择器读标签不扫 JSON）。
    """
    await promote_overlay_copy(
        db,
        user_id=ov.user_id,
        src_key=old.src_key,
        content=ov.content or "",
        meta={
            "genre": old.genre, "concept": old.concept, "title": old.title,
            "payload_json": old.payload_json, "when_json": old.when_json,
            "instruction": old.instruction,
        },
    )


async def promote_overlay_copy(
    db: AsyncSession, *, user_id: str, src_key: str, content: str, meta: dict
) -> bool:
    """孤儿 edit 副本 → 账号自有条目（同步下架与备份恢复共用单源）。

    meta 来自旧层行（同步路径）或备份包 enrichment（导入路径）；两处必须同形状。
    """
    from sqlalchemy import insert as _ins

    from kb.service import _tags_for  # 物化标签单源（与手录/导入同口径）
    from models.kb import KbEntry, KbEntryTag

    text = (content or "").strip() or str(meta.get("instruction") or "").strip()
    if not text:
        return False
    try:
        payload = json.loads(str(meta.get("payload_json") or "{}"))
        when = json.loads(str(meta.get("when_json") or "{}"))
    except ValueError:
        payload, when = {}, {}
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(when, dict):
        when = {}

    genre = str(meta.get("genre") or "")
    concept = str(meta.get("concept") or "")
    entry = KbEntry(
        user_id=user_id,
        genre=genre,
        concept=concept,
        concept_id=f"{genre}:{concept}",
        title=(str(meta.get("title") or ""))[:40],
        payload_json=json.dumps(payload, ensure_ascii=False),
        instruction=text,
        when_json=json.dumps(when, ensure_ascii=False),
        status="active",
        src_kind="manual",
        src_ref="",
        src_key="",
        src_novel_name=_PROMOTED_SRC,
        # 溯源：原文 src_key（回退/再上架时据此给对方账号补 hide，防两份重复）
        evidence_json=json.dumps({"promoted_from": src_key}, ensure_ascii=False),
    )
    db.add(entry)
    await db.flush()
    tag_rows = [
        {"entry_id": entry.id, "user_id": user_id, "dim": dim, "value": value}
        for dim, value in _tags_for(entry, payload, when)
    ]
    if tag_rows:
        await db.execute(_ins(KbEntryTag), tag_rows)
    return True


async def _current_version() -> int:
    from db import async_session

    try:
        async with async_session() as db:
            meta = await db.get(AppMeta, VERSION_KEY)
            return int(meta.value) if meta else 0
    except Exception:  # noqa: BLE001
        return 0
