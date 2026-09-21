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

from filesystem.storage import get_storage
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
                # 卷的验证卡（volume-plan-ai）：写作默认页右栏一行「卷号 · 名字 · 章数目标」
                "chapter_target": v.chapter_target,
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
    db, project, *, title: str, summary: str = "",
    core_conflict: str = "", ending: str = "",
    antagonist_type: str | None = None, antagonist_line: str = "",
    chapter_target: int | None = None,
) -> dict:
    """MAX+1（忽略 body.vol_num）+ tier 门控 + DB 行 + 计数自增。

    四问＋章数一次写入（c-volume-antagonist：抽卡确认与免费「直接创建」共用）；
    卷名可空——**服务端兜底「第N卷」**（VolumeCreate.title 已放宽为空，别再依赖调用方兜底）。
    """
    vol_no = await volume_repo.max_volume_no(db, project.id) + 1
    title = (title or "").strip() or f"第{vol_no}卷"
    result = await tier_or_gate(
        db, project, gate_settings_complete, project.root_path, project.id
    )
    if result.hard_block and not result.valid:
        raise HTTPException(400, f"Settings incomplete: {result.warnings}")

    update_phase(project, "outline")
    vol = await volume_repo.upsert(db, project.id, vol_no, title=title, summary=summary)
    vol.core_conflict = core_conflict
    vol.ending = ending
    vol.antagonist_type = antagonist_type or None
    vol.antagonist_line = antagonist_line
    vol.chapter_target = chapter_target
    project.total_volumes += 1
    await db.commit()
    logger.info("created volume %s for project %s", vol_no, project.id)

    return {"vol_num": vol_no, "ref": f"vol-{vol_no}"}


# 组装详情时输出的卷纲标量键（None 的不输出，保持响应干净）
_DETAIL_SCALARS = [
    "core_conflict",
    "ending",
    "chapter_target",
    "antagonist_type",
    "antagonist_line",
]


def _split_lines(value: str | None) -> list[str]:
    """TEXT 一行一条列 → list[str]（读回契约；复用 schemas 归一保单语义）。"""
    from volumes.schemas import normalize_line_list

    return normalize_line_list([value or ""])


async def _aggregate_cast(db, vol) -> list[dict]:
    """卷角色聚合（只读视图）：卷下各**主线章**章纲出场角色合集（去重保序、主角置顶）。

    - 空态＝无章即空；主角只在聚合集里出现时置顶（不凭空入列——评审拍板）；
    - 旧稿支线章（ghost_of 非空）不参与（与同一响应的 chapters 口径一致）；
    - 名字在 antagonist_line 中命中者标反派；行形状 {name, role}；
    - 一条 JOIN 取全（旧实现逐章一条 SELECT：200 章 ≈ 200 条语句，导出链再乘卷数）。
    """
    from sqlalchemy import select

    from models.chapter import Chapter, ChapterCharacter
    from models.character import Character

    rows = await db.execute(
        select(ChapterCharacter.character_name)
        .join(Chapter, Chapter.id == ChapterCharacter.chapter_id)
        .where(Chapter.volume_id == vol.id, Chapter.ghost_of.is_(None))
        .order_by(Chapter.chapter_no, ChapterCharacter.sort_order)
    )
    names: list[str] = []
    seen: set[str] = set()
    for (raw,) in rows.all():
        nm = (raw or "").strip()
        if nm and nm not in seen:
            seen.add(nm)
            names.append(nm)

    # 主角置顶：本卷聚合集里若含主角（role='主角'），排到最前
    protagonist = await db.scalar(
        select(Character.name).where(
            Character.novel_id == vol.project_id, Character.role == "主角"
        )
    )
    if protagonist and protagonist in seen:
        names = [protagonist] + [n for n in names if n != protagonist]

    ant_line = (vol.antagonist_line or "").strip()
    return [
        {"name": nm, "role": ("反派" if ant_line and nm in ant_line else "")}
        for nm in names
    ]


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
    # 规划台/卷纲表单「进场」行单源（事实优先：归档章收尾 > 上一卷预期结局 > 首卷全景起步）
    data["prev_ending"] = await resolve_prev_ending(db, project, vol.volume_no)
    # 旧 goal 并入卷末尾句（评审拍板：读侧合并，PUT 保存即固化；goal 不再独立回显）
    if getattr(vol, "goal", None):
        base = data.get("ending") or ""
        data["ending"] = (base + ("。 " if base else "") + vol.goal).strip()
    # 卷角色＝聚合视图（c-volume-antagonist）：卷下各章出场角色合集，无章即空
    data["cast_members"] = await _aggregate_cast(db, vol)
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
    from models.volume import VolumePlotNode

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
    # goal 一次性固化（检视 P1-3）：读侧把旧 goal 并进 ending 尾句，作者改完保存时把派生值
    # 写回 ending → 若不清 goal，下一次 GET 会再拼一遍（每保存一次长一节）。清列即幂等。
    if "ending" in fields_set and getattr(vol, "goal", None):
        vol.goal = None
    for key in _DETAIL_SCALARS:
        if key in fields_set:
            setattr(vol, key, getattr(body, key))
    if body.title is not None:
        vol.title = body.title
    if body.summary is not None:
        vol.summary = body.summary
    # 先清旧子行并 flush（flush 内插入先于删除，会撞 UNIQUE(volume_id, sort_order)）
    if body.plot_nodes is not None:
        vol.plot_nodes.clear()
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


async def resolve_prev_ending(
    db, project, vol_no: int, *, actual_first: bool = True
) -> dict:
    """进场材料：这一卷从上一卷的哪里接着写（事实优先）。

    - 有归档章：取上一卷最后一个归档章的章纲一句话（实际写到的收尾）。
    - 没写到：回落上一卷卷纲的「预期结局」（计划口径），来源说明里注明。
    - 首卷：取主线全景的起步（story.yaml.synopsis 前段）。
    返回 {"text", "source"}——text 给 prompt/界面，source 是来源说明（界面小字）。
    """
    storage = get_storage()
    if vol_no <= 1:
        story = await storage.read_yaml(project.root_path, "story.yaml") or {}
        arc = story.get("story_arc") or {}
        full = str(arc.get("fullstory", "") or "").strip()
        text = full[:120] if full else "（主线还没写起步——先去设定补主线）"
        return {"text": text, "source": "第一卷 · 来自主线全景的「他从哪起步」"}

    from repositories import chapter_repo

    prev = await volume_repo.get_by_volume_no(db, project.id, vol_no - 1)
    if prev is None:
        return {
            "text": "（上一卷不存在）",
            "source": f"第{vol_no - 1}卷 · 未找到",
        }

    archived = [
        c
        for c in await chapter_repo.list_by_volume(db, prev.id)
        if c.status == "archived" and not c.ghost_of
    ]
    if archived:
        last = max(archived, key=lambda c: c.chapter_no)
        text = (last.summary or "").strip() or last.title
        return {
            "text": text,
            "source": f"第{vol_no - 1}卷 · 实际收尾（第{last.chapter_no}章）——写到那里之后，这里以实际为准",
        }
    return {
        "text": (prev.ending or "").strip() or "（上一卷还没定收尾）",
        "source": f"第{vol_no - 1}卷 · 预期结局（还没写到，先按卷纲）",
    }
