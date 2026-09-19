"""VolumeService — 卷族 CRUD 全量走 DB（数据全量入库，无文件层）。

- list_volumes：DB 查询全量卷+章树元数据（含 has_prose/outline_status/archived）。
- create_volume：MAX(volume_no)+1 + tier_or_gate + DB 行（唯一存储，失败即 500 不降级）。
- get_volume：卷行标量 + 登场人物/剧情节点行集 + 主线章列表（含 outline_summary/ghost_count）。
- update_volume：显式传入键才写（fields_set，显式 null/[] 即清空）；行集传入即整体替换。
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
    # revert-ghost：支线章不入主线卷章数组（经 GET /ghosts 单独返回）
    mainline = [c for c in chapters if not c.ghost_of]
    by_vol: dict[str, list] = defaultdict(list)
    for c in mainline:
        by_vol[c.volume_id].append(c)

    result = []
    for v in vols:
        chs = by_vol.get(v.id, [])
        result.append(
            {
                "ref": f"vol-{v.volume_no}",
                "title": v.title,
                "summary": v.summary,
                # 章数以主线实测为准（缓存列在旧稿支线存在时不代表主线章数）
                "chapter_count": len(chs),
                "chapters": [
                    {
                        "id": c.id,  # DB 章 id（foreshadow-settings-v2：伏笔选择器按 id 引用章）
                        "ref": c.ref,
                        "volume": v.volume_no,
                        "chapter": c.chapter_no,
                        "title": c.title,
                        "status": c.status,
                        "word_count": c.word_count,
                        "has_prose": c.has_prose,
                        "outline_status": c.outline_status,
                        "archived": c.status == "archived",
                        # chapter-rewrite：基于旧设定角标（主线章自身状态列）
                        "stale": bool(c.stale),
                    }
                    for c in sorted(chs, key=lambda x: x.chapter_no)
                ],
            }
        )
    return result


async def list_ghosts(db, project) -> list[dict]:
    """旧稿支线章（revert-ghost / chapter-rewrite）：脱离主线的章，只读保留。"""
    import re as _re

    ghosts = await chapter_repo.list_by_project(db, project.id)
    return [
        {
            "id": c.id,
            "ref": c.ref,
            "volume": _vol_no_of(c),
            "chapter": c.chapter_no,
            "title": c.title,
            "word_count": c.word_count,
            "ghost_of": c.ghost_of,
            # origin：重写旧稿＝内容寻址后缀（-r{8hex}），其余为回退转入
            "origin": "rewrite"
            if _re.match(r"^.*-r[0-9a-f]{8}$", c.ref or "")
            else "revert",
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in sorted(
            (g for g in ghosts if g.ghost_of),
            key=lambda x: (x.ghost_of or "", x.chapter_no),
        )
    ]


def _vol_no_of(c) -> int:
    import re as _re

    m = _re.match(r"^vol-(\d+)-ch-", c.ref or "")
    return int(m.group(1)) if m else 0


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
    "template_name",
    "core_conflict",
    "goal",
    "ending",
    "chapter_target",
]


def _split_lines(value: str | None) -> list[str]:
    """TEXT 一行一条列 → list[str]（读回契约；复用 schemas 归一保单语义）。"""
    from volumes.schemas import normalize_line_list

    return normalize_line_list([value or ""])


async def get_volume(db, project, ref: str) -> dict | None:
    """卷详情组装：标量 + 登场人物/剧情节点行集 + 主线章列表；{ref} 容 .yaml 尾缀。"""
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
    data["plants"] = _split_lines(vol.plants)
    data["reveals"] = _split_lines(vol.reveals)
    data["cast_members"] = [
        {"who": m.who, "target": m.target, "change": m.change}
        for m in vol.cast_members
    ]
    data["plot_nodes"] = [
        {"stage": n.stage, "text": n.text}
        for n in vol.plot_nodes
    ]

    all_chapters = await chapter_repo.list_by_volume(db, vol.id)
    mainline = [c for c in all_chapters if not c.ghost_of]
    # 旧稿支线不入台账与计数，仅以 ghost_count 汇总（卷视图提示「旧稿支线 N 章」）
    data["ghost_count"] = len(all_chapters) - len(mainline)
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
            # 本卷章节台账「章纲一句话」（Chapter.summary 随章纲落库）
            "outline_summary": (c.summary or "").strip(),
        }
        for c in sorted(mainline, key=lambda x: x.chapter_no)
    ]
    return data


def _replace_children(vol, body: VolumeUpdate) -> None:
    """子表整体替换：传入即删旧插新（sort_order 按列表序 0 起）。"""
    from models.volume import VolumeCastMember, VolumePlotNode

    if body.cast_members is not None:
        vol.cast_members = [
            VolumeCastMember(
                sort_order=i,
                who=m.who,
                target=m.target,
                change=m.change,
            )
            for i, m in enumerate(body.cast_members)
        ]
    if body.plot_nodes is not None:
        vol.plot_nodes = [
            VolumePlotNode(
                sort_order=i,
                stage=n.stage,
                text=n.text,
            )
            for i, n in enumerate(body.plot_nodes)
        ]


async def update_volume(db, project, ref: str, body: VolumeUpdate) -> dict:
    """显式传入的键才写（fields_set 判定，显式 null/[] 即清空）；行集传入即整体替换。"""
    vol_no = int(strip_suffix(ref).replace("vol-", ""))
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")

    fields_set = body.model_fields_set
    for key in _DETAIL_SCALARS:
        if key in fields_set:
            setattr(vol, key, getattr(body, key))
    for key in ("plants", "reveals"):
        if key in fields_set:
            setattr(vol, key, "\n".join(getattr(body, key) or []))
    if body.title is not None:
        vol.title = body.title
    if body.summary is not None:
        vol.summary = body.summary
    # 先清旧子行并 flush（flush 内插入先于删除，会撞 UNIQUE(volume_id, sort_order)）
    for _attr in ("cast_members", "plot_nodes"):
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
