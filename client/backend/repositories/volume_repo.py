"""Volume repository — volumes 表 DB 查询层（development-plan §5.1）。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.project import Novel
from models.volume import Volume


async def list_by_project(db: AsyncSession, project_id: str) -> list[Volume]:
    stmt = (
        select(Volume)
        .where(Volume.project_id == project_id)
        .order_by(Volume.volume_no)
    )
    result = await db.scalars(stmt)
    return list(result.all())


def _parse_volume_no(ref_or_no) -> int | None:
    """容 `.yaml` 尾缀：`vol-1` / `vol-1.yaml` / `1` → 卷号；无法解析返 None。"""
    if isinstance(ref_or_no, int):
        return ref_or_no
    s = str(ref_or_no)
    s = s.removesuffix(".yaml")
    s = s.removeprefix("vol-")
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


async def get_by_ref_or_number(
    db: AsyncSession, project_id: str, ref_or_no
) -> Volume | None:
    vol_no = _parse_volume_no(ref_or_no)
    if vol_no is None:
        return None
    return await get_by_volume_no(db, project_id, vol_no)


async def get_by_volume_no(
    db: AsyncSession, project_id: str, volume_no: int
) -> Volume | None:
    stmt = select(Volume).where(
        Volume.project_id == project_id, Volume.volume_no == volume_no
    )
    return await db.scalar(stmt)


async def get_outline_by_root(
    db: AsyncSession, root_path: str, volume_no: int
) -> str:
    """AI 生成链路（仅持有 root_path）取卷纲装配文本（卷视图换代素材单源）。

    载入 Volume（selectinload plot_nodes）后交 volumes/render 装配；卷缺失返回空串。
    """
    from volumes.render import volume_outline_text

    stmt = (
        select(Volume)
        .join(Novel, Volume.project_id == Novel.id)
        .where(Novel.root_path == root_path, Volume.volume_no == volume_no)
    )
    vol = await db.scalar(stmt)
    if vol is None:
        return ""
    return volume_outline_text(vol)


async def max_volume_no(db: AsyncSession, project_id: str) -> int:
    stmt = select(func.max(Volume.volume_no)).where(Volume.project_id == project_id)
    return await db.scalar(stmt) or 0


async def upsert(
    db: AsyncSession,
    project_id: str,
    volume_no: int,
    *,
    title: str,
    summary: str = "",
) -> Volume:
    """按 UNIQUE(project_id, volume_no) 找，缺则 insert；flush 但不 commit（交调用方事务）。"""
    row = await get_by_volume_no(db, project_id, volume_no)
    if row is not None:
        if title and title != row.title:
            row.title = title
        if summary and summary != row.summary:
            row.summary = summary
        return row
    row = Volume(
        project_id=project_id,
        volume_no=volume_no,
        title=title,
        summary=summary,
    )
    db.add(row)
    await db.flush()
    return row


async def count_by_project(db: AsyncSession, project_id: str) -> int:
    stmt = select(func.count(Volume.id)).where(Volume.project_id == project_id)
    return await db.scalar(stmt) or 0


async def ensure_volume_row(
    db: AsyncSession,
    project_id: str,
    volume_no: int,
    *,
    title: str | None = None,
) -> Volume:
    """懒补统一收口：卷行缺失 → upsert 卷（title 兜底「导入卷 N」）再插章行。

    供章族双写与读路径自愈复用；行已存在直接返回。
    """
    row = await get_by_volume_no(db, project_id, volume_no)
    if row is not None:
        return row
    return await upsert(
        db, project_id, volume_no, title=title or f"导入卷 {volume_no}"
    )
