"""重写这一章（chapter-rewrite）：旧稿快照转旧稿支线＋下游「基于旧设定」置位。

设计要点（评审后的设计层方案）：
- **内容寻址旧稿 ref**：`{ref}-r{sha256(正文)[:8]}`——同内容重放=同 ref，
  唯一键天然幂等（双击/重试不产生重复旧稿，无取号竞态）。
- **stale 是章自身的列**：重写事务把源章之后的主线章（有正文者）置 stale=True；
  本章自身被写（正文/章纲保存）时由单写入口（chapters/store.save_chapter）清除。
  不做时间戳派生（updated_at 条件触发不可靠）。
- **合成事务**：快照 + 归档章解锁 + 下游置位一次提交；失败全败。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from chapters.frontier import _vol_no
from chapters.scope import mainline_stmt
from models.chapter import Chapter, ChapterContent
from repositories import chapter_repo


def ghost_ref_for(ref: str, prose: str) -> str:
    """内容寻址旧稿 ref：同正文 → 同 ref（幂等由构造保证）。"""
    digest = hashlib.sha256(prose.encode("utf-8")).hexdigest()[:8]
    return f"{ref}-r{digest}"


async def rewrite_chapter(db: AsyncSession, project, ref: str) -> dict:
    """重写：返回 {ok, ghost_ref, source_ref, stale_marked, unarchived}。

    拒绝：主线无此章（404/ghost 源 409）；无正文（409）。
    幂等：同正文再次重写返回既有旧稿 ref，不再改动 stale/解锁状态之外的任何数据
    （stale 置位与解锁重复执行均幂等）。
    """
    from fastapi import HTTPException

    rows = (await db.scalars(mainline_stmt(project.id).order_by(Chapter.ref))).all()
    src = next((c for c in rows if c.ref == ref), None)
    if src is None:
        # 主线查不到：区分不存在（404）与 ghost 源（409，旧稿不可再重写）
        stray = await chapter_repo.get_by_ref(db, project.id, ref)
        if stray is not None and stray.ghost_of:
            raise HTTPException(409, "旧稿支线章不可重写")
        raise HTTPException(404, "Chapter not found")

    prose = src.content.prose if src.content is not None else ""
    if not prose.strip():
        raise HTTPException(409, "本章还没有正文，无可重写")

    # ① 旧稿快照（内容寻址；已存在=既有旧稿，幂等返回）
    ghost_ref = ghost_ref_for(ref, prose)
    ghost = await chapter_repo.get_by_ref(db, project.id, ghost_ref)
    created = False
    if ghost is None:
        ghost = await chapter_repo.upsert(
            db,
            project.id,
            src.volume_id,
            chapter_no=src.chapter_no,
            ref=ghost_ref,
            title=src.title,
            status="archived",
            word_count=src.word_count,
            has_prose=True,
            archived_at=datetime.now(UTC),
        )
        await db.flush()
        db.add(ChapterContent(chapter_id=ghost.id, prose=prose))
        ghost.ghost_of = ref
        created = True

    # ② 归档章解锁回可写（重写流：作者接着在原文上改）
    unarchived = False
    if src.status == "archived":
        src.status = "writing" if src.has_prose else "outline"
        src.archived_at = None
        unarchived = True

    # ③ 下游主线章（有正文者）置「基于旧设定」
    src_key = (_vol_no(src.ref), src.chapter_no)
    stale_marked = 0
    for c in rows:
        if c.id == src.id:
            continue
        if (
            (_vol_no(c.ref), c.chapter_no) > src_key
            and c.has_prose
            and not c.stale
        ):
            c.stale = True
            stale_marked += 1

    await db.commit()
    return {
        "ok": True,
        "source_ref": ref,
        "ghost_ref": ghost_ref,
        "ghost_created": created,
        "unarchived": unarchived,
        "stale_marked": stale_marked,
    }
