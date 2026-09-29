"""故事状态（截至某章）——章档累计态的查询折叠单源（c-chapter-dossier D5）。

两个消费方共用，口径唯一：
- 章档提取（archive/dossier.py）：输入基线＝截至**上一章**的累计态（认知/关系/
  物品判「变化」的依据）；
- 写正文组装（chapter_writer）与组装来源只读展示：「故事状态（截至上章）」段。

折叠规则（确定性，按 (volume_no, chapter_no) 章序）：
- settings：按 (area, content) 归一去重，后章覆盖；
- relations：按 (owner, other) 有序对 upsert，后章覆盖；
- items：按 item_name 取最新（持有者状态）；
- knowledge：按 (character, fact) 翻转覆盖（不知 → 已知）。

只取「主线 ∧ status='archived' ∧ not dossier_stale」章的 accepted 行——
unarchive 章按章现态退出消费；stale 章跳过并进 skipped_stale_refs（块头注记用）。
"""

from __future__ import annotations

from sqlalchemy import select

DOMAIN_KEYS = ("settings", "relations", "items", "knowledge")


def _norm(s: str) -> str:
    return "".join(str(s or "").split())


async def _cutoff_key(session, novel_id: str, upto_ref: str | None):
    """upto_ref 主线章的 (volume_no, chapter_no)；找不到返回 None（全书）。"""
    from models.chapter import Chapter
    from models.volume import Volume

    if upto_ref is None:
        return None
    return (
        await session.execute(
            select(Volume.volume_no, Chapter.chapter_no)
            .join(Chapter, Chapter.volume_id == Volume.id)
            .where(
                Chapter.project_id == novel_id,
                Chapter.ref == upto_ref,
                Chapter.ghost_of.is_(None),
            )
        )
    ).first()


def _key_le(a, b) -> bool:
    return a[0] < b[0] or (a[0] == b[0] and a[1] <= b[1])


async def story_state_upto(
    novel_id: str,
    upto_ref: str | None = None,
    *,
    exclusive: bool = False,
) -> dict:
    """截至 upto_ref 章（含；exclusive=True 时不含该章）的累计态。

    返回 {settings/relations/items/knowledge: [条目…], skipped_stale_refs: [ref…]}。
    条目含领域字段与来源 ref（渲染层不输出 ref）。
    """
    from models.chapter import (
        Chapter,
        ChapterItemChange,
        ChapterKnowledgeChange,
        ChapterRelationChange,
        ChapterSettingChange,
    )
    from models.volume import Volume

    async with _session() as session:
        cutoff = await _cutoff_key(session, novel_id, upto_ref)

        async def _rows(model, *cols):
            stmt = (
                select(Chapter.ref, *cols)
                .join(Chapter, Chapter.id == model.chapter_id)
                .join(Volume, Volume.id == Chapter.volume_id)
                .where(
                    Chapter.project_id == novel_id,
                    Chapter.ghost_of.is_(None),
                    Chapter.status == "archived",
                    Chapter.dossier_stale.is_(False),
                    model.status == "accepted",
                )
                .order_by(Volume.volume_no, Chapter.chapter_no, model.sort_order)
            )
            return (await session.execute(stmt)).all()

        settings_rows = await _rows(
            ChapterSettingChange, ChapterSettingChange.area, ChapterSettingChange.content
        )
        relation_rows = await _rows(
            ChapterRelationChange,
            ChapterRelationChange.owner_name,
            ChapterRelationChange.other_name,
            ChapterRelationChange.rel_type,
            ChapterRelationChange.change_note,
        )
        item_rows = await _rows(
            ChapterItemChange,
            ChapterItemChange.item_name,
            ChapterItemChange.change_type,
            ChapterItemChange.holder_name,
            ChapterItemChange.detail,
        )
        knowledge_rows = await _rows(
            ChapterKnowledgeChange,
            ChapterKnowledgeChange.character_name,
            ChapterKnowledgeChange.fact,
            ChapterKnowledgeChange.learned,
        )
        # stale 章注记（含被跳过章的 ref，供块头「基于旧设定仅供参考」）
        stale_refs = [
            r[0]
            for r in (
                await session.execute(
                    select(Chapter.ref)
                    .join(Volume, Volume.id == Chapter.volume_id)
                    .where(
                        Chapter.project_id == novel_id,
                        Chapter.ghost_of.is_(None),
                        Chapter.status == "archived",
                        Chapter.dossier_stale.is_(True),
                    )
                    .order_by(Volume.volume_no, Chapter.chapter_no)
                )
            ).all()
        ]

    def _ref_key(ref: str):
        try:
            v = int(ref.split("-")[1])
            c = int(ref.rsplit("ch-", 1)[-1].split("-")[0])
            return (v, c)
        except (IndexError, ValueError):
            return (10**9, 10**9)

    def _keep(ref: str) -> bool:
        if cutoff is None:
            return True
        k = _ref_key(ref)
        return k < cutoff if exclusive else _key_le(k, cutoff)

    settings: dict[tuple, dict] = {}
    for ref, area, content in settings_rows:
        if not _keep(ref):
            continue
        settings[(_norm(area), _norm(content))] = {
            "area": area, "content": content, "ref": ref,
        }
    relations: dict[tuple, dict] = {}
    for ref, owner, other, rel_type, note in relation_rows:
        if not _keep(ref):
            continue
        relations[(_norm(owner), _norm(other))] = {
            "owner": owner, "other": other, "rel_type": rel_type,
            "change_note": note, "ref": ref,
        }
    items: dict[str, dict] = {}
    for ref, name, change_type, holder, detail in item_rows:
        if not _keep(ref):
            continue
        items[_norm(name)] = {
            "name": name, "change_type": change_type, "holder": holder,
            "detail": detail, "ref": ref,
        }
    knowledge: dict[tuple, dict] = {}
    for ref, character, fact, learned in knowledge_rows:
        if not _keep(ref):
            continue
        knowledge[(_norm(character), _norm(fact))] = {
            "character": character, "fact": fact,
            "learned": bool(learned), "ref": ref,
        }

    return {
        "settings": list(settings.values()),
        "relations": list(relations.values()),
        "items": list(items.values()),
        "knowledge": list(knowledge.values()),
        "skipped_stale_refs": [r for r in stale_refs if _keep(r)],
    }


def _session():
    from db import async_session

    return async_session()
