"""官方基线知识包同步（按题材）——s-kb-signed-delivery。

- 分发：C 端向 S 端 `/api/kb/sign` 换 **COS 私有桶短时 URL**；不再走公开 CDN。
- 一个 release/一份签名 manifest；每个题材的数据是一个独立对象
  （`baseline/v{N}/genres/<slug>.jsonl`）。**每次只同步一个题材**，只替换该题材的
  只读 lower 层；其他题材与用户 overlay 原样保留。
- 配额：题材同步由用户手动触发（知识库页/写作提示）；S 端按档位每日限次；
  pointer/manifest 探测免费；启动/登录/周期复查只刷指针，绝不静默扣额度。
- 用户改/藏基线＝upper 层写时复制（kb_baseline_overlays），基线原件永不改变。
- 信任模型：pointer/manifest Ed25519 验签（manifest_crypto）＋manifest sha256＋
  `format_client` 格式闸＋题材文件 sha256/size＋出站守卫（COS 桶域白名单）。
- 撤回恢复：`latest.json` 的 `resume_baseline=true` 是 S 端/内容仓的显式放行；
  只有带该标记才清 `kb_baseline_retired`，清后仍需用户选题材。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete as _del
from sqlalchemy import insert as _ins
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kb import server_api
from models.app_meta import AppMeta
from models.kb import KbBaselineEntry, KbBaselineOverlay, KbBaselineTag

logger = logging.getLogger(__name__)

VERSION_KEY = "kb_baseline_version"
LAST_SYNC_KEY = "kb_baseline_last_sync"
GENRES_KEY = "kb_baseline_genres"
RETIRED_KEY = "kb_baseline_retired"

# 版本口径只有两个：内容包 version ＋ format_client（按哪代客户端写）。
FORMAT_CLIENT = "0.45.0"
_KNOWN_FORMAT_CLIENTS = frozenset({FORMAT_CLIENT})
_MAX_PACK_BYTES = 16 * 1024 * 1024
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_POINTER_BYTES = 64 * 1024

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ai-novel/kb-baseline")
# {kid: 32B raw}——测试注入优先；否则 CLIENT_KB_PUBKEYS → CLIENT_PACK_PUBKEYS → 生产默认。
_TRUST_PUBKEYS: dict[str, bytes] = {}
_PROD_PUBKEYS_JSON = '{"pack-k1":"UaJFasM5PBIB3Tg1o03cjG6Opeq5CaKtPv2ooLyNPPM="}'

_syncing = False

# 这些 reason 属于网络/内容失败；其余（未登录/档位/配额/格式/撤回）是正常跳过。
_FAILED_REASONS = frozenset(
    {
        "s_unreachable",
        "pointer_fetch",
        "manifest_fetch",
        "pointer_invalid",
        "manifest_invalid",
        "manifest_hash",
        "manifest_version",
        "manifest_genres",
        "proxy_fake_ip",
    }
)


def proxy_id(src_key: str) -> str:
    """基线条目确定性代理主键：uuid5(NS, src_key)。"""
    return str(uuid.uuid5(_NS, src_key))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_sha(instruction: str) -> str:
    """条目内容指纹（与 overlay.base_content_sha256 同一口径）。"""
    return hashlib.sha256((instruction or "").strip().encode("utf-8")).hexdigest()


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


def _format_ok(manifest: dict) -> bool:
    fc = manifest.get("format_client")
    if not isinstance(fc, str) or not fc.strip():
        return True
    return fc.strip() in _KNOWN_FORMAT_CLIENTS


def _reason_from_code(code: object) -> str:
    try:
        value = int(code)
    except (TypeError, ValueError):
        value = -1
    return {
        401: "not_logged_in",
        -2: "not_logged_in",
        403: "tier_denied",
        429: "quota_exceeded",
        400: "bad_request",
        -1: "s_unreachable",
    }.get(value, "s_unreachable")


def _parse_entries(raw: bytes) -> tuple[list[dict], int, set[str]]:
    """题材 jsonl → (合格条目, 违规计数, 认得出 src_key 的违规条目键)。"""
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


# ── 每题材状态（AppMeta JSON）─────────────────────────────────────────────


async def _genre_states(db: AsyncSession | None = None) -> dict:
    from db import async_session

    async def _read(session: AsyncSession) -> dict:
        row = await session.get(AppMeta, GENRES_KEY)
        try:
            data = json.loads(row.value) if row and row.value else {}
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    if db is not None:
        return await _read(db)
    try:
        async with async_session() as session:
            return await _read(session)
    except Exception:  # noqa: BLE001 —— 状态读失败按未同步
        return {}


async def genre_states() -> dict:
    """给 API/前端读的按题材已同步状态快照。"""
    return await _genre_states()


async def _save_genre_states(db: AsyncSession, states: dict) -> None:
    value = json.dumps(states, ensure_ascii=False, sort_keys=True)
    row = await db.get(AppMeta, GENRES_KEY)
    if row is None:
        db.add(AppMeta(key=GENRES_KEY, value=value))
    else:
        row.value = value


def _max_version(states: dict) -> int:
    versions = [
        int(v.get("version") or 0)
        for v in states.values()
        if isinstance(v, dict)
    ]
    return max(versions) if versions else 0


async def _current_version() -> int:
    states = await _genre_states()
    version = _max_version(states)
    if version:
        return version
    from db import async_session

    try:
        async with async_session() as db:
            row = await db.get(AppMeta, VERSION_KEY)
            return int(row.value) if row and str(row.value).isdigit() else 0
    except Exception:  # noqa: BLE001
        return 0


async def _already_installed() -> bool:
    states = await _genre_states()
    return any(int(v.get("version") or 0) > 0 for v in states.values() if isinstance(v, dict))


async def _is_retired(db: AsyncSession | None = None) -> bool:
    from kb.revocation import is_retired

    try:
        return await is_retired(db)
    except Exception:  # noqa: BLE001
        return False


# ── 指针/清单（免费探测）──────────────────────────────────────────────────


async def _load_release() -> dict:
    """sign pointer → 下载/验签 → sign manifest → 下载/对拍 sha/验签。

    返回 {ok, reason, version, genres, quota, resume, pointer, manifest}。
    `reason` 为 `_FAILED_REASONS` 之外的都属于正常跳过（未登录/档位/配额/格式）。
    """
    from manifest_crypto import verify_manifest

    keys = _trust_keys()
    if not keys:
        return {"ok": False, "reason": "not_configured"}

    resp = await server_api.sign("baseline_pointer")
    code = resp.get("code", -1)
    if int(code) != 0:
        return {
            "ok": False,
            "reason": _reason_from_code(code),
            "quota": (resp.get("data") or {}).get("quota") or {},
        }
    data = resp.get("data") or {}
    quota = data.get("quota") or {}
    pointer_raw, pointer_verdict = await server_api.fetch_signed(
        str(data.get("url") or ""), _MAX_POINTER_BYTES
    )
    if pointer_raw is None:
        reason = "proxy_fake_ip" if pointer_verdict == "fakeip" else "pointer_fetch"
        return {"ok": False, "reason": reason, "quota": quota}
    try:
        pointer = json.loads(pointer_raw)
    except ValueError:
        pointer = None
    if not isinstance(pointer, dict) or not verify_manifest(pointer, keys):
        return {"ok": False, "reason": "pointer_invalid", "quota": quota}
    try:
        version = int(pointer.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version <= 0:
        return {"ok": False, "reason": "pointer_invalid", "quota": quota}

    resp = await server_api.sign("baseline_manifest", version=version)
    code = resp.get("code", -1)
    if int(code) != 0:
        return {
            "ok": False,
            "reason": _reason_from_code(code),
            "quota": (resp.get("data") or {}).get("quota") or quota,
            "version": version,
        }
    mdata = resp.get("data") or {}
    quota = mdata.get("quota") or quota
    manifest_raw, manifest_verdict = await server_api.fetch_signed(
        str(mdata.get("url") or ""), _MAX_MANIFEST_BYTES
    )
    if manifest_raw is None:
        reason = "proxy_fake_ip" if manifest_verdict == "fakeip" else "manifest_fetch"
        return {"ok": False, "reason": reason, "quota": quota, "version": version}
    if sha256_hex(manifest_raw) != str(pointer.get("manifest_sha256") or ""):
        return {"ok": False, "reason": "manifest_hash", "quota": quota, "version": version}
    try:
        manifest = json.loads(manifest_raw)
    except ValueError:
        manifest = None
    if not isinstance(manifest, dict) or not verify_manifest(manifest, keys):
        return {"ok": False, "reason": "manifest_invalid", "quota": quota, "version": version}
    if int(manifest.get("version") or 0) != version:
        return {"ok": False, "reason": "manifest_version", "quota": quota, "version": version}
    if not _format_ok(manifest):
        return {"ok": False, "reason": "format_newer", "quota": quota, "version": version}
    genres = manifest.get("genres")
    if not isinstance(genres, dict) or not genres:
        return {"ok": False, "reason": "manifest_genres", "quota": quota, "version": version}
    return {
        "ok": True,
        "pointer": pointer,
        "manifest": manifest,
        "version": version,
        "genres": {str(k): v for k, v in genres.items() if isinstance(v, dict)},
        "quota": quota,
        "resume": bool(pointer.get("resume_baseline")),
    }


async def probe_latest() -> dict:
    """只读探测：免费；返回已同步题材/可更新题材/配额/resume。"""
    states = await _genre_states()
    installed = _max_version(states)
    rel = await _load_release()
    if not rel["ok"]:
        # 撤回态优先于「未登录/网络失败」：本地已停用同步，UI 应提示已撤回。
        if await _is_retired():
            return {
                "installed": installed,
                "latest": 0,
                "update_available": False,
                "reason": "retired",
                "quota": rel.get("quota") or {},
                "genres": {},
                "installed_genres": states,
                "resume": False,
            }
        return {
            "installed": installed,
            "latest": 0,
            "update_available": False,
            "reason": rel["reason"],
            "quota": rel.get("quota") or {},
            "genres": {},
            "installed_genres": states,
            "resume": False,
        }
    if await _is_retired() and not rel["resume"]:
        return {
            "installed": installed,
            "latest": rel["version"],
            "update_available": False,
            "reason": "retired",
            "quota": rel["quota"],
            "genres": rel["genres"],
            "installed_genres": states,
            "resume": False,
        }
    updates = [
        genre
        for genre, meta in rel["genres"].items()
        if str((states.get(genre) or {}).get("sha256") or "")
        != str(meta.get("sha256") or "")
    ]
    return {
        "installed": installed,
        "latest": rel["version"],
        "update_available": bool(updates),
        "updates": updates,
        "genres": rel["genres"],
        "installed_genres": states,
        "quota": rel["quota"],
        "resume": rel["resume"],
        "reason": "",
    }


# ── 调度：只刷指针，不自动下载题材 ────────────────────────────────────────


def schedule_sync() -> None:
    """启动补偿：后台探测指针（免费）；`KB_BASELINE_SYNC=0` 关。"""
    import os

    if (os.environ.get("KB_BASELINE_SYNC") or "").strip() == "0":
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_sync_with_logging())


async def _sync_with_logging() -> None:
    try:
        result = await sync_baseline()
    except Exception:  # noqa: BLE001 —— 探测失败静默
        logger.warning("event=kb_baseline_probe_failed", exc_info=True)
        return
    if result.get("status") == "failed" or result.get("update_available"):
        logger.info("event=kb_baseline_probe %s", json.dumps(result, ensure_ascii=False))


RECHECK_INTERVAL = 3600.0
RECHECK_RETRY_INTERVAL = 300.0

_recheck_task = None


def _next_recheck_delay(result: dict) -> float:
    return RECHECK_RETRY_INTERVAL if result.get("status") == "failed" else RECHECK_INTERVAL


def schedule_periodic_recheck() -> None:
    """会话内周期复查：只探测（免费），不下载题材；`KB_BASELINE_SYNC=0` 同闸。"""
    import os

    global _recheck_task

    if (os.environ.get("KB_BASELINE_SYNC") or "").strip() == "0":
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _recheck_task is not None and not _recheck_task.done():
        return
    _recheck_task = loop.create_task(_recheck_loop())


async def _recheck_loop() -> None:
    delay = RECHECK_RETRY_INTERVAL
    while True:
        await asyncio.sleep(delay)
        try:
            result = await sync_baseline()
        except Exception:  # noqa: BLE001
            logger.warning("event=kb_baseline_recheck_failed", exc_info=True)
            result = {"status": "failed"}
        if result.get("status") == "failed" or result.get("update_available"):
            logger.info(
                "event=kb_baseline_recheck %s", json.dumps(result, ensure_ascii=False)
            )
        delay = _next_recheck_delay(result)


def maybe_sync() -> None:
    """登录钩子：只刷指针（free），不静默下载题材。"""
    import os

    if (os.environ.get("KB_BASELINE_SYNC") or "").strip() == "0":
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_sync_with_logging())


async def sync_baseline(db: AsyncSession | None = None) -> dict:
    """启动/登录/周期复查入口：只探测指针；返回 {status: probed|skipped|failed, ...}。"""
    if _syncing:
        return {"status": "skipped", "reason": "syncing"}
    probe = await probe_latest()
    reason = probe.get("reason")
    if reason in _FAILED_REASONS:
        return {"status": "failed", **probe}
    if reason:
        return {"status": "skipped", **probe}
    return {"status": "probed", **probe}


# ── 按题材同步（用户手动触发）────────────────────────────────────────────


async def sync_genre(genre: str, db: AsyncSession | None = None) -> dict:
    """下载并替换单个题材的官方层；只扣该题材 1 次配额。"""
    global _syncing

    genre = (genre or "").strip()
    if not genre:
        return {"status": "skipped", "reason": "genre_required"}
    if _syncing:
        return {"status": "skipped", "reason": "syncing"}
    _syncing = True
    try:
        retired = await _is_retired(db)
        rel = await _load_release()
        if retired and (not rel["ok"] or not rel["resume"]):
            return {"status": "skipped", "reason": "retired"}
        if not rel["ok"]:
            return {
                "status": "skipped" if rel["reason"] not in _FAILED_REASONS else "failed",
                "reason": rel["reason"],
                "quota": rel.get("quota") or {},
            }
        meta = rel["genres"].get(genre)
        if not isinstance(meta, dict) or not str(meta.get("path") or ""):
            return {"status": "skipped", "reason": "genre_not_found"}
        version = rel["version"]
        states = await _genre_states(db)
        state = states.get(genre) if isinstance(states.get(genre), dict) else {}
        if int(state.get("version") or 0) > version:
            return {
                "status": "skipped",
                "reason": "older_than_installed",
                "version": version,
            }
        if str(state.get("sha256") or "") == str(meta.get("sha256") or ""):
            return {"status": "current", "version": version, "genre": genre}

        resp = await server_api.sign(
            "baseline_genre",
            version=version,
            path=str(meta.get("path")),
            genre=genre,
        )
        code = resp.get("code", -1)
        quota = (resp.get("data") or {}).get("quota") or {}
        if int(code) != 0:
            skipped = int(code) in (401, -2, 403, 429)
            return {
                "status": "skipped" if skipped else "failed",
                "reason": _reason_from_code(code),
                "quota": quota,
            }
        data = resp.get("data") or {}
        quota = data.get("quota") or quota
        raw, verdict = await server_api.fetch_signed(
            str(data.get("url") or ""), _MAX_PACK_BYTES
        )
        if raw is None:
            reason = "proxy_fake_ip" if verdict == "fakeip" else "genre_fetch"
            return {"status": "failed", "reason": reason, "quota": quota}
        expected_bytes = meta.get("bytes")
        if isinstance(expected_bytes, int) and len(raw) != expected_bytes:
            return {"status": "failed", "reason": "genre_size", "quota": quota}
        if sha256_hex(raw) != str(meta.get("sha256") or ""):
            return {"status": "failed", "reason": "genre_hash", "quota": quota}

        entries, skipped, rejected = _parse_entries(raw)
        expected_count = meta.get("entry_count")
        if isinstance(expected_count, int) and expected_count > 0 and not entries:
            return {
                "status": "failed",
                "reason": "entry_count",
                "skipped": skipped,
                "quota": quota,
            }
        if skipped:
            logger.warning(
                "event=kb_baseline_partial genre=%s version=%s accepted=%d skipped=%d",
                genre, version, len(entries), skipped,
            )

        if db is None:
            from db import async_session

            async with async_session() as session:
                return await _replace_genre_layer(
                    session, genre, version, entries, skipped, rel["manifest"],
                    rejected, meta, quota, resume=rel["resume"],
                )
        return await _replace_genre_layer(
            db, genre, version, entries, skipped, rel["manifest"], rejected,
            meta, quota, resume=rel["resume"],
        )
    except Exception:  # noqa: BLE001 —— 任何异常＝保持旧层，静默可重试
        logger.warning("event=kb_baseline_sync_failed", exc_info=True)
        return {"status": "failed"}
    finally:
        _syncing = False


async def _replace_genre_layer(
    db: AsyncSession,
    genre: str,
    version: int,
    entries: list[dict],
    skipped: int,
    manifest: dict,
    rejected: set[str] | None,
    meta: dict,
    quota: dict,
    *,
    resume: bool,
) -> dict:
    """只替换该题材的只读层：其他题材行/overlay 原样保留；单事务提交。"""
    old_rows = {
        r.src_key: r
        for r in (
            await db.execute(
                select(KbBaselineEntry).where(KbBaselineEntry.genre == genre)
            )
        ).scalars().all()
    }
    old_ids = [r.entry_id for r in old_rows.values()]
    if old_ids:
        await db.execute(_del(KbBaselineTag).where(KbBaselineTag.entry_id.in_(old_ids)))
        await db.execute(_del(KbBaselineEntry).where(KbBaselineEntry.entry_id.in_(old_ids)))

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
                "pack_version": old.pack_version,
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
                "concept": old.concept,
                "genre": old.genre,
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

    # 每题材状态 + 全局版本（兼容 write_block 旧读数；新 fingerprint 用 genre_states）
    states = await _genre_states(db)
    states[genre] = {
        "version": version,
        "sha256": str(meta.get("sha256") or ""),
        "path": str(meta.get("path") or ""),
        "entries": len(rows),
        "synced_at": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
    }
    await _save_genre_states(db, states)
    max_version = _max_version(states) or version
    version_row = await db.get(AppMeta, VERSION_KEY)
    if version_row is None:
        db.add(AppMeta(key=VERSION_KEY, value=str(max_version)))
    else:
        version_row.value = str(max_version)

    # overlay 清理/提升只在该题材的 src_key 作用域内
    old_keys = set(old_rows)
    new_keys = set(accepted_keys)
    scoped = sorted(old_keys | new_keys)
    overlays = (
        (
            await db.execute(
                select(KbBaselineOverlay).where(
                    KbBaselineOverlay.src_key.in_(scoped)
                )
            )
        ).scalars().all()
        if scoped
        else []
    )
    promoted = 0
    for ov in overlays:
        if ov.src_key in new_keys:
            continue
        if ov.action == "hide":
            if (ov.content or "").strip():
                continue
            await db.delete(ov)
            continue
        old = old_rows.get(ov.src_key)
        if old is None:
            continue
        existing = await find_promoted_copy(db, user_id=ov.user_id, src_key=ov.src_key)
        if existing is not None and getattr(existing, "status", "active") == "active":
            text = (ov.content or "").strip()
            if text:
                existing.instruction = text
            await db.delete(ov)
            promoted += 1
            continue
        await _promote_overlay(db, ov, old)
        await db.delete(ov)
        promoted += 1
    readded = new_keys - old_keys
    await _hide_radded_promoted(db, readded)

    if resume and await _is_retired(db):
        retired_row = await db.get(AppMeta, RETIRED_KEY)
        if retired_row is None:
            db.add(AppMeta(key=RETIRED_KEY, value="0"))
        else:
            retired_row.value = "0"

    summary = {
        "at": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
        "version": version,
        "genre": genre,
        "accepted": len(entries),
        "skipped": skipped,
        "carried": carried,
        "promoted": promoted,
        "quota": quota,
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
        "genre": genre,
        "entries": len(rows),
        "tags": len(tag_rows),
        "skipped": skipped,
        "carried": carried,
        "promoted": promoted,
        "quota": quota,
    }


# ── overlay 提升/去重（原逻辑，保留）──────────────────────────────────────

_PROMOTED_SRC = "官方精选（已下架）"


def _promoted_key(row) -> str:
    try:
        return str(json.loads(row.evidence_json or "{}").get("promoted_from") or "")
    except ValueError:
        return ""


async def find_promoted_copy(
    db: AsyncSession, *, user_id: str, src_key: str
) -> object | None:
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
                user_id=row.user_id,
                src_key=key,
                action="hide",
                content="",
                base_content_sha256="",
            )
        )
        existing.add((row.user_id, key))


async def _promote_overlay(
    db: AsyncSession, ov: KbBaselineOverlay, old: KbBaselineEntry
) -> None:
    await promote_overlay_copy(
        db,
        user_id=ov.user_id,
        src_key=old.src_key,
        content=ov.content or "",
        meta={
            "genre": old.genre,
            "concept": old.concept,
            "title": old.title,
            "payload_json": old.payload_json,
            "when_json": old.when_json,
            "instruction": old.instruction,
        },
    )


async def promote_overlay_copy(
    db: AsyncSession, *, user_id: str, src_key: str, content: str, meta: dict
) -> bool:
    from kb.service import _tags_for as _entry_tags_for
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
        evidence_json=json.dumps({"promoted_from": src_key}, ensure_ascii=False),
    )
    db.add(entry)
    await db.flush()
    tag_rows = [
        {"entry_id": entry.id, "user_id": user_id, "dim": dim, "value": value}
        for dim, value in _entry_tags_for(entry, payload, when)
    ]
    if tag_rows:
        await db.execute(_ins(KbEntryTag), tag_rows)
    return True
