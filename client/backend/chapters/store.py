"""章族存取 DB 心脏 — 表⇆JSON 组装/拆装（API JSON 结构不变，前端零改动）。

- load_chapter(root_path, ref)：DB 行 → 章全量 dict（outline/memo/emotional_design/
  scene_cards/knowledge_states/segments/prose），形态与 YAML 时代逐键一致。
- save_chapter(root_path, ref, data)：dict 拆装落库（标量+子表整体替换+正文 upsert），
  同事务派生 word_count/has_prose/status/outline_status；prose 或 outline.summary
  变化时写 versions YAML 快照（PR③ 切 DB），上限 MAX_VERSIONS_PER_CHAPTER。
- collect_prose_by_root(root_path)：全项目正文拼接（AI 回填语料）。

长度纪律：SQLite 不强制 VARCHAR 长度，写入侧 _fit() 截断到列宽
（用户输入由 router 层 Pydantic max_length 严校验拒收；AI 生成物截断安全）。
"""

import contextlib
import json
import logging
import re
import time

from sqlalchemy import select

from novels.service import count_chars
from workflow.engine import MAX_VERSIONS_PER_CHAPTER, strip_suffix

logger = logging.getLogger("uvicorn.error")

# 章纲标量列映射：(JSON 键, 列名, 列宽)
_OUTLINE_SCALARS = [
    ("summary", "summary", 300),
    ("location", "location", 200),
    ("time", "story_time", 150),
    ("narrative_pov", "narrative_pov", 50),
]
_EMOTIONAL_SCALARS = [
    ("primary_mood", "primary_mood", 50),
    ("mood_progression", "mood_progression", 300),
    ("intensity_peak", "intensity_peak", 300),
    ("intensity_level", "intensity_level", None),
    ("emotional_hook", "emotional_hook", 150),
]
_EXPECTATION_SCALARS = [
    ("state", "expectation_state", 150),
    ("strategy", "expectation_strategy", 50),
    ("detail", "expectation_detail", 300),
]

_KEY_POINT_TAG = re.compile(r"^\[([^\]]+)\](.*)$", re.DOTALL)


def _fit(value, width: int | None):
    """写入侧截断：None 直通；超宽截断（生成物截断安全，用户输入走 schema 拒收）。"""
    if value is None:
        return None
    s = str(value)
    if width is not None and len(s) > width:
        return s[:width]
    return s


def _parse_key_point(item: str) -> tuple[str, str]:
    """'[推进剧情·对话] 内容' → ('推进剧情·对话', '内容')；无标签 → ('', 原文)。"""
    m = _KEY_POINT_TAG.match(item or "")
    if m:
        return m.group(1).strip()[:50], m.group(2)
    return "", item or ""


def _format_key_point(tag: str, content: str) -> str:
    return f"[{tag}]{content}" if tag else content


def _split_labeled(item: str) -> tuple[str, str]:
    """'场景：功能' → ('场景', '功能')；无标签 → ('', 原文)。

    纯字符串切分（首个全/半角冒号）；标签空或超 50 字、冒号后为空则不拆。
    """
    s = (item or "").strip()
    positions = [i for i in (s.find("："), s.find(":")) if i != -1]
    if positions:
        idx = min(positions)
        label, rest = s[:idx].strip(), s[idx + 1 :].strip()
        if label and rest and len(label) <= 50:
            return label, rest
    return "", s


def _derive_outline_status(status: str, prose: str) -> str:
    if status == "confirmed":
        return "confirmed"
    if (prose or "").strip():
        return "in_progress"
    return "unfilled"


