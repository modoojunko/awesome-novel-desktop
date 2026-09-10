"""VolumeService — 卷族 CRUD 全量走 DB（数据全量入库，无文件层）。

- list_volumes：DB 查询全量卷+章树元数据（含 has_prose/outline_status/archived）。
- create_volume：MAX(volume_no)+1 + tier_or_gate + DB 行（唯一存储，失败即 500 不降级）。
- get_volume：卷行标量 + 4 张卷纲子表 + 章列表（Chapter 行）组装详情。
- update_volume：标量按传入键更新；子表传入即整体替换；Pydantic 已做四档长度校验。
- delete_volume：删 DB 行（CASCADE 删章行/卷纲子表/版本快照/归档/提示词）+ 清残留章 YAML（PR⑤ 前仍是文件）+ 计数维护。
"""

import logging
from collections import defaultdict

from fastapi import HTTPException

from repositories import chapter_repo, volume_repo
from volumes.schemas import VolumeUpdate
from workflow.engine import strip_suffix, update_phase
from workflow.gates import gate_settings_complete
from workflow.tier import tier_or_gate

logger = logging.getLogger("uvicorn.error")


async def list_volumes(db, project) -> list[dict]:
    """DB 全量树：一次拉卷 + 章，内存按 volume_id 分组（免 N+1）。"""
    vols = await volume_repo.list_by_project(db, project.id)
    chapters = await chapter_repo.list_by_project(db, project.id)
    by_vol: dict[str, list] = defaultdict(list)
    for c in chapters:
        by_vol[c.volume_id].append(c)

    result = []
    for v in vols:
        chs = by_vol.get(v.id, [])
        result.append(
            {
                "ref": f"vol-{v.volume_no}",
                "title": v.title,
                "summary": v.summary,
                "chapter_count": v.chapter_count,
                "chapters": [
                    {
                        "ref": c.ref,
                        "volume": v.volume_no,
                        "chapter": c.chapter_no,
                        "title": c.title,
                        "status": c.status,
                        "word_count": c.word_count,
                        "has_prose": c.has_prose,
                        "outline_status": c.outline_status,
                        "archived": c.status == "archived",
                    }
                    for c in sorted(chs, key=lambda x: x.chapter_no)
                ],
            }
        )
    return result


async def create_volume(
    db, project, *, title: str, summary: str = ""
) -> dict:
    """MAX+1（忽略 body.vol_num）+ tier 门控 + DB 行 + 计数自增。"""
    vol_no = await volume_repo.max_volume_no(db, project.id) + 1
    result = await tier_or_gate(
        db, project, gate_settings_complete, project.root_path, project.id
    )
    if result.hard_block and not result.valid:
        raise HTTPException(400, f"Settings incomplete: {result.warnings}")

    update_phase(project, "outline")
    await volume_repo.upsert(db, project.id, vol_no, title=title, summary=summary)
    project.total_volumes += 1
    await db.commit()
    logger.info("created volume %s for project %s", vol_no, project.id)

    return {"vol_num": vol_no, "ref": f"vol-{vol_no}"}


# 组装详情时输出的卷纲标量键（None 的不输出，保持响应干净）
_DETAIL_SCALARS = [
    "direction_method",
    "template_name",
    "core_conflict",
    "emotional_arc",
    "arc_mode",
    "primary_drive",
    "info_gap_start",
    "info_gap_end",
    "chapter_target",
]


