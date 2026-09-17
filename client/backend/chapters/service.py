"""ChapterService — 章族 CRUD 全量走 DB（PR② 数据全量入库）。

- create_chapter：卷内建章（MAX+1）→ DB 行 + 计数同事务；不再写章 YAML 模板。
- save_chapter / save_prose：委托 chapters.store 统一写入口
  （拆装落库 + word_count/has_prose/outline_status 派生 + 版本快照）。
- get_chapter_row：纯 DB 元数据读（行缺失返回 None，无文件自愈）。
- 删章落盘产物清理已废：归档/提示词随章行 FK CASCADE（PR④）。
"""

import logging

from fastapi import HTTPException

from repositories import chapter_repo, volume_repo
from workflow.engine import strip_suffix

logger = logging.getLogger("uvicorn.error")


def _parse_chapter_ref(ref: str) -> tuple[int, int]:
    """`vol-N-ch-M` → (N, M)；容 `.yaml` 尾缀；不匹配抛 400。"""
    ref = strip_suffix(ref)
    parts = ref.split("-")
    if len(parts) != 4 or parts[0] != "vol" or parts[2] != "ch":
        raise HTTPException(400, f"Invalid chapter reference: {ref}")
    try:
        return int(parts[1]), int(parts[3])
    except ValueError:
        raise HTTPException(400, f"Invalid chapter reference: {ref}")


async def create_chapter(db, project, volume_ref: str, title: str) -> dict:
    """卷内建章：定位卷 → MAX+1 → DB 行（空章纲）+ 计数同事务。"""
    vol_no = int(strip_suffix(volume_ref).replace("vol-", ""))
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")

    chapter_no = await chapter_repo.max_chapter_no(db, project.id, vol.id) + 1
    ref = f"vol-{vol.volume_no}-ch-{chapter_no}"

    await chapter_repo.upsert(
        db, project.id, vol.id, chapter_no=chapter_no, ref=ref,
        title=title, status="outline", word_count=0, has_prose=False,
        outline_status="unfilled",
    )
    vol.chapter_count += 1
    project.total_chapters += 1
    await db.commit()
    logger.info("created chapter %s for project %s", ref, project.id)

    return {"chapter_ref": ref, "ref": ref}


async def save_chapter(db, project, ref: str, data: dict) -> None:
    """统一写入口委托：拆装落库 + 元数据派生 + 版本快照。"""
    from chapters.store import save_chapter as store_save

    await store_save(project.root_path, ref, data)


async def save_prose(db, project, ref: str, prose: str) -> None:
    """编辑器自动保存专用：只更 prose，走同一统一写入口。"""
    from chapters.store import load_chapter
    from chapters.store import save_chapter as store_save

    data = await load_chapter(project.root_path, ref)
    if not data:
        raise HTTPException(404, "Chapter not found")
    data["prose"] = prose
    await store_save(project.root_path, ref, data)


async def get_chapter_row(db, project, ref: str) -> dict | None:
    """供 GET 合并返回的 DB 元数据（行即真相，无文件自愈）。"""
    row = await chapter_repo.get_by_ref(db, project.id, strip_suffix(ref))
    if row is None:
        return None
    return {
        "word_count": row.word_count,
        "outline_status": row.outline_status,
        "status": row.status,
        "has_prose": row.has_prose,
        "ghost_of": row.ghost_of,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
    }