def _int_or_none(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_enum(value, allowed: set, width: int):
    """枚举列写入守卫：合法值截断落库，非法/空值置 None（读侧 ``or ""`` 语义不变）。"""
    if value is None:
        return None
    s = str(value).strip()
    if s not in allowed:
        return None
    return _fit(s, width)


# ── 组装：DB 行 → 章 JSON（形态对齐 YAML 时代）──────────────────────────────


def assemble_chapter(row) -> dict:
    """Chapter 行（selectin 已带子表/正文/卷）→ 全量章 dict。"""
    data: dict = {
        "volume": row.volume.volume_no,
        "chapter": row.chapter_no,
        "title": row.title,
        "status": row.status,
        "prose": row.content.prose if row.content is not None else "",
    }
    if row.word_target is not None:
        data["word_target"] = row.word_target
    if row.ladder_exit:
        data["ladder_exit"] = row.ladder_exit

    outline: dict = {
        "key_points": [_format_key_point(k.func_tag, k.content) for k in row.key_points],
        "characters": [c.character_name for c in row.characters],
    }
    for json_key, col, _w in _OUTLINE_SCALARS:
        outline[json_key] = getattr(row, col) or ""
    if row.perspective_guidance:
        outline["perspective_guidance"] = row.perspective_guidance
    data["outline"] = outline

    payoff: dict[str, list[str]] = {
        "must_resolve": [],
        "must_hold": [],
        "partial_advance": [],
    }
    for p in row.payoff_items:
        payoff.setdefault(p.kind, []).append(p.content)
    memo: dict = {
        "current_task": row.current_task or "",
        "reader_expectation": {
            json_key: getattr(row, col) or ""
            for json_key, col, _w in _EXPECTATION_SCALARS
        },
        "payoff_plan": payoff,
        "downtime_functions": [
            f"{d.scene}：{d.func}" if d.scene else d.func
            for d in row.downtime_functions
        ],
        "key_choices": [k.content for k in row.key_choices],
        "required_changes": [
            f"{c.change_type}：{c.content}" if c.change_type else c.content
            for c in row.required_changes
        ],
        "prohibitions": [p.content for p in row.prohibitions],
    }
    data["memo"] = memo

    emotional = {
        json_key: getattr(row, col)
        for json_key, col, _w in _EMOTIONAL_SCALARS
        if getattr(row, col) is not None
    }
    if emotional:
        data["emotional_design"] = emotional

    if row.scene_cards:
        data["scene_cards"] = [
            {
                "scene_name": s.scene_name,
                "goal": s.goal,
                "obstacle": s.obstacle,
                "hook": s.hook,
                **({"weight": s.weight} if s.weight else {}),
                **({"focus": s.focus} if s.focus else {}),
            }
            for s in row.scene_cards
        ]
    if row.micro_payoffs:
        data["micro_payoffs"] = [
            {
                "kind": m.kind,
                "description": m.description,
                "location": m.location,
            }
            for m in row.micro_payoffs
        ]
    if row.knowledge_states:
        data["knowledge_states"] = [
            {
                "character_name": k.character_name,
                "knows": k.knows,
                "unknowns": k.unknowns,
                "gap_relation": k.gap_relation,
                "gap_change": k.gap_change,
            }
            for k in row.knowledge_states
        ]

    data["segments"] = [_assemble_segment(s) for s in row.segments]
    return data


def _assemble_segment(s) -> dict:
    seg: dict = {"summary": s.summary or "", "target_words": s.target_words or 0}
    for key in ("what_to_write", "goal", "emotional_tone", "function"):
        value = getattr(s, key)
        if value:
            seg[key] = value
    if s.characters:
        seg["characters"] = [n.strip() for n in s.characters.split(",") if n.strip()]
    if s.word_target is not None:
        seg["word_target"] = s.word_target
    if s.seg_number is not None:
        seg["seg_number"] = s.seg_number
    return seg


# ── 拆装：章 JSON → DB 行（子表整体替换）───────────────────────────────────


def _disassemble_scalars(row, data: dict) -> None:
    outline = data.get("outline") or {}
    memo = data.get("memo") or {}
    emotional = data.get("emotional_design") or {}
    expectation = memo.get("reader_expectation") or {}

    for json_key, col, width in _OUTLINE_SCALARS:
        setattr(row, col, _fit(outline.get(json_key), width))
    row.perspective_guidance = _fit(outline.get("perspective_guidance"), 300)
    row.current_task = _fit(memo.get("current_task"), 300)
    for json_key, col, width in _EXPECTATION_SCALARS:
        setattr(row, col, _fit(expectation.get(json_key), width))
    for json_key, col, width in _EMOTIONAL_SCALARS:
        setattr(row, col, _fit(emotional.get(json_key), width))
    row.word_target = _int_or_none(data.get("word_target"))
    row.ladder_exit = _fit(data.get("ladder_exit"), 300)


_CHILD_ATTRS = (
    "key_points", "characters", "payoff_items", "downtime_functions",
    "key_choices", "required_changes", "prohibitions",
    "scene_cards", "micro_payoffs", "knowledge_states", "segments",
)

# 场景卡权重/焦点的合法值（越界值置空，防脏数据进提示词）
_SCENE_WEIGHTS = {"high", "mid", "low"}
_SCENE_FOCUS = {"核心冲突", "人物情绪", "信息差"}


async def _resolve_names(session, project_id: str, names: list[str]) -> dict[str, str]:
    """名字/别名 → 角色 id（character-settings-v2）。

    精确名命中优先，别名兜底；未命中的名字不在返回 map 里（调用方落快照 + 告警）。
    """
    from models.character import Character

    if not names:
        return {}
    cards = (
        await session.scalars(
            select(Character).where(Character.novel_id == project_id)
        )
    ).all()
    by_name = {c.name: c.id for c in cards if c.name}
    by_alias: dict[str, str] = {}
    for c in cards:
        try:
            for alias in json.loads(c.aliases or "[]"):
                by_alias.setdefault(alias, c.id)
        except (TypeError, ValueError):
            continue
    out: dict[str, str] = {}
    for name in names:
        if name in by_name:
            out[name] = by_name[name]
        elif name in by_alias:
            out[name] = by_alias[name]
    return out


async def _replace_children(session, row, data: dict, character_ids: dict[str, str] | None = None) -> list[str]:
    """子表整体替换。返回未命中角色的 warnings（character-settings-v2）。

    character_ids：导入路径直插 pending 对象时由调用方预算的 名字→id 映射；
    None = 由 session 现查（apply_chapter_data 主路径）。
    """
    if character_ids is None:
        name_map = await _resolve_names(
            session, row.project_id,
            [str(n).strip()[:50] for n in (data.get("outline") or {}).get("characters") or [] if str(n).strip()],
        )
    else:
        name_map = character_ids
    return await _replace_children_impl(session, row, data, name_map)


async def _replace_children_impl(session, row, data: dict, name_map: dict[str, str]) -> list[str]:
    from models.chapter import (
        ChapterCharacter,
        ChapterContent,
        ChapterDowntimeFunction,
        ChapterKeyChoice,
        ChapterKeyPoint,
        ChapterKnowledgeState,
        ChapterMicroPayoff,
        ChapterPayoffItem,
        ChapterProhibition,
        ChapterRequiredChange,
        ChapterSceneCard,
        ChapterSegment,
    )

    outline = data.get("outline") or {}
    memo = data.get("memo") or {}

    row.key_points = [
        ChapterKeyPoint(sort_order=i, func_tag=tag, content=_fit(content, 300) or "")
        for i, item in enumerate(outline.get("key_points") or [])
        for tag, content in [_parse_key_point(str(item))]
    ]
    names = [str(name).strip()[:50] for name in (outline.get("characters") or []) if str(name).strip()]
    warnings = [
        f"出场角色「{name}」没有对应的角色卡，已按原文保留"
        for name in names if name not in name_map
    ]
    row.characters = [
        ChapterCharacter(
            sort_order=i,
            character_name=name,
            character_id=name_map.get(name),
        )
        for i, name in enumerate(names)
    ]

    payoff_rows: list[tuple[int, str, str]] = []
    payoff_order = 0
    for kind in ("must_resolve", "must_hold", "partial_advance"):
        for item in memo.get("payoff_plan", {}).get(kind) or []:
            # 三类共用一个递增序号：逐类从 0 编号会撞 UNIQUE(chapter_id, sort_order)
            payoff_rows.append((payoff_order, kind, str(item)))
            payoff_order += 1
    row.payoff_items = [
        ChapterPayoffItem(sort_order=i, kind=kind, content=_fit(content, 300) or "")
        for i, kind, content in payoff_rows
    ]
    row.downtime_functions = [
        ChapterDowntimeFunction(
            sort_order=i, scene=_fit(scene, 150) or "", func=_fit(func, 300) or ""
        )
        for i, item in enumerate(memo.get("downtime_functions") or [])
        for scene, func in [_split_labeled(str(item))]
    ]
    row.key_choices = [
        ChapterKeyChoice(sort_order=i, content=_fit(str(item), 300) or "")
        for i, item in enumerate(memo.get("key_choices") or [])
    ]
    row.required_changes = [
        ChapterRequiredChange(
            sort_order=i,
            change_type=_fit(kind, 50) or "",
            content=_fit(content, 300) or "",
        )
        for i, item in enumerate(memo.get("required_changes") or [])
        for kind, content in [_split_labeled(str(item))]
    ]
    row.prohibitions = [
        ChapterProhibition(sort_order=i, content=_fit(str(item), 300) or "")
        for i, item in enumerate(memo.get("prohibitions") or [])
    ]

    row.scene_cards = [
        ChapterSceneCard(
            sort_order=i,
            scene_name=_fit(sc.get("scene_name", ""), 200) or "",
            goal=_fit(sc.get("goal", ""), 300) or "",
            obstacle=_fit(sc.get("obstacle", ""), 300) or "",
            hook=_fit(sc.get("hook", ""), 300) or "",
            weight=_normalize_enum(sc.get("weight"), _SCENE_WEIGHTS, 10),
            focus=_normalize_enum(sc.get("focus"), _SCENE_FOCUS, 50),
        )
        for i, sc in enumerate(data.get("scene_cards") or [])
        if isinstance(sc, dict)
    ]
    row.micro_payoffs = [
        ChapterMicroPayoff(
            sort_order=i,
            kind=_fit(mp.get("kind", ""), 50) or "",
            description=_fit(mp.get("description", ""), 300) or "",
            location=_fit(mp.get("location", ""), 20) or "",
        )
        for i, mp in enumerate(data.get("micro_payoffs") or [])
        if isinstance(mp, dict) and str(mp.get("description") or "").strip()
    ]
    row.knowledge_states = [
        ChapterKnowledgeState(
            sort_order=i,
            character_name=_fit(ks.get("character_name", ""), 50) or "",
            knows=_fit(ks.get("knows", ""), 300) or "",
            unknowns=_fit(ks.get("unknowns", ""), 300) or "",
            gap_relation=_fit(ks.get("gap_relation", ""), 300) or "",
            gap_change=_fit(ks.get("gap_change", ""), 300) or "",
        )
        for i, ks in enumerate(data.get("knowledge_states") or [])
        if isinstance(ks, dict)
    ]

    row.segments = [
        ChapterSegment(
            sort_order=i,
            summary=_fit(seg.get("summary", ""), 300) or "",
            target_words=_int_or_none(seg.get("target_words")),
            what_to_write=_fit(seg.get("what_to_write"), 300),
            goal=_fit(seg.get("goal"), 300),
            emotional_tone=_fit(seg.get("emotional_tone"), 50),
            characters=_fit(
                ",".join(str(n).strip() for n in seg.get("characters") or []), 200
            ),
            function=_fit(seg.get("function"), 150),
            word_target=_int_or_none(seg.get("word_target")),
            seg_number=_int_or_none(seg.get("seg_number")),
        )
        for i, seg in enumerate(data.get("segments") or [])
        if isinstance(seg, dict)
    ]

    prose = data.get("prose") or ""
    if row.content is not None:
        row.content.prose = prose
    else:
        row.content = ChapterContent(prose=prose)
    return warnings


# ── 对外入口（签名与 YAML 时代的 engine.load/save 一致）────────────────────


async def _get_chapter_by_root(session, root_path: str, chapter_ref: str):
    """root_path + ref 定位章行（AI 链路手里只有 root_path）。"""
    from models.chapter import Chapter
    from models.project import Novel

    stmt = (
        select(Chapter)
        .join(Novel, Novel.id == Chapter.project_id)
        .where(Novel.root_path == root_path, Chapter.ref == strip_suffix(chapter_ref))
    )
    return await session.scalar(stmt)


async def load_chapter(root_path: str, chapter_ref: str) -> dict:
    """章全量 dict；行缺失返回 {}（调用方 404）。"""
    from db import async_session

    async with async_session() as session:
        row = await _get_chapter_by_root(session, root_path, chapter_ref)
        if row is None:
            return {}
        return assemble_chapter(row)


async def save_chapter(root_path: str, chapter_ref: str, data: dict) -> list[str]:
    """统一写入口：拆装落库 + 元数据派生 + versions 快照（PR③ 前仍文件）。

    子表 clear 后先 flush 落删除再重建（flush 内插入先于删除会撞唯一键）。
    """
    from db import async_session

    ref = strip_suffix(chapter_ref)
    async with async_session() as session:
        row = await _get_chapter_by_root(session, root_path, ref)
        if row is None:
            raise LookupError(f"chapter row not found for {ref}")

        old_prose = row.content.prose if row.content is not None else ""
        old_summary = row.summary or ""
        old_status = row.status

        if data.get("title"):
            row.title = str(data["title"])[:200]
        prose = data.get("prose") or ""
        status = data.get("status") or row.status
        # 状态机系统维护：首次落非空正文 outline → writing（页面已无状态选择器，
        # 覆盖正文保存/AI 写本章/续写三条路径——它们都经本统一写入口）
        if prose.strip() and status == "outline":
            status = "writing"
        row.status = status
        _prose, _status, warnings = await apply_chapter_data(session, row, data)
        await session.commit()

    # 版本快照：prose / outline.summary 实质变化才写（正文已落库，快照失败不回滚）
    new_summary = (data.get("outline") or {}).get("summary") or ""
    if old_prose != prose or old_summary != new_summary:
        with contextlib.suppress(Exception):
            await _write_version_snapshot(
                root_path, ref, old_status, prose, data.get("outline") or {}, status
            )
    return warnings


async def apply_chapter_data(session, row, data: dict) -> tuple[str, str, list[str]]:
    """字段落库（无提交无快照）：c-novel-export-roundtrip PR2 抽取共用。

    出场角色在此处做「名字 → character_id」解析（这里有 session 与 row.project_id；
    _replace_children 是纯同步无 session，解析不放那里——character-settings-v2）。
    未命中的名字保留原文快照并进 warnings（不静默丢、不自动建卡）。

    Returns: (prose, status, warnings)
    """
    if data.get("title"):
        row.title = str(data["title"])[:200]
    prose = data.get("prose") or ""
    status = data.get("status") or row.status
    # 状态机系统维护：首次落非空正文 outline → writing
    if prose.strip() and status == "outline":
        status = "writing"
    row.status = status
    _disassemble_scalars(row, data)
    for attr in _CHILD_ATTRS:
        getattr(row, attr).clear()
    await session.flush()
    warnings = await _replace_children(session, row, data)

    row.word_count = count_chars(prose)
    row.has_prose = bool(prose.strip())
    row.outline_status = _derive_outline_status(status, prose)
    return prose, status, warnings


async def _write_version_snapshot(
    root_path: str, ref: str, old_status: str, prose: str, outline: dict, status: str
) -> None:
    """chapter_versions 表 — version 为 13 位毫秒时间戳（BIGINT），≤50/章。"""
    import json

    from db import async_session
    from models.chapter import ChapterVersion

    timestamp = int(time.time() * 1000)
    snapshot = json.dumps(
        {"prose": prose, "outline": outline, "status": status or old_status},
        ensure_ascii=False,
    )
    async with async_session() as session:
        row = await _get_chapter_by_root(session, root_path, ref)
        if row is None:
            return
        session.add(
            ChapterVersion(
                chapter_id=row.id,
                version=timestamp,
                comment="自动保存",
                snapshot=snapshot,
            )
        )
        # 快照上限：version 单调递增，留最新 MAX_VERSIONS_PER_CHAPTER 条
        stale = (
            await session.scalars(
                select(ChapterVersion)
                .where(ChapterVersion.chapter_id == row.id)
                .order_by(ChapterVersion.version.desc())
                .offset(MAX_VERSIONS_PER_CHAPTER)
            )
        ).all()
        for old_row in stale:
            await session.delete(old_row)
        await session.commit()


async def collect_prose_by_root(root_path: str) -> str:
    """全项目正文拼接（AI 回填语料；替代扫章 YAML）。"""
    from db import async_session
    from models.chapter import Chapter, ChapterContent
    from models.project import Novel

    stmt = (
        select(ChapterContent.prose)
        .join(Chapter, Chapter.id == ChapterContent.chapter_id)
        .join(Novel, Novel.id == Chapter.project_id)
        .where(Novel.root_path == root_path)
        .order_by(Chapter.ref)
    )
    async with async_session() as session:
        return "\n\n".join(p for p in await session.scalars(stmt) if p)
