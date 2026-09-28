"""归档收尾提案服务（archive-reconcile）。

归档即刻生效后，AI 在后台完成收尾（设定变化提取/关系建议/伏笔登记/lore 建议/
角色状态变化），产出一律先落 chapter_reconcile 待确认行；作者逐条采纳才经
目标对象自身服务写回。未确认提案不在目标对象上 → 天然不进后续章节的提示词。

设计要点（design.md D1-D3）：
- 提案行不复存对象数据（payload 只存待确认差异＋证据句）；采纳走对象自身服务。
- 同章同键未决行覆盖（防堆积）；已决行保留留痕。
- 后台单飞线程（每章一把锁）：照抄 backup/export._job 模式；asyncio.run 包异步主体。
- 收尾 AI 全归 PRO：免费档/模型未就绪 → 不产生提案行（归档本身不受影响）。
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime

from sqlalchemy import select

from db import async_session
from models.chapter import Chapter
from models.hook import NovelHook
from models.project import Novel
from models.reconcile import ChapterReconcile

# 收尾类别 → 展示名（工作台「操作」页签用）
# c-chapter-dossier：set_changes/relations/char_states 三类迁章档页签，收尾通道
# 只剩伏笔登记与世界要素两类（采纳写回书级）；四域提取见 archive/dossier.py。
KINDS: dict[str, str] = {
    "hooks": "伏笔登记",
    "lore": "世界要素",
}

_job_lock = threading.Lock()
_job: dict | None = None  # 全局单飞：同一时刻只跑一章收尾（与提取的每章键控单飞不同）


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _load_pending(session, chapter_id: str, kind: str):
    """同章同键未决行（覆盖用）。"""
    return (
        await session.scalars(
            select(ChapterReconcile).where(
                ChapterReconcile.chapter_id == chapter_id,
                ChapterReconcile.kind == kind,
                ChapterReconcile.status == "pending",
            )
        )
    ).all()


async def _upsert_pending(session, chapter_id: str, novel_id: str, kind: str, payload: dict) -> str:
    """同章同键未决行覆盖；无未决则新建。返回行 id。"""
    pending = await _load_pending(session, chapter_id, kind)
    if pending:
        row = pending[0]
        for extra in pending[1:]:
            extra.status = "rejected"  # 多余未决行并入驳回（防御性，正常不出现）
        row.payload = json.dumps(payload, ensure_ascii=False)
        row.error = ""
        session.add(row)
        return row.id
    row = ChapterReconcile(
        novel_id=novel_id,
        chapter_id=chapter_id,
        kind=kind,
        status="pending",
        payload=json.dumps(payload, ensure_ascii=False),
        # created_at 走列 server_default（DateTime 列；此前的 ISO 字符串会在
        # SQLite 直接 TypeError——收尾任务一落行即炸，本测试首跑撕出）
    )
    session.add(row)
    await session.flush()  # id 为 insert 期默认值：不 flush 返回 None
    return row.id


def start_reconcile_job(
    novel_id: str,
    root_path: str,
    chapter_ref: str,
    chapter_id: str,
    kinds: list[str] | None = None,
) -> dict | None:
    """单飞：同章已跑收尾返回 None（调用方忽略即可，进度区以行状态为准）。

    kinds：按类按需触发（工作台右栏 AI 辅助的三处入口）；None＝全量五类。
    """
    global _job
    key = f"{novel_id}:{chapter_ref}"
    with _job_lock:
        if _job and _job.get("state") == "running":
            return None
        _job = {"state": "running", "key": key, "started": _now_iso(), "kinds": kinds}
    t = threading.Thread(
        target=_run_thread,
        args=(novel_id, root_path, chapter_ref, chapter_id, kinds),
        daemon=True,
    )
    t.start()
    return {"state": "running", "key": key}


def _run_thread(
    novel_id: str, root_path: str, chapter_ref: str, chapter_id: str,
    kinds: list[str] | None = None,
) -> None:
    try:
        asyncio.run(_run_async(novel_id, root_path, chapter_ref, chapter_id, kinds))
    except Exception as e:  # noqa: BLE001,S110 — 收尾失败不影响归档；留痕供排查
        print(f"[reconcile] chapter {chapter_ref} 收尾失败：{e}")
    finally:
        global _job
        with _job_lock:
            _job = None


async def _run_async(
    novel_id: str, root_path: str, chapter_ref: str, chapter_id: str,
    kinds: list[str] | None = None,
) -> None:
    from ai_client import get_ai_client_for_novel
    from chapters.store import load_chapter

    # 模型未就绪：静默不产生提案（免费/未配置）
    try:
        client = await get_ai_client_for_novel(novel_id)
    except Exception:  # noqa: BLE001
        client = None
    if client is None:
        return

    chapter = await load_chapter(root_path, chapter_ref)
    full_text = chapter.get("prose", "")
    if not full_text.strip():
        return

    # ① 伏笔登记（埋下/收束＋证据句）→ kind=hooks
    # ② 世界要素建议 → kind=lore
    # （set_changes/relations/char_states 三类已迁章档，c-chapter-dossier）
    outline_chars = (chapter.get("outline") or {}).get("characters") or []
    cast = [str(n) for n in outline_chars if str(n).strip()]
    # lore 段带「现有世界设定」：只提与外面对不上的新要素（防重复提案）
    from filesystem.storage import get_storage
    from settings.world_model import world_summary_text

    world_raw = await get_storage().read_yaml(root_path, "settings/world-setting.yaml") or {}
    world_now = world_summary_text(world_raw, None).strip()

    for kind, prompt in _collect_prompts(chapter_ref, chapter, full_text, cast, world_now):
        if kinds is not None and kind not in kinds:
            continue
        usage: dict = {}
        try:
            text = await client.chat(
                model="haiku", system="", messages=[{"role": "user", "content": prompt}],
                max_tokens=600, usage=usage,
            )
            await _record(novel_id, kind, usage)
            data = _parse_json_lenient(text)
            if not data:
                # 返回了文字但不是 JSON：显式落失败行（可重试），不得静默蒸发
                await _record_fail(novel_id, kind, usage)
                await _mark_failed(
                    novel_id, chapter_id, kind,
                    f"parse: 模型输出不是可解析的 JSON（{str(text)[:120]}）",
                )
                continue
        except Exception:  # noqa: BLE001 — 单类失败不拖垮其他收尾
            await _record_fail(novel_id, kind, usage)
            await _mark_failed(novel_id, chapter_id, kind, str(usage))
            continue
        async with async_session() as session:
            await _upsert_pending(session, chapter_id, novel_id, kind, data)
            await session.commit()


def _collect_prompts(
    chapter_ref: str, chapter: dict, full_text: str, cast: list[str], world_now: str = ""
):
    """两类收尾的 prompt；正文全量给（章目标上限 6000，旧 [:3000] 会丢掉章末钩子）。

    lore 段带「现有世界设定」：只提与外面对不上的新要素（防重复提案）。
    """
    body = full_text
    world_block = f"现有世界设定（与之重复的不要提）：\n{world_now}\n\n" if world_now else ""
    yield "hooks", (
        f"判断第 {chapter_ref} 章埋下或收束了哪些伏笔，每条给出证据句。"
        f'JSON 数组输出，形如 {{"planted": [{{"description": "信标坐标漂移", '
        f'"evidence": "原文一句话"}}], "resolved": [{{"description": "镜面之谜", '
        f'"evidence": "…"}}]}}。没有则输出空数组。\n\n正文：\n{body}'
    )
    yield "lore", (
        f"从第 {chapter_ref} 章正文识别新出现或变化的世界要素（地点/组织/历史/规则）。"
        f"JSON 数组输出，每条含 key/value/set，set 取 history/factions/extra，拿不准用 extra；"
        f'形如 {{"items": [{{"key": "静默带", "value": "一句话", "set": "extra"}}]}}。'
        f"没有则输出空数组。\n\n{world_block}正文：\n{body}"
    )


def _parse_json_lenient(text: str) -> dict | None:
    """模型输出宽松 JSON 解析：截取首个 { 到末个 }；失败返回 None。"""
    import json as _json

    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = _json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


async def _record(novel_id: str, kind: str, usage: dict) -> None:
    from archive.service import _record_ai_usage

    await _record_ai_usage(novel_id, f"reconcile_{kind}", usage)


async def _record_fail(novel_id: str, kind: str, usage: dict) -> None:
    from archive.service import _record_ai_usage

    await _record_ai_usage(novel_id, f"reconcile_{kind}_fail", usage, force=True)


async def _mark_failed(novel_id: str, chapter_id: str, kind: str, message: str) -> None:
    async with async_session() as session:
        row = ChapterReconcile(
            novel_id=novel_id,
            chapter_id=chapter_id,
            kind=kind,
            status="failed",
            payload="{}",
            error=message[:500],
        )
        session.add(row)
        await session.commit()


async def apply_accept(db, row: ChapterReconcile) -> None:
    """采纳：经目标对象自身服务写回。任一步失败抛异常（行置 failed 保留 payload）。

    c-chapter-dossier 后只剩两类：lore → lore-apply 幂等合并；hooks → 伏笔服务。
    退役 kind（set_changes/relations/char_states）到达此处 → ValueError（上游
    run/retry 白名单已拦，历史已决行不会再被采纳）。
    """
    import json as _json

    payload = _json.loads(row.payload or "{}")

    if row.kind == "lore":
        # 世界要素建议 → lore-apply 幂等合并（origin=本章 ref）
        from filesystem.storage import get_storage
        from settings.world_model import (
            lore_apply_entries,
            normalize_world,
            put_world_merged,
        )

        novel = await db.get(Novel, row.novel_id)
        ch = await db.get(Chapter, row.chapter_id)
        items = payload.get("items") or []
        from settings.world_model import SET_NAMES as _WORLD_SETS

        entries = []
        for i in items:
            if not isinstance(i, dict) or not str(i.get("key", "")).strip():
                continue
            set_name = str(i.get("set", "")).strip()
            if set_name not in _WORLD_SETS:
                set_name = "extra"  # 归属缺失/非法 → 「更多世界细节」（可后补名目）
            entries.append({
                "key": str(i.get("key", "")).strip(),
                "value": str(i.get("value", "")).strip(),
                "origin": ch.ref if ch else "",
                "set": set_name,
            })
        # 路径唯一来源（filesystem.paths.KEY_TO_PATH）：硬编码 settings/world.yaml
        # 会写进一个全仓没人读的野文件（本测试撕出）
        from filesystem.paths import KEY_TO_PATH as _K2P

        raw = await get_storage().read_yaml(novel.root_path, _K2P["world"]) or {}
        v2 = normalize_world(raw)
        v2 = lore_apply_entries(v2, entries)
        merged = put_world_merged(raw, v2)
        await get_storage().write_yaml(novel.root_path, _K2P["world"], merged)

    elif row.kind == "hooks":
        # 伏笔登记：埋下 → create_hook(active, introduced=本章)；
        # 收束 → 描述匹配既有 active 钩（命中改 resolved＋收束章；未命中建已收束条目）
        from settings.hooks_service import create_hook, patch_hook

        for item in payload.get("planted") or []:
            await create_hook(db, row.novel_id, {
                "description": str(item.get("description", ""))[:300],
                "type": "mystery",
                "priority": 2,
                "status": "active",
                # 服务契约：章引用列只认章 id（ref 字符串会被白名单拒绝）
                "introduced_chapter_id": row.chapter_id,
            })
        for item in payload.get("resolved") or []:
            desc = str(item.get("description", ""))[:300]
            hooks = (
                await db.scalars(
                    select(NovelHook).where(
                        NovelHook.novel_id == row.novel_id,
                        NovelHook.status == "active",
                    )
                )
            ).all()
            target = next(
                (h for h in hooks if desc and desc in (h.description or "")), None
            )
            if target is not None:
                await patch_hook(db, row.novel_id, target.id, {
                    "status": "resolved",
                    "resolved_chapter_id": row.chapter_id,
                })
            else:
                await create_hook(db, row.novel_id, {
                    "description": desc,
                    "type": "mystery",
                    "priority": 2,
                    "status": "resolved",
                    "introduced_chapter_id": row.chapter_id,
                    "resolved_chapter_id": row.chapter_id,
                })

    else:
        raise ValueError(f"未知的收尾类别：{row.kind}")

    row.status = "accepted"
    row.decided_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(row)


async def migrate_legacy_pending() -> dict:
    """存量退役 kind 的 pending 行一次性迁移（c-chapter-dossier，启动幂等）。

    - set_changes/relations pending → 物化成对应章档子表 pending 行
      （与既有章档行合并后整批重建；无证据句置空）；
    - char_states pending → 置 rejected（数据生成时已直写 state_change，非提案语义）；
    - 已迁移的 pending 行删除（chapter_reconcile 是运行态待办、不进备份，
      历史已决行原地留痕不搬）。
    """
    import json as _json

    from chapters.store import _apply_dossier
    from models.chapter import Chapter

    migrated = 0
    rejected = 0
    async with async_session() as session:
        rows = (
            await session.scalars(
                select(ChapterReconcile).where(
                    ChapterReconcile.status == "pending",
                    ChapterReconcile.kind.in_(("set_changes", "relations", "char_states")),
                )
            )
        ).all()
        by_chapter: dict[str, list[ChapterReconcile]] = {}
        for r in rows:
            by_chapter.setdefault(r.chapter_id, []).append(r)
        for chapter_id, group in by_chapter.items():
            chapter = await session.get(Chapter, chapter_id)
            if chapter is None:
                continue
            # 现有章档行并入 payload（_apply_dossier 是整批替换语义）
            payload = {
                "settings": [
                    {"area": s.area, "content": s.content, "evidence": s.evidence,
                     "status": s.status, "flags": s.flags}
                    for s in chapter.dossier_settings
                ],
                "relations": [
                    {"owner": r_.owner_name, "other": r_.other_name,
                     "rel_type": r_.rel_type, "change_note": r_.change_note,
                     "evidence": r_.evidence, "status": r_.status, "flags": r_.flags}
                    for r_ in chapter.dossier_relations
                ],
                "items": [], "knowledge": [],
            }
            touched = False
            for rec in group:
                if rec.kind == "char_states":
                    rec.status = "rejected"
                    rec.decided_at = datetime.now(UTC).replace(tzinfo=None)
                    rejected += 1
                    continue
                try:
                    data = _json.loads(rec.payload or "{}")
                except ValueError:
                    data = {}
                items = data.get("items") if isinstance(data, dict) else None
                if rec.kind == "set_changes":
                    for i in items or []:
                        if isinstance(i, dict) and str(i.get("value", "")).strip():
                            payload["settings"].append({
                                "area": str(i.get("set", "extra"))[:50],
                                "content": str(i.get("key", "") + "：" + i.get("value", ""))[:300],
                                "evidence": "", "status": "pending", "flags": "",
                            })
                            migrated += 1
                            touched = True
                elif rec.kind == "relations":
                    for i in items or []:
                        if isinstance(i, dict) and str(i.get("owner", "")).strip() \
                                and str(i.get("other", "")).strip():
                            payload["relations"].append({
                                "owner": str(i.get("owner", ""))[:50],
                                "other": str(i.get("other", ""))[:50],
                                "rel_type": str(i.get("rel_type", ""))[:50],
                                "change_note": str(i.get("stance", "") or i.get("note", ""))[:300],
                                "evidence": "", "status": "pending", "flags": "",
                            })
                            migrated += 1
                            touched = True
                # 已物化/已驳回的原 pending 行删除（char_states 除外——置 rejected 留痕）
                await session.delete(rec)
            if touched:
                for attr in ("dossier_settings", "dossier_relations",
                             "dossier_items", "dossier_knowledge"):
                    getattr(chapter, attr).clear()
                await session.flush()
                _apply_dossier(chapter, payload, {})
        await session.commit()
    return {"migrated": migrated, "char_states_rejected": rejected}