async def get_volume(db, project, ref: str) -> dict | None:
    """卷详情组装：标量 + 卷纲四族子表 + 章列表；{ref} 容 .yaml 尾缀。"""
    vol_no = int(strip_suffix(ref).replace("vol-", ""))
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        return None

    data: dict = {
        "ref": f"vol-{vol_no}",
        "volume": vol.volume_no,
        "title": vol.title,
        "summary": vol.summary,
    }
    for key in _DETAIL_SCALARS:
        value = getattr(vol, key)
        if value is not None:
            data[key] = value
    data["stages"] = [
        {
            "stage_name": s.stage_name,
            "stage_function": s.stage_function,
            "chapter_count": s.chapter_count,
        }
        for s in vol.stages
    ]
    data["conflict_ladders"] = [
        {
            "layer_no": l.layer_no,
            "chapters_range": l.chapters_range,
            "obstacle": l.obstacle,
            "turning_type": l.turning_type,
            "turning_point": l.turning_point,
        }
        for l in vol.conflict_ladders
    ]
    data["chapter_plans"] = [
        {
            "chapter_no": p.chapter_no,
            "title": p.title,
            "summary": p.summary,
            "emotional_anchor": p.emotional_anchor,
            "info_gap": p.info_gap,
            "arc_position": p.arc_position,
        }
        for p in vol.chapter_plans
    ]
    data["character_voices"] = [
        {
            "character_name": v.character_name,
            "situation": v.situation,
            "unfinished": v.unfinished,
            "interlude_thought": v.interlude_thought,
            "next_action": v.next_action,
        }
        for v in vol.character_voices
    ]

    data["chapters"] = [
        {
            "ref": c.ref,
            "volume": vol.volume_no,
            "chapter": c.chapter_no,
            "title": c.title,
            "status": c.status,
            "word_count": c.word_count,
            "has_prose": c.has_prose,
            "outline_status": c.outline_status,
            "archived": c.status == "archived",
        }
        for c in await chapter_repo.list_by_volume(db, vol.id)
    ]
    return data


def _replace_children(vol, body: VolumeUpdate) -> None:
    """子表整体替换：传入即删旧插新（sort_order 按列表序 0 起）。"""
    from models.volume import (
        VolumeChapterPlan,
        VolumeCharacterVoice,
        VolumeConflictLadder,
        VolumeStage,
    )

    if body.stages is not None:
        vol.stages = [
            VolumeStage(
                sort_order=i,
                stage_name=s.stage_name,
                stage_function=s.stage_function,
                chapter_count=s.chapter_count,
            )
            for i, s in enumerate(body.stages)
        ]
    if body.conflict_ladders is not None:
        vol.conflict_ladders = [
            VolumeConflictLadder(
                sort_order=i,
                layer_no=l.layer_no,
                chapters_range=l.chapters_range,
                obstacle=l.obstacle,
                turning_type=l.turning_type,
                turning_point=l.turning_point,
            )
            for i, l in enumerate(body.conflict_ladders)
        ]
    if body.chapter_plans is not None:
        vol.chapter_plans = [
            VolumeChapterPlan(
                sort_order=i,
                chapter_no=p.chapter_no,
                title=p.title,
                summary=p.summary,
                emotional_anchor=p.emotional_anchor,
                info_gap=p.info_gap,
                arc_position=p.arc_position,
            )
            for i, p in enumerate(body.chapter_plans)
        ]
    if body.character_voices is not None:
        vol.character_voices = [
            VolumeCharacterVoice(
                sort_order=i,
                character_name=v.character_name,
                situation=v.situation,
                unfinished=v.unfinished,
                interlude_thought=v.interlude_thought,
                next_action=v.next_action,
            )
            for i, v in enumerate(body.character_voices)
        ]


async def update_volume(db, project, ref: str, body: VolumeUpdate) -> dict:
    """标量按传入键更新（None 跳过）；子表传入即整体替换。"""
    vol_no = int(strip_suffix(ref).replace("vol-", ""))
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")

    for key in _DETAIL_SCALARS:
        value = getattr(body, key)
        if value is not None:
            setattr(vol, key, value)
    if body.title is not None:
        vol.title = body.title
    if body.summary is not None:
        vol.summary = body.summary
    # 先清旧子行并 flush（flush 内插入先于删除，会撞 UNIQUE(volume_id, sort_order)）
    for _attr in ("stages", "conflict_ladders", "chapter_plans", "character_voices"):
        if getattr(body, _attr) is not None:
            getattr(vol, _attr).clear()
    await db.flush()
    _replace_children(vol, body)
    await db.commit()
    return {"ok": True}


async def delete_volume(db, project, ref: str) -> dict:
    """删 DB 行（CASCADE 删章行/卷纲子表/版本快照/归档/提示词）→ 计数维护。"""
    vol_no = int(strip_suffix(ref).replace("vol-", ""))
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)

    deleted_chapters = 0
    if vol is not None:
        deleted_chapters = await chapter_repo.count_by_volume(db, vol.id)
        await db.delete(vol)  # ORM cascade 删章行 + 卷纲子表（FK CASCADE 双保险）
    project.total_volumes = max(0, (project.total_volumes or 0) - 1)
    project.total_chapters = max(0, (project.total_chapters or 0) - deleted_chapters)
    await db.commit()
    return {"ok": True}
