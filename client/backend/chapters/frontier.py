"""主线 frontier（workbench-frontier，storyline.html 口径）。

规则（storyline.html 原型为准）：
- 主线顺序 = 卷序 × 章序；
- frontier = 主线上第一个「未归档」的章（草稿或拟定）；
- 全部归档时 frontier = 主线末端的「待写」占位章（不落库，写时创建）；
- 可写性：frontier 章（或任何**已有正文**的章＝草稿可继续）可写；
  frontier 之后的拟定章 SHALL NOT 写正文（排队门禁）。
- 存量兼容：章的状态枚举不扩展——「拟定/草稿」为派生态
  （有正文未归档＝草稿；无正文未归档＝拟定），待写为纯派生占位。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.chapter import Chapter


async def frontier_info(db: AsyncSession, novel_id: str) -> dict:
    """返回 {ref, chapter_no, state, writable, volume_id}；空书返回 chapters=[] 语义由调用方处理。"""
    # 主线性单源（chapters/scope.py）：ghost_of IS NULL——旧稿快照不得抢占 frontier
    from chapters.scope import mainline_stmt

    rows = (await db.scalars(mainline_stmt(novel_id).order_by(Chapter.ref))).all()
    chapters = sorted(
        (
            {
                "ref": c.ref,
                "chapter_no": c.chapter_no,
                "volume_no": _vol_no(c.ref),
                "has_prose": bool(c.has_prose),
                "archived": c.status == "archived",
            }
            for c in rows
        ),
        key=lambda ch: (ch["volume_no"], ch["chapter_no"]),
    )
    return {"chapters": chapters, "frontier": _pick_frontier(chapters)}


def _vol_no(ref: str) -> int:
    try:
        return int(ref.split("-")[1])
    except (IndexError, ValueError):
        return 0


def _pick_frontier(chapters: list[dict]) -> dict | None:
    for ch in chapters:
        if not ch["archived"]:
            return _decorate(ch, chapters)
    # 全部归档：待写占位 = 主线末端 + 1
    if not chapters:
        return None
    last = chapters[-1]
    pending = {
        "ref": _next_ref(last["ref"]),
        "chapter_no": last["chapter_no"] + 1,
        "volume_no": last["volume_no"],
        "has_prose": False,
        "archived": False,
        "pending": True,
    }
    return _decorate(pending, chapters)


def _decorate(ch: dict, chapters: list[dict]) -> dict:
    # 草稿 = 有正文未归档；拟定 = 无正文未归档；待写 = pending 占位
    if ch.get("pending"):
        state = "pending"
    elif ch["has_prose"]:
        state = "draft"
    else:
        state = "planned"
    # 可写：frontier 自己，或任何已有正文的章（存量草稿可继续）；
    # frontier 之后的章不可写（排队门禁）
    idx = chapters.index(ch) if ch in chapters else len(chapters)
    earlier_unwritten = any(
        not c["has_prose"] and not c["archived"] for c in chapters[:idx]
    )
    writable = not earlier_unwritten or bool(ch["has_prose"])
    return {**ch, "state": state, "writable": writable}


def _next_ref(ref: str) -> str:
    """vol-1-ch-3 → vol-1-ch-4（同卷续章）。"""
    import re

    m = re.match(r"^(vol-\d+-ch-)(\d+)$", ref)
    if not m:
        return ref + "-next"
    return f"{m.group(1)}{int(m.group(2)) + 1}"


async def is_writable(db: AsyncSession, novel_id: str, ref: str) -> tuple[bool, str]:
    """排队门禁：章可写 = 自己已有正文，或它是主线 frontier（前面无未写章）。

    返回 (可写, 拒绝原因)；拒绝文案面向作者（无内部术语）。
    """
    info = await frontier_info(db, novel_id)
    row = (
        await db.scalars(
            select(Chapter).where(
                Chapter.project_id == novel_id, Chapter.ref == ref
            )
        )
    ).first()
    if row is not None and row.ghost_of:
        return False, "旧稿支线只读"
    target = next((c for c in info["chapters"] if c["ref"] == ref), None)
    if target is None:
        return True, ""  # 章不存在（将由调用方 404），门禁不拦
    front = info["frontier"]
    if target["has_prose"]:
        return True, ""
    if front is None:
        return True, ""
    if front.get("pending"):
        # 全部归档：待写占位由「新增一章」创建后即为 frontier
        return True, ""
    if front["ref"] == ref:
        return True, ""
    return (
        False,
        f"还不能写这一章：先完成前面的章节（当前主线在第 {front['chapter_no']} 章）",
    )


def asyncio_run_frontier(db: AsyncSession, novel_id: str) -> dict:
    """同事件流内直接复用调用方的 session 跑 frontier 查询。"""
    import asyncio

    return asyncio.get_event_loop().run_until_complete(frontier_info(db, novel_id))


async def revert_to_chapter(db: AsyncSession, novel_id: str, ref: str) -> dict:
    """回退到指定章（revert-ghost）：

    - 主线上该章之后的章（含跨卷）→ 旧稿支线（ghost_of = 回退点 ref），
      正文原样保留、只读；
    - 支线章的派生数据按章序清除：出场引用 state_change 清空、
      来源章在支线的关系记录删除、支线章引入的伏笔删除、
      支线章收束的伏笔回到进行中、支线章的收尾提案与归档行删除；
    - 世界 lore 的已采纳条目不回撤（显式采纳属作者决定，见 spec）。

    返回 {ghosted: n, hooks_removed: n, hooks_reactivated: n, relations_removed: n}。
    """
    from fastapi import HTTPException

    from chapters.scope import mainline_stmt
    from models.archive import Archive
    from models.hook import NovelHook
    from models.reconcile import ChapterReconcile

    rows = (await db.scalars(mainline_stmt(novel_id).order_by(Chapter.ref))).all()
    mainline = [
        {"row": c, "volume_no": _vol_no(c.ref), "chapter_no": c.chapter_no}
        for c in rows
    ]
    target = next((m for m in mainline if m["row"].ref == ref), None)
    if target is None:
        raise HTTPException(404, "Chapter not found")

    ghost_rows = [m["row"] for m in mainline if (m["volume_no"], m["chapter_no"]) > (target["volume_no"], target["chapter_no"])]
    ghost_ids = [c.id for c in ghost_rows]
    for c in ghost_rows:
        c.ghost_of = ref
        c.status = "writing" if c.has_prose else "outline"
        c.archived_at = None

    ghosts_set = set(ghost_ids)

    # 出场引用：state_change 清空（变化来自被回退的线）
    from models.chapter import ChapterCharacter

    for cid in ghost_ids:
        for cc in await db.scalars(
            select(ChapterCharacter).where(ChapterCharacter.chapter_id == cid)
        ):
            cc.state_change = ""

    # 关系：来源章在支线的记录删除（它们由那条线长出）
    rels_removed = 0
    from models.character import CharacterRelation

    for rel in await db.scalars(
        select(CharacterRelation).where(
            CharacterRelation.novel_id == novel_id,
            CharacterRelation.origin_chapter_id.in_(ghosts_set),
        )
    ):
        await db.delete(rel)
        rels_removed += 1

    # 伏笔：支线章引入的删除；支线章收束的回到进行中；支线章 mentioned 清空
    hooks_removed = 0
    hooks_reactivated = 0
    for h in await db.scalars(
        select(NovelHook).where(
            NovelHook.novel_id == novel_id,
            NovelHook.status != "abandoned",
        )
    ):
        changed = False
        if h.introduced_chapter_id in ghosts_set:
            await db.delete(h)
            hooks_removed += 1
            changed = True
        else:
            if h.resolved_chapter_id in ghosts_set:
                h.status = "active"
                h.resolved_chapter_id = None
                changed = True
            if h.mentioned_chapter_id in ghosts_set:
                h.mentioned_chapter_id = None
                changed = True
        if changed:
            hooks_reactivated += 1 if h.status == "active" else 0

    # 收尾提案与归档行：支线章的一并删除
    for cid in ghost_ids:
        for rec in await db.scalars(
            select(ChapterReconcile).where(ChapterReconcile.chapter_id == cid)
        ):
            await db.delete(rec)
        for arc in await db.scalars(
            select(Archive).where(Archive.chapter_id == cid)
        ):
            await db.delete(arc)

    await db.commit()
    return {
        "ghosted": len(ghost_rows),
        "hooks_removed": hooks_removed,
        "relations_removed": rels_removed,
    }
