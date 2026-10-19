"""A 路原子落库：书/卷/章/正文/import_token 单事务写入。

不复用 create_project / save_chapter（两者内部 commit）；失败整笔回滚，
重复 import_token 返回同一本书。正文按 manifest 的 body_ranges 从源文件切片。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import book_root
from deconstruct.textparse import count_chars, normalize_volume_title
from models.chapter import Chapter, ChapterContent
from models.import_session import ImportSession
from models.project import Novel
from models.volume import Volume
from novels.import_structure import active_chapters, validate_structure
from novels.service import slugify


class ImportSourceMismatch(ValueError):
    pass


def _subtract(
    start: int, end: int, cuts: list[list[int]]
) -> list[tuple[int, int]]:
    pieces = [(start, end)]
    for cut_start, cut_end in cuts:
        rest: list[tuple[int, int]] = []
        for a, b in pieces:
            if cut_end <= a or cut_start >= b:
                rest.append((a, b))
                continue
            if a < cut_start:
                rest.append((a, cut_start))
            if cut_end < b:
                rest.append((cut_end, b))
        pieces = rest
    return pieces


def slice_import_prose(
    text: str,
    ranges: list[list[int]],
    heading_ranges: list[list[int]] | None = None,
) -> str:
    """按 manifest 区间取正文；只剔除 manifest 精确登记的卷标题行区间。

    以前按「第X卷」正则逐行过滤，会把正文里恰好以「第一卷…」开头的短句静默删掉；
    现在卷标题由 parser 定位并冻结，正文切片不再二次猜。
    """
    cuts = [list(map(int, r)) for r in (heading_ranges or [])]
    chunks: list[str] = []
    for a, b in ranges:
        pieces = [
            text[start:end]
            for start, end in _subtract(int(a), int(b), cuts)
            if end > start
        ]
        if pieces:
            # 同一区间内的片段直接拼接（只删卷标题行，不额外加空行）；
            # 多个 body_range（章前序文＋正文）之间才补一个换行。
            chunks.append("".join(pieces))
    return "\n".join(chunks).strip()


async def _unique_slug(db: AsyncSession, user_id: str, name: str) -> str:
    base = slugify(name) or "imported"
    slug = base
    for _ in range(12):
        exists = await db.scalar(
            select(Novel.id).where(Novel.user_id == user_id, Novel.slug == slug)
        )
        if not exists:
            return slug
        slug = f"{base}-{uuid.uuid4().hex[:6]}"
    raise ValueError("无法生成唯一书名标识，请改名后重试")


async def persist_import(
    db: AsyncSession,
    *,
    user_id: str,
    name: str,
    session: ImportSession,
    structure: list,
    import_token: str,
    excluded_source_nos: list[int] | None = None,
) -> Novel:
    if not (import_token or "").strip():
        raise ValueError("缺少导入令牌，请重试")

    manifest = json.loads(session.manifest_json)
    active = active_chapters(manifest, excluded_source_nos)
    normalized = validate_structure(structure, len(active))
    volume_headings = manifest.get("volume_heading_ranges") or []

    with open(session.source_path, "rb") as f:
        raw = f.read()
    if hashlib.sha256(raw).hexdigest() != session.source_sha256:
        raise ImportSourceMismatch("源文件已变化，请重新解析后再导入")
    text = raw.decode(session.encoding or manifest["encoding"])

    try:
        async with db.begin():
            existing = await db.scalar(
                select(Novel).where(Novel.import_token == import_token)
            )
            if existing is not None:
                if existing.user_id != user_id:
                    raise ValueError("导入令牌已被使用")
                return existing

            slug = await _unique_slug(db, user_id, name)
            now = datetime.now(UTC).replace(tzinfo=None)
            book = Novel(
                user_id=user_id,
                name=name.strip() or "未命名作品",
                slug=slug,
                root_path=book_root(slug),
                source="import",
                import_kind="direct",
                import_token=import_token,
                current_phase="settings",
                total_volumes=len(normalized),
                total_chapters=len(active),
            )
            db.add(book)
            await db.flush()

            for vi, vol in enumerate(normalized, start=1):
                vol_name = normalize_volume_title(vol["title"])
                # 只存卷名；显示层统一拼「第N卷 · 卷名」，避免重复序号。
                vol_title = vol_name
                start = int(vol["chapter_from"])
                end = int(vol["chapter_to"])
                vol_row = Volume(
                    project_id=book.id,
                    volume_no=vi,
                    title=vol_title,
                    summary="",
                    chapter_count=end - start + 1,
                )
                db.add(vol_row)
                await db.flush()
                for ci, active_idx in enumerate(range(start, end + 1), start=1):
                    mch = active[active_idx - 1]
                    prose = slice_import_prose(
                        text, mch["body_ranges"], volume_headings
                    )
                    ch = Chapter(
                        project_id=book.id,
                        volume_id=vol_row.id,
                        chapter_no=ci,
                        ref=f"vol-{vi}-ch-{ci}",
                        title=str(mch.get("title") or ""),
                        status="draft",
                        origin="import",
                        imported_at=now,
                        word_count=count_chars(prose),
                        has_prose=bool(prose),
                        outline_status="unfilled",
                    )
                    ch.content = ChapterContent(prose=prose)
                    db.add(ch)
            # commit 由 async with db.begin() 收口
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(select(Novel).where(Novel.import_token == import_token))
        if existing is not None and existing.user_id == user_id:
            return existing
        raise

    return book
