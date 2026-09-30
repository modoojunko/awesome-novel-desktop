"""chapter_prompts 表读写 — PR④ 数据全量入库。

替代 prompts/{ref}-{name}.md 落盘。name 形如 "seg-1-prompt" / "write-prompt"，
对外文件名 {ref}-{name}.md 由调用方派生（前端零改动）。
"""

from sqlalchemy import select

from chapters.store import _get_chapter_by_root
from db import async_session
from models.archive import ChapterPrompt


def _fit_name(name: str) -> str:
    return str(name)[:200]


async def save_prompt(root_path: str, chapter_ref: str, name: str, content: str) -> None:
    """按 (章, name) upsert 一条提示词；章行缺失静默跳过（对齐文件时代不抛错）。"""
    from workflow.engine import strip_suffix

    ref = strip_suffix(chapter_ref)
    async with async_session() as session:
        ch_row = await _get_chapter_by_root(session, root_path, ref)
        if ch_row is None:
            return
        row = await session.scalar(
            select(ChapterPrompt).where(
                ChapterPrompt.chapter_id == ch_row.id,
                ChapterPrompt.name == _fit_name(name),
            )
        )
        if row is None:
            session.add(
                ChapterPrompt(
                    chapter_id=ch_row.id,
                    name=_fit_name(name),
                    content=content,
                )
            )
        else:
            row.content = content
        await session.commit()


async def load_prompt(root_path: str, chapter_ref: str, name: str) -> str:
    """读单条提示词；缺失返回空串（提示词行 content 即正文，无文件语义）。"""
    from workflow.engine import strip_suffix

    ref = strip_suffix(chapter_ref)
    async with async_session() as session:
        ch_row = await _get_chapter_by_root(session, root_path, ref)
        if ch_row is None:
            return ""
        row = await session.scalar(
            select(ChapterPrompt).where(
                ChapterPrompt.chapter_id == ch_row.id,
                ChapterPrompt.name == _fit_name(name),
            )
        )
        return row.content if row is not None else ""
