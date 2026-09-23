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


async def create_chapter(db, project, volume_ref: str, title: str, fields: dict | None = None) -> dict:
    """卷内建章：定位卷 → MAX+1 → DB 行（空章纲）+ 计数同事务。

    c-chapter-plan-ai「排上」：`fields` 携带拆章五段（plot/challenge/ending/acts/stage），
    **同一事务**内经既有装配写回（store.apply_chapter_data，其不自行 commit）——
    不出现「章已建、关键剧情字段为空」的中间态；重复提交经 upsert 幂等（不冒 500）。
    """
    vol_no = int(strip_suffix(volume_ref).replace("vol-", ""))
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")

    # 主线末端门禁（c-chapter-plan-ai，与「在本卷新增一章」同一判据）：新章只能排在
    # 写作位所在卷**及其之后**——否则会插进主线中段（frontier 排队模型下永远轮不到写）。
    # 前端两个入口同判据置灰；这里是绕过 UI 时的兜底。
    from chapters.frontier import frontier_info

    front = (await frontier_info(db, project.id))["frontier"]
    if front is not None and vol.volume_no < front["volume_no"]:
        raise HTTPException(
            409,
            f"写作位在第{front['volume_no']}卷——新章要排在写作位所在卷及其之后，"
            f"先去第{front['volume_no']}卷拆章",
        )

    chapter_no = await chapter_repo.max_chapter_no(db, project.id, vol.id) + 1
    ref = f"vol-{vol.volume_no}-ch-{chapter_no}"

    row = await chapter_repo.upsert(
        db, project.id, vol.id, chapter_no=chapter_no, ref=ref,
        title=title, status="outline", word_count=0, has_prose=False,
        outline_status="unfilled",
    )
    vol.chapter_count += 1
    project.total_chapters += 1
    if fields:
        # 排上：五段与建章同一事务写入（复用既有装配，不新写标量路径）
        # upsert 返回的是新插入行——先 refresh 预载 selectin 关系，
        # 否则装配内的关系访问会在同步上下文触发懒加载（MissingGreenlet）。
        await db.refresh(row)
        from chapters.store import apply_chapter_data

        # 键路径与章档案一致：summary 在 outline 内；challenge/chapter_acts/plot_stage/ladder_exit 在顶层
        payload = {
            "outline": {"summary": (fields.get("plot") or "").strip() or None},
            "challenge": (fields.get("challenge") or "").strip() or None,
            "ladder_exit": (fields.get("ending") or "").strip() or None,
            "chapter_acts": fields.get("acts") or None,
            "plot_stage": (fields.get("stage") or "").strip() or None,
        }
        clean = {k: v for k, v in payload.items() if v and not (k == "outline" and not v.get("summary"))}
        await apply_chapter_data(db, row, clean)
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


async def resplit_volume(db, project, volume_ref: str) -> dict:
    """重拆整卷（c-chapter-plan-ai D14）：清掉本卷**拟定章**（无正文未归档），
    供作者重新拆章；有正文/已归档的章一律保留。

    按章号**降序**逐章删——每步都满足「尾章＋拟定＋无正文」单章守卫（不留章号空洞）。
    卷级级联删除不受单章守卫约束（既有语义），此处走单章路径故必须守序。
    """
    from repositories import chapter_repo

    vol_no = int(strip_suffix(volume_ref).replace("vol-", ""))
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")
    rows = [
        c for c in await chapter_repo.list_by_volume(db, vol.id) if not c.ghost_of
    ]
    removable = [
        c for c in rows if c.status == "outline" and not c.has_prose
    ]
    kept = [c.ref for c in rows if c not in removable]
    removed: list[str] = []
    for row in sorted(removable, key=lambda c: c.chapter_no, reverse=True):
        await chapter_repo.delete(db, row.id)
        vol.chapter_count = max(0, vol.chapter_count - 1)
        project.total_chapters = max(0, (project.total_chapters or 0) - 1)
        removed.append(row.ref)
    await db.commit()
    logger.info("resplit volume %s: removed %d chapters", volume_ref, len(removed))
    return {"ok": True, "removed": removed, "kept": kept}
