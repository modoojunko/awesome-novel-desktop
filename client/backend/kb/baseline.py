"""官方基线知识包同步（c-kb-baseline 批A）——overlay 只读 lower 层。

- 官方基线＝只读 lower 层：同步＝整层事务替换（清旧插新＋记 pack_version），
  客户端任何路径 SHALL NOT 对其做单条修改。
- 用户改/藏基线＝upper 层写时复制（kb_baseline_overlays：edit 物化副本/hide whiteout），
  基线原件永不改变；恢复默认＝删覆盖记录。
- 同步挂启动补偿：静默、失败可重试、不阻断启动与写法块（未就绪＝不出现）。
- 信任模型：latest/manifest Ed25519 验签（manifest_crypto 同源）＋manifest sha256
  ＋格式闸（format_client＝按哪代客户端写）＋包体上限＋https/可信域/公网 SSRF 防线。
- 版本口径只有两个：内容包 version（第几版）＋format_client（哪代客户端的结构）；
  条目级向前兼容（读不懂的条目只跳过），整包都不认识才保旧层。
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.app_meta import AppMeta
from models.kb import KbBaselineEntry, KbBaselineOverlay, KbBaselineTag

import outbound_guard

logger = logging.getLogger(__name__)

VERSION_KEY = "kb_baseline_version"
LAST_SYNC_KEY = "kb_baseline_last_sync"
# 包里只有两个版本概念，别再增生：
#   ① 内容包 version（第几版，单调递增，目录不可变）
#   ② format_client＝「这份内容按哪一代客户端的结构写」（boss 拍板：格式随客户端版本走）
# 独立的格式编号与 min_client 字段已裁撤——与客户端版本重复，多一套号迟早漂。
# 新增不兼容代际时：本端把新客户端版本加进 _KNOWN_FORMAT_CLIENTS，内容仓同批登记。
FORMAT_CLIENT = "0.45.0"
_KNOWN_FORMAT_CLIENTS = frozenset({FORMAT_CLIENT})
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


def _validate_outbound(url: str) -> tuple[bool, str]:
    """出站校验单源（outbound_guard）：返回 (放行, verdict)。

    https＋可信域（空 allowlist 放行＝开发态）＋解析判定；http＋环回宿主为本地
    测试逃生口（旧语义逐字保持）。verdict ∈ ok／fakeip（TUN 代理 fake-ip DNS
    全命中，放行）／blocked——fake-ip 环境下的获取失败由调用方记 proxy_fake_ip。
    """
    return outbound_guard.validate_outbound(
        url, _trusted_hosts(), allow_dev_loopback=True, trusted_required=False,
    )


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


def _parse_entries(raw: bytes) -> tuple[list[dict], int, set[str]]:
    """entries.jsonl → (合格条目, 违规计数, 认得出 src_key 的违规条目键)。

    判据集＝`kb.gates.check_baseline_entry`（与内容仓 validate 同集，fixture 双端
    parity）；instruction 归一为 strip 后原文（存储与 content_sha256 同字节口径）；
    src_key 包内重复按违规跳过，不让单条脏数据把整层事务炸掉。

    第三返回值用于「本端读不懂 ≠ 官方下架」：官方仍发布的条目若用了新概念/新维度，
    同步器沿用旧层原文而不是把它当移除（见 `_replace_layer` 的 carried）。
    """
    from kb.gates import check_baseline_entry

    ok: list[dict] = []
    seen: set[str] = set()
    rejected: set[str] = set()
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
            key = e.get("src_key") if isinstance(e, dict) else None
            if isinstance(key, str) and key:
                rejected.add(key)
            continue
        src_key = e["src_key"]
        if src_key in seen:
            bad += 1
            continue
        seen.add(src_key)
        e["instruction"] = e["instruction"].strip()
        ok.append(e)
    return ok, bad, rejected


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


def _format_ok(manifest: dict) -> bool:
    """格式闸：`format_client` 表达「这份内容按哪代客户端写」。

    - 认识的代际 → 收（条目级子集容错另行处理新东西）；
    - 不认识的代际 → 静默跳过，保持旧层；
    - 没有该字段（v1 这类历史包）→ 就是第一代，照收。
    """
    fc = manifest.get("format_client")
    if not isinstance(fc, str) or not fc.strip():
        return True
    return fc.strip() in _KNOWN_FORMAT_CLIENTS


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


def maybe_sync() -> None:
    """登录/校验成功钩子（照 prompt_pack.maybe_after_auth 同构）：缺层才补、已装零外呼。

    早退检查放后台任务体内（登录路径零阻塞）：本地已有版本且层非空 → 不发任何
    网络请求即退；层空/从未同步 → 跑一次同步（静默失败、下次钩子再试）。
    `KB_BASELINE_SYNC=0` 与 `schedule_sync` 共闸（测试态不联网）。
    """
    import asyncio
    import os

    if (os.environ.get("KB_BASELINE_SYNC") or "").strip() == "0":
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_maybe_sync_task())


async def _maybe_sync_task() -> None:
    if await _already_installed():
        return
    await _sync_with_logging()


async def _already_installed() -> bool:
    """已装判定＝app_meta 有版本号且基线层非空（迁移带回后层空也会补同步）。"""
    from sqlalchemy import select

    from db import async_session

    try:
        async with async_session() as db:
            if await _current_version() <= 0:
                return False
            r = await db.execute(select(KbBaselineEntry.entry_id).limit(1))
            return r.first() is not None
    except Exception:  # noqa: BLE001 —— 判定失败按「未装」处理，交给同步幂等兜底
        return False


async def probe_latest() -> dict:
    """只读探测 CDN 最新版本（照 prompt-pack /probe：探测不触发同步）。

    返回 {installed, latest, update_available}；CDN 不可达/验签失败 →
    update_available=False + reason（不抛错、不打扰）。
    """
    import asyncio

    import httpx

    from kb.revocation import is_retired
    from manifest_crypto import verify_manifest

    if await is_retired():
        return {"installed": 0, "latest": 0, "update_available": False, "reason": "retired"}
    installed = await _current_version()
    keys = _trust_keys()
    if not keys:
        return {"installed": installed, "latest": 0, "update_available": False, "reason": "not_configured"}
    async with httpx.AsyncClient() as client:
        verdicts: list[str] = []
        for candidate in _cdn_bases():
            latest_url = _derive(candidate, "latest.json")
            # DNS 解析是同步调用：丢线程，别让慢解析卡住事件循环
            ok, verdict = await asyncio.to_thread(_validate_outbound, latest_url)
            verdicts.append(verdict)
            if not ok:
                continue
            probe = await _fetch_json(client, latest_url)
            if probe is not None and verify_manifest(probe, keys):
                latest = int(probe.get("version") or 0)
                return {
                    "installed": installed,
                    "latest": latest,
                    "update_available": bool(latest and latest != installed),
                }
        reason = "proxy_fake_ip" if "fakeip" in verdicts else "latest_invalid"
        return {"installed": installed, "latest": 0, "update_available": False, "reason": reason}


async def sync_baseline(db: AsyncSession | None = None) -> dict:
    """同步入口（幂等）。返回 {status: synced|current|skipped|failed, ...}。"""
    global _syncing
    from kb.revocation import is_retired

    if await is_retired(db):
        return {"status": "skipped", "reason": "retired"}
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

    from kb.revocation import is_retired
    from manifest_crypto import verify_manifest

    if await is_retired(db):
        return {"status": "skipped", "reason": "retired"}
    keys = _trust_keys()
    if not keys:
        return {"status": "skipped", "reason": "not_configured"}

    async with httpx.AsyncClient() as client:
        # 主域→兜底域逐个探 latest.json（签名有效才算命中；静态托管与更新/提示词包同域）
        base = ""
        latest = None
        sync_verdicts: list[str] = []
        for candidate in _cdn_bases():
            latest_url = _derive(candidate, "latest.json")
            # DNS 解析是同步调用：丢线程，别让慢解析卡住整个事件循环（启动期尤甚）
            ok, verdict = await asyncio.to_thread(_validate_outbound, latest_url)
            sync_verdicts.append(verdict)
            if not ok:
                continue
            probe = await _fetch_json(client, latest_url)
            if probe is not None and verify_manifest(probe, keys):
                base, latest = candidate, probe
                break
        if latest is None:
            reason = "proxy_fake_ip" if "fakeip" in sync_verdicts else "latest_invalid"
            return {"status": "failed", "reason": reason}
        version = int(latest.get("version") or 0)
        current = await _current_version()
        if version and version == current:
            return {"status": "current", "version": current}

        manifest_url = _derive(base, f"v{version}/manifest.json")
        manifest_ok, _v = await asyncio.to_thread(_validate_outbound, manifest_url)
        if not manifest_ok:
            return {"status": "failed", "reason": "unsafe_url"}
        manifest_raw = await _fetch_bytes(client, manifest_url)
        try:
            manifest = json.loads(manifest_raw) if manifest_raw is not None else None
        except ValueError:
            manifest = None
        if not isinstance(manifest, dict) or not verify_manifest(manifest, keys):
            return {"status": "failed", "reason": "manifest_invalid"}
        # 清单内声明优先（latest 是「有没有新版」的门，manifest 是「本包能不能装」的门）
        if not _format_ok(manifest):
            return {"status": "skipped", "reason": "format_newer", "version": version}

        files = {f["path"]: f for f in manifest.get("files", []) if isinstance(f, dict)}
        entries_bytes = await _fetch_bytes(client, _derive(base, f"v{version}/entries.jsonl"))
        if entries_bytes is None or sha256_hex(entries_bytes) != files.get("entries.jsonl", {}).get("sha256"):
            return {"status": "failed", "reason": "entries_hash"}
        entries, skipped, rejected = _parse_entries(entries_bytes)
        # 向前兼容（c-kb-forward-compat）：包里的条目按本端「看得懂的那一子集」落层——
        # 新增概念/新维度的条目由老客户端整条跳过，其余照收，绝不因此整包拒收。
        # 只有「一条都读不懂」才视为代际不兼容，保旧层（免得把用户现有基线清空）。
        expected = manifest.get("entry_count")
        if isinstance(expected, int) and expected > 0 and not entries:
            return {"status": "failed", "reason": "entry_count", "skipped": skipped}
        if skipped:
            logger.warning(
                "event=kb_baseline_partial version=%s accepted=%d skipped=%d "
                "（本端读不懂的条目沿用旧层原文，不当下架）",
                version, len(entries), skipped,
            )

        if db is None:
            from db import async_session as _session

            async with _session() as session:
                return await _replace_layer(
                    session, version, entries, skipped, manifest, rejected
                )
        return await _replace_layer(db, version, entries, skipped, manifest, rejected)


async def _replace_layer(
    db: AsyncSession, version: int, entries: list[dict], skipped: int, manifest: dict,
    rejected: set[str] | None = None,
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
                # v2 条目级字段（c-knowledge-source-align）：基线投影 C 端知识对象形状
                "example": str(e.get("example") or "")[:500],
                "evidence_ch": str(e.get("evidence_ch") or "")[:80],
                "confidence": str(e.get("confidence") or ""),
                "kind": str(e.get("kind") or "")[:20],
                "node_key": str(e.get("node_key") or "")[:60],
                "content_sha256": content_sha(instruction),
                "published_at": published_at,
            }
        )
        for dim, value in _tags_for(e):
            tag_rows.append({"entry_id": entry_id, "dim": dim, "value": value})

    # 「本端读不懂」≠「官方下架」：包内仍发布、只是本端判据不认的条目，沿用旧层原文
    # （不缩水、不触发下架提升）。只有整包里真的没有该 src_key 才算移除。
    carried = 0
    accepted_keys = {e["src_key"] for e in entries}
    for key in sorted(rejected or ()):
        old = old_rows.get(key)
        if old is None or key in accepted_keys:
            continue
        rows.append(
            {
                "entry_id": old.entry_id,
                "src_key": old.src_key,
                "pack_version": old.pack_version,  # 留旧版本号：内容确实来自上一包
                "genre": old.genre,
                "concept": old.concept,
                "title": old.title,
                "instruction": old.instruction,
                "when_json": old.when_json,
                "payload_json": old.payload_json,
                "scope": old.scope,
                "slot": old.slot,
                "content_sha256": old.content_sha256,
                "published_at": old.published_at,
            }
        )
        for dim, value in _tags_for(
            {
                "concept": old.concept, "genre": old.genre,
                "payload": json.loads(old.payload_json or "{}"),
                "when": json.loads(old.when_json or "{}"),
            }
        ):
            tag_rows.append({"entry_id": old.entry_id, "dim": dim, "value": value})
        accepted_keys.add(key)
        carried += 1

    if rows:
        await db.execute(_ins(KbBaselineEntry), rows)
    if tag_rows:
        await db.execute(_ins(KbBaselineTag), tag_rows)

    meta = await db.get(AppMeta, VERSION_KEY)
    if meta is None:
        db.add(AppMeta(key=VERSION_KEY, value=str(version)))
    else:
        meta.value = str(version)
    # 孤儿清理/提升只认「整包里真的没有」：carried（本端读不懂、沿用旧层）仍在架，
    # 不能当移除——否则用户副本会被误提升成「官方精选（已下架）」自有条目。
    new_keys = set(accepted_keys)
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
    # 最近一次同步摘要（状态端点透出）：让「部分接受」可被看见，而不是只躺在日志里。
    # accepted＝入闸条目数（不含 carried），entries＋carried＋…对得上包 entry_count。
    summary = {
        "at": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
        "version": version, "accepted": len(entries),
        "skipped": skipped, "carried": carried, "promoted": promoted,
    }
    last = await db.get(AppMeta, LAST_SYNC_KEY)
    if last is None:
        db.add(AppMeta(key=LAST_SYNC_KEY, value=json.dumps(summary, ensure_ascii=False)))
    else:
        last.value = json.dumps(summary, ensure_ascii=False)
    await db.commit()
    return {
        "status": "synced",
        "version": version,
        "entries": len(rows),  # 层内条目数＝accepted＋carried（沿用件也是层的一员）
        "tags": len(tag_rows),
        "skipped": skipped,
        "carried": carried,
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
