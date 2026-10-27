"""重写这一章（chapter-rewrite）：归档章解锁回可写＋下游「基于旧设定」置位。

设计要点（c-rewrite-ghost-retire 后的形态）：
- **旧稿不再转存支线**：重写前正文必然已有版本快照（每次正文实质落库即写
  chapter_versions——保存/导入同源；重写前那份是当时最新一条，恢复入口＝
  正文页签「版本历史」）。左栏旧稿支线分组只服务回退（revert-ghost）。
- **stale 是章自身的列**：重写事务把源章之后的主线章（有正文者）置 stale=True；
  本章自身被写（正文/章纲保存）时由单写入口（chapters/store.save_chapter）清除。
  不做时间戳派生（updated_at 条件触发不可靠）。
- **合成事务**：归档章解锁 + 下游置位一次提交；失败全败。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from chapters.frontier import _vol_no
from chapters.scope import mainline_stmt
from models.chapter import Chapter
from repositories import chapter_repo


async def rewrite_chapter(db: AsyncSession, project, ref: str) -> dict:
    """重写：返回 {ok, source_ref, unarchived, stale_marked, dossier_*}。

    拒绝：主线无此章（404/ghost 源 409）；无正文（409）。
    """
    from fastapi import HTTPException

    rows = (await db.scalars(mainline_stmt(project.id).order_by(Chapter.ref))).all()
    src = next((c for c in rows if c.ref == ref), None)
    if src is None:
        # 主线查不到：区分不存在（404）与 ghost 源（409，支线章不可重写）
        stray = await chapter_repo.get_by_ref(db, project.id, ref)
        if stray is not None and stray.ghost_of:
            raise HTTPException(409, "旧稿支线章不可重写")
        raise HTTPException(404, "Chapter not found")

    prose = src.content.prose if src.content is not None else ""
    if not prose.strip():
        raise HTTPException(409, "本章还没有正文，无可重写")

    # ① 归档章解锁回可写（重写流：作者接着在原文上改）
    unarchived = False
    if src.status == "archived":
        src.status = "writing" if src.has_prose else "outline"
        src.archived_at = None
        unarchived = True

    # ② 下游主线章（有正文者）置「基于旧设定」
    # ③ 章档级联（c-chapter-dossier）：同事务——源章四域行清空（重归档整体重提、
    # 源章 dossier_stale 复位）；下游**已有章档行**的章置 dossier_stale（无行不标，
    # 防「章档待更新」角标出现在从未提取过的章上）
    src_key = (_vol_no(src.ref), src.chapter_no)
    stale_marked = 0
    dossier_stale_marked = 0
    for c in rows:
        if c.id == src.id:
            continue
        if (_vol_no(c.ref), c.chapter_no) > src_key and c.has_prose:
            if not c.stale:
                c.stale = True
                stale_marked += 1
            has_dossier = bool(
                c.dossier_settings or c.dossier_relations
                or c.dossier_items or c.dossier_knowledge
            )
            if has_dossier and not c.dossier_stale:
                c.dossier_stale = True
                dossier_stale_marked += 1

    from sqlalchemy import select

    from models.chapter import (
        ChapterItemChange,
        ChapterKnowledgeChange,
        ChapterRelationChange,
        ChapterSettingChange,
    )

    dossier_rows_cleared = 0
    for model in (
        ChapterSettingChange, ChapterRelationChange,
        ChapterItemChange, ChapterKnowledgeChange,
    ):
        for row in await db.scalars(
            select(model).where(model.chapter_id == src.id)
        ):
            await db.delete(row)
            dossier_rows_cleared += 1
    src.dossier_stale = False

    await db.commit()
    return {
        "ok": True,
        "source_ref": ref,
        "unarchived": unarchived,
        "stale_marked": stale_marked,
        "dossier_rows_cleared": dossier_rows_cleared,
        "dossier_stale_marked": dossier_stale_marked,
    }
