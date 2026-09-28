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
import time

from sqlalchemy import select

from chapters.schemas import normalize_plot_items
from novels.service import count_chars
from workflow.engine import MAX_VERSIONS_PER_CHAPTER, strip_suffix

logger = logging.getLogger("uvicorn.error")

# 章纲标量列映射：(JSON 键, 列名, 列宽)
# c-og-slim-v2：location/time/narrative_pov 与 reader_expectation 两键、情绪设计两暗字段
# （mood_progression/emotional_hook）与 intensity_* 一并退役——列随模型摘除，拆装链不再含。
_OUTLINE_SCALARS = [
    ("summary", "summary", 300),
]
_EMOTIONAL_SCALARS = [
    ("primary_mood", "primary_mood", 50),
]


def _fit(value, width: int | None):
    """写入侧截断：None 直通；超宽截断（生成物截断安全，用户输入走 schema 拒收）。"""
    if value is None:
        return None
    s = str(value)
    if width is not None and len(s) > width:
        return s[:width]
    return s


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
    if row.ghost_of:
        data["ghost_of"] = row.ghost_of
    # chapter-rewrite：基于旧设定角标（主线章；上游重写置位、本章保存清除）
    if row.stale:
        data["stale"] = True
    if row.word_target is not None:
        data["word_target"] = row.word_target
    if row.ladder_exit:
        data["ladder_exit"] = row.ladder_exit
    # 拆章两格（c-chapter-plan-ai）：challenge/plot_stage 标量直出
    # （c-og-slim-v2：「本章行动」退役，其「谁在场」语义由概要＋剧情条目承载）
    if row.challenge:
        data["challenge"] = row.challenge
    if row.plot_stage:
        data["plot_stage"] = row.plot_stage
    # 本章文风影子（chapter-style-shadow）：JSON 直出，加键兼容
    try:
        import json as _json

        data["style_shadow"] = _json.loads(row.style_shadow or "{}")
    except Exception:  # noqa: BLE001 — 影子损坏按空处理，不阻塞章读取
        data["style_shadow"] = {}
    # 章内剧情条目（c-plot-split）：string[] 直出、恒带键；空串/损坏/非数组按 []，
    # 不阻塞章读取（旧库无此列时 server_default "[]" 兜住）
    try:
        _items = json.loads(row.plot_items or "[]")
        data["plot_items"] = [str(x) for x in _items] if isinstance(_items, list) else []
    except Exception:  # noqa: BLE001 — 剧情条目损坏按空处理，不阻塞章读取
        data["plot_items"] = []

    outline: dict = {
        "characters": [c.character_name for c in row.characters],
    }
    # archive-reconcile：本章各出场角色的状态变化（加键兼容，API 契约不变）
    char_states = [
        {"name": c.character_name, "state_change": c.state_change}
        for c in row.characters
        if c.state_change
    ]
    if char_states:
        outline["character_states"] = char_states
    for json_key, col, _w in _OUTLINE_SCALARS:
        outline[json_key] = getattr(row, col) or ""
    data["outline"] = outline

    payoff: dict[str, list[str]] = {
        "must_resolve": [],
        "must_hold": [],
    }
    for p in row.payoff_items:
        payoff.setdefault(p.kind, []).append(p.content)
    memo: dict = {
        "payoff_plan": payoff,
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

    if row.micro_payoffs:
        data["micro_payoffs"] = [
            {
                "kind": m.kind,
                "description": m.description,
            }
            for m in row.micro_payoffs
        ]

    return data


# ── 拆装：章 JSON → DB 行（子表整体替换）───────────────────────────────────


def _disassemble_scalars(row, data: dict) -> None:
    """标量族落库——缺键保持现值（patch-gates）。

    c-og-chapter-put-patch-gates：此前除 plot_items 外全字段族「缺键即清」，任何
    部分键 PUT（旁路写入/瘦身底座合并）都会把未带字段抹空。统一改为按 family 键
    presence-gate：family 键存在才写该族（族内子键缺失按空落值，显式清空走空值）；
    顶层标量逐键 gate。plot_items/style_shadow 的形状守卫保持原样。
    """
    outline = data.get("outline")
    if isinstance(outline, dict):
        for json_key, col, width in _OUTLINE_SCALARS:
            if outline.get(json_key) is not None:
                setattr(row, col, _fit(outline.get(json_key), width))
    emotional = data.get("emotional_design")
    if isinstance(emotional, dict):
        for json_key, col, width in _EMOTIONAL_SCALARS:
            if emotional.get(json_key) is not None:
                setattr(row, col, _fit(emotional.get(json_key), width))
    if "word_target" in data:
        row.word_target = _int_or_none(data.get("word_target"))
    # 文本标量：None 按缺键处理（与 plot_items None 口径一致）；显式 "" 清空
    for key, col, width in (("ladder_exit", "ladder_exit", 300),
                            ("challenge", "challenge", 150),
                            ("plot_stage", "plot_stage", 20)):
        if data.get(key) is not None:
            setattr(row, col, _fit(data.get(key), width))
    # 本章文风影子：仅收 dict 形状 {dim: {value, reason}}，越界值置空
    shadow = data.get("style_shadow")
    if isinstance(shadow, dict):
        clean: dict[str, dict] = {}
        for dim, item in shadow.items():
            if isinstance(item, dict) and (str(item.get("value", "")).strip() or str(item.get("reason", "")).strip()):
                clean[str(dim)] = {
                    "value": str(item.get("value", "")),
                    "reason": str(item.get("reason", "")),
                }
        import json as _json

        row.style_shadow = _json.dumps(clean, ensure_ascii=False)
    # 章内剧情条目（c-plot-split）：presence-gate——缺键/None 保持现值（导入旧包
    # 缺失键走列默认 []），显式 [] 清空；形状非列表按缺键处理（不误清现值）。
    # 预算越界静默夹（normalize_plot_items 单源）——保存链不报错。
    if "plot_items" in data and isinstance(data["plot_items"], list):
        row.plot_items = json.dumps(
            normalize_plot_items(data["plot_items"]), ensure_ascii=False
        )


# 子表整体替换面（c-og-slim-v2：key_points/scene_cards/segments 三表退役）
_CHILD_ATTRS = (
    "characters", "payoff_items",
    "required_changes", "prohibitions",
    "micro_payoffs",
)


def _child_replace_plan(data: dict) -> dict[str, bool]:
    """子表替换计划——缺键保持现值（patch-gates，与 plot_items 守卫同一合同）。

    characters 键在 outline 内；payoff_items/required_changes/prohibitions 在 memo 内；
    micro_payoffs 在顶层。键存在才整体替换（显式 [] = 清空）；键缺失＝本次不动该表。
    导入/导出全量包各键恒在（assemble 恒出 outline/memo），行为不变。
    """
    outline = data.get("outline") if isinstance(data.get("outline"), dict) else None
    memo = data.get("memo") if isinstance(data.get("memo"), dict) else None
    return {
        "characters": outline is not None and "characters" in outline,
        "payoff_items": memo is not None and "payoff_plan" in memo,
        "required_changes": memo is not None and "required_changes" in memo,
        "prohibitions": memo is not None and "prohibitions" in memo,
        "micro_payoffs": "micro_payoffs" in data,
    }


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


async def _replace_children(
    session, row, data: dict,
    character_ids: dict[str, str] | None = None,
    plan: dict[str, bool] | None = None,
) -> list[str]:
    """子表整体替换（按键 plan 门控——缺键保持现值）。返回未命中角色的 warnings。

    character_ids：导入路径直插 pending 对象时由调用方预算的 名字→id 映射；
    None = 由 session 现查（apply_chapter_data 主路径）。
    """
    if plan is None:
        plan = _child_replace_plan(data)
    if character_ids is None and plan["characters"]:
        outline = data.get("outline")
        raw_names = outline.get("characters") or [] if isinstance(outline, dict) else []
        name_map = await _resolve_names(
            session, row.project_id,
            [str(n).strip()[:50] for n in raw_names if str(n).strip()],
        )
    else:
        name_map = character_ids or {}
    return await _replace_children_impl(session, row, data, name_map, plan=plan)


async def _replace_children_impl(
    session, row, data: dict, name_map: dict[str, str],
    plan: dict[str, bool] | None = None,
) -> list[str]:
    from models.chapter import (
        ChapterCharacter,
        ChapterContent,
        ChapterMicroPayoff,
        ChapterPayoffItem,
        ChapterProhibition,
        ChapterRequiredChange,
    )

    if plan is None:
        plan = _child_replace_plan(data)
    outline = data.get("outline") if isinstance(data.get("outline"), dict) else {}
    memo = data.get("memo") if isinstance(data.get("memo"), dict) else {}

    names = [str(name).strip()[:50] for name in (outline.get("characters") or []) if str(name).strip()]
    warnings = [
        f"出场角色「{name}」没有对应的角色卡，已按原文保留"
        for name in names if name not in name_map
    ]
    # 本章各角色的状态变化（archive-reconcile）：键=角色名；重归档/重试覆盖
    state_by_name = {
        str(item.get("name", "")).strip(): str(item.get("state_change", "") or "")
        for item in (
            outline.get("character_states")
            if isinstance(outline.get("character_states"), list)
            else []
        )
        if isinstance(item, dict)
    }
    if plan["characters"]:
        row.characters = [
            ChapterCharacter(
                sort_order=i,
                character_name=name,
                character_id=name_map.get(name),
                state_change=_fit(state_by_name.get(name, ""), 200),
            )
            for i, name in enumerate(names)
        ]

    payoff_rows: list[tuple[int, str, str]] = []
    payoff_order = 0
    for kind in ("must_resolve", "must_hold"):
        for item in memo.get("payoff_plan", {}).get(kind) or []:
            # 三类共用一个递增序号：逐类从 0 编号会撞 UNIQUE(chapter_id, sort_order)
            payoff_rows.append((payoff_order, kind, str(item)))
            payoff_order += 1
    if plan["payoff_items"]:
        row.payoff_items = [
            ChapterPayoffItem(sort_order=i, kind=kind, content=_fit(content, 300) or "")
            for i, kind, content in payoff_rows
        ]
    if plan["required_changes"]:
        row.required_changes = [
            ChapterRequiredChange(
                sort_order=i,
                change_type=_fit(kind, 50) or "",
                content=_fit(content, 300) or "",
            )
            for i, item in enumerate(memo.get("required_changes") or [])
            for kind, content in [_split_labeled(str(item))]
        ]
    if plan["prohibitions"]:
        row.prohibitions = [
            ChapterProhibition(sort_order=i, content=_fit(str(item), 300) or "")
            for i, item in enumerate(memo.get("prohibitions") or [])
        ]

    if plan["micro_payoffs"]:
        row.micro_payoffs = [
            ChapterMicroPayoff(
                sort_order=i,
                kind=_fit(mp.get("kind", ""), 50) or "",
                description=_fit(mp.get("description", ""), 300) or "",
            )
            for i, mp in enumerate(data.get("micro_payoffs") or [])
            if isinstance(mp, dict) and str(mp.get("description") or "").strip()
        ]

    if "prose" in data:
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
        # prose 缺键＝本次不动正文：派生与快照口径取存量值（patch-gates）
        prose_in = data.get("prose")
        prose = old_prose if prose_in is None else (prose_in or "")
        status = data.get("status") or row.status
        old_exit = (row.ladder_exit or "").strip()  # 变更前快照（stale 判定用）
        # 状态机系统维护：首次落非空正文 outline → writing（页面已无状态选择器，
        # 覆盖正文保存/AI 写本章/续写三条路径——它们都经本统一写入口；
        # 翻转只看本次携带的 prose，缺键＝未动正文不触发）
        if (prose_in or "").strip() and status == "outline":
            status = "writing"
        row.status = status
        _prose, _status, warnings = await apply_chapter_data(session, row, data)
        # chapter-rewrite：本章内容有写（正文/章纲/重写归档）＝作者已接管，
        # 「基于旧设定」角标在单写入口统一清除
        if row.stale:
            row.stale = False
        # c-chapter-plan-ai 第二触发面：上游章末落点**实质变更**（trim 后不同）且
        # 下一主线章已有正文 → 给下一章置「基于旧设定」（拆章改落点会让下一章进场过期）。
        await _mark_next_stale_on_exit_change(session, row, data, old_exit)
        await session.commit()

    # 版本快照：prose / outline.summary 实质变化才写（正文已落库，快照失败不回滚）。
    # 缺键＝未动该族，不触发快照（patch-gates：部分键 PUT 不再误判「清空」而写快照）。
    outline_in = data.get("outline")
    new_summary = (outline_in or {}).get("summary") or "" if isinstance(outline_in, dict) else ""
    if prose != old_prose or (isinstance(outline_in, dict) and new_summary != old_summary):
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
    status = data.get("status") or row.status
    # 状态机系统维护：首次落非空正文 outline → writing（只看本次携带的 prose）
    if (data.get("prose") or "").strip() and status == "outline":
        status = "writing"
    row.status = status
    _disassemble_scalars(row, data)
    plan = _child_replace_plan(data)
    for attr in _CHILD_ATTRS:
        if plan[attr]:
            getattr(row, attr).clear()
    await session.flush()
    warnings = await _replace_children(session, row, data, plan=plan)

    # 派生元数据只在本次确实携带 prose 键时重算（缺键＝未动正文，保持现值——
    # 否则部分键 PUT 会把 word_count/has_prose 清零、outline_status 降级）。
    if "prose" in data:
        prose = data.get("prose") or ""
        row.word_count = count_chars(prose)
        row.has_prose = bool(prose.strip())
        row.outline_status = _derive_outline_status(status, prose)
    else:
        prose = row.content.prose if row.content is not None else ""
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


async def _mark_next_stale_on_exit_change(session, row, data: dict, old_exit: str) -> None:
    """上游章末落点实质变更 → 下一主线章置 stale（已有正文才置；措辞微调不触发）。"""
    if "ladder_exit" not in data:
        return
    new_exit = str(data.get("ladder_exit") or "").strip()
    if new_exit == old_exit:
        return
    from sqlalchemy import select

    from models.chapter import Chapter

    nxt = (
        await session.scalars(
            select(Chapter)
            .where(
                Chapter.volume_id == row.volume_id,
                Chapter.chapter_no > row.chapter_no,
                Chapter.ghost_of.is_(None),
            )
            .order_by(Chapter.chapter_no)
            .limit(1)
        )
    ).first()
    if nxt is not None and nxt.has_prose:
        nxt.stale = True


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
