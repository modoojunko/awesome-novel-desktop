"""设定字段 AI 工具（c-writing-agent 收编：设定卡 16 行 AI 能力进 agent）。

boss 拍板 2026-11-15：调用架构改走 agent——agent 识别任务→分派给大模型→调
后端接口→产物卡回对话过目。本组工具包装 settings/ai_router 的生成核：
  - settings_genre_m1~m4：题材四问（主要看什么/绝对禁止/吃苦指数/本小说斗什么）
  - settings_intro / settings_world / settings_style：简介/世界/文风生成核
  - settings_hooks：伏笔起草/埋坑体检/查一致性
产物一律只产卡（kind="text"），作家过目后自行写回对应设置项——工具不直接
写设定（写回走前端采纳或作家手填，零新写回路径）。

字段错位判例（2026-11-15）：包装工具返回摘要必须对照数据源真实键名逐字段核。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from assistant.card_digest import (
    digest_candidates,
    digest_report,
    digest_text,
    flatten_fields,
    one_line,
)
from assistant.tools import Tool, ToolContext, ToolResult
from db import async_session
from novels.service import get_novel


def _clip(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    return text[: budget - 1] + "…"


async def _project_ok(ctx: ToolContext) -> bool:
    async with async_session() as db:
        project = await get_novel(db, ctx.novel_id, ctx.user_id)
        return project is not None


def _vocab_labels(kind: str) -> dict[str, str]:
    """候选池 id → 中文标签（题材四问的 forbidden/battlefield 出参只带 tagId）。"""
    from genres.vocab_presets import VOCAB_PRESETS

    return {str(e["id"]): str(e["label"]) for e in VOCAB_PRESETS if e["kind"] == kind}


def _field_digest(summary_head: str, field: str, value: Any) -> str:
    """题材四问的人话摘要（c-card-digest）：四种出参形状各自逐条渲染，绝不 str(dict)。"""
    if field == "cost_ratio":
        return (
            f"{summary_head}建议：{value}（1 最轻、10 最重）。"
            "还没写进书里，过目后在题材面板填回。"
        )
    if field == "core_promise":
        raw_items = value if isinstance(value, list) else [value]
        items: list[str] = []
        for item in raw_items:
            if isinstance(item, dict):
                head = str(item.get("value") or "").strip()
                note = str(item.get("note") or "").strip()
                text = f"{head}（{note}）" if head and note else head or note
            else:
                text = str(item or "").strip()
            if text:
                items.append(text)
        if not items:
            return f"{summary_head}没有给出可用候选，可重试。"
        return digest_candidates(
            f"{summary_head}候选已出", items, lambda x: x,
            tail="（还没写进书里，在题材面板勾选采纳后才生效）",
        )
    if field in ("forbidden_list", "battlefield"):
        labels = _vocab_labels("forbidden" if field == "forbidden_list" else "battlefield")
        items = []
        for item in value if isinstance(value, list) else []:
            if isinstance(item, dict):
                tag = str(item.get("tagId") or "")
                items.append(labels.get(tag) or str(item.get("text") or "") or tag)
            else:
                items.append(str(item or ""))
        items = [x for x in items if x.strip()]
        if not items:
            return f"{summary_head}没有给出可用候选，可重试。"
        return digest_candidates(
            f"{summary_head}候选已出", items, lambda x: x,
            tail="（还没写进书里，在题材面板勾选采纳后才生效）",
        )
    body = flatten_fields(value) if isinstance(value, dict) else one_line(value)
    return digest_text(f"{summary_head}候选已出", body, tail="（还没写进书里，过目后填回对应设置项）")


async def _settings_field(
    ctx: ToolContext,
    stype: str,
    field: str,
    summary_head: str,
) -> ToolResult:
    """万能量：单字段生成核（generate_field 直调——与 HTTP 端点同核同提示词）。"""
    if not await _project_ok(ctx):
        return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
    from assistant.caps.settings import CapabilityError, generate_settings_field

    try:
        result = await generate_settings_field(ctx.novel_id, stype, field, ctx.user_id)
    except CapabilityError as e:
        return ToolResult(ok=False, summary=e.message)
    value = result.get("value")
    payload = {"stype": stype, "field": field, "value": value}
    return ToolResult(
        ok=True,
        summary=_field_digest(summary_head, field, value),
        card={"kind": "text", "payload": payload},
    )


_INTRO_VERDICT = {"strong": "稳", "ok": "过得去", "weak": "偏弱"}


def _intro_check_digest(result: dict) -> str:
    """简介体检：六段缺口＋禁忌触线逐条，达标段只计数。"""
    items: list[dict[str, Any]] = []
    for seg in result.get("six_segments") or []:
        if not isinstance(seg, dict):
            continue
        items.append(
            {
                "status": seg.get("status"),
                "name": seg.get("name") or "未命名段",
                "note": seg.get("note") or seg.get("excerpt") or "",
            }
        )
    taboo = result.get("taboo") if isinstance(result.get("taboo"), dict) else {}
    for hit in taboo.get("hits") or []:
        if not isinstance(hit, dict):
            continue
        excerpts = "；".join(str(x) for x in (hit.get("excerpts") or []) if str(x).strip())
        items.append(
            {
                "status": "warn",
                "name": f"触线·{hit.get('rule') or '禁忌'}",
                "note": excerpts or "踩到简介禁忌",
            }
        )
    verdict = _INTRO_VERDICT.get(str(result.get("verdict") or ""), "")
    head = f"简介体检完成（判定：{verdict}）" if verdict else "简介体检完成"
    return digest_report(
        head,
        items,
        status_of=lambda it: str(it.get("status") or ""),
        render=lambda it: f"{it['name']}：{it['note'] or '需要补'}",
    )


def _intro_draft_digest(result: dict) -> str:
    """简介起草：三条候选逐条全文（c-card-digest 的主因场景）。"""
    candidates = [c for c in result.get("candidates") or [] if isinstance(c, dict)]
    if not candidates:
        return digest_text("简介候选已出", flatten_fields(result))
    return digest_candidates(
        "简介候选已出",
        candidates,
        lambda c: f"{c.get('label') or '候选'}：{c.get('synopsis') or ''}",
    )


async def _settings_intro(ctx: ToolContext, action: str) -> ToolResult:
    """简介 AI 核（caps.settings.intro_ai_action——与面板端点同核）。"""
    if not await _project_ok(ctx):
        return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
    from assistant.caps.settings import CapabilityError, intro_ai_action

    try:
        result = await intro_ai_action(ctx.novel_id, action, ctx.user_id)
    except CapabilityError as e:
        return ToolResult(ok=False, summary=e.message)
    payload = {"action": action, "result": result}
    summary = _intro_check_digest(result) if action == "check" else _intro_draft_digest(result)
    return ToolResult(
        ok=True,
        summary=summary,
        card={"kind": "text", "payload": payload},
    )


def _hooks_draft_lines(result: dict) -> list[str]:
    """伏笔候选逐条（[类型·优先级] 描述）——摘要与卡面共用同一份人话行。"""
    from settings.hooks_model import priority_label, type_label

    lines: list[str] = []
    for i, c in enumerate(result.get("candidates") or [], 1):
        if not isinstance(c, dict):
            continue
        head = str(c.get("label") or c.get("name") or "").strip()
        desc = str(c.get("description") or c.get("synopsis") or "").strip()
        tag = "·".join(
            x for x in (type_label(c.get("type")), priority_label(c.get("priority"))) if x
        )
        tag_text = f"[{tag}] " if tag else ""
        if head and desc:
            lines.append(f"{tag_text}{head}：{desc}")
        else:
            lines.append(f"{tag_text}{desc or head or f'候选{i}'}")
    return [x for x in lines if x.strip()]


def _hooks_check_lines(result: dict) -> list[str]:
    """伏笔体检逐条（code：note）——卡面看全量，摘要只给问题条目。"""
    lines: list[str] = []
    for c in result.get("checks") or []:
        if not isinstance(c, dict):
            continue
        code = str(c.get("code") or c.get("name") or "伏笔")
        note = str(c.get("note") or "").strip()
        lines.append(f"{code}：{note}" if note else code)
    return [x for x in lines if x]


def _make_hooks_tool(action: str, desc: str) -> Tool:
    async def _fn(ctx: ToolContext, **_model_extra: Any) -> ToolResult:
        if not await _project_ok(ctx):
            return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
        from assistant.caps.settings import CapabilityError, hooks_ai_action

        try:
            result = await hooks_ai_action(ctx.novel_id, action, ctx.user_id)
        except CapabilityError as e:
            return ToolResult(ok=False, summary=e.message)

        if action == "check":
            checks = [c for c in result.get("checks") or [] if isinstance(c, dict)]
            summary = digest_report(
                "伏笔体检完成",
                checks,
                status_of=lambda c: str(c.get("status") or ""),
                render=lambda c: f"{c.get('code') or '伏笔'}：{c.get('note') or '需处理'}",
            )
            draft = "\n".join(_hooks_check_lines(result)) or "体检完成，没有要处理的问题。"
        else:
            lines = _hooks_draft_lines(result)
            summary = (
                digest_candidates("伏笔候选已出", lines, lambda x: x)
                if lines
                else digest_text("伏笔 AI 完成", flatten_fields(result))
            )
            draft = "\n".join(lines) or "AI 没有给出可用候选，可重试。"
        return ToolResult(
            ok=True,
            summary=summary,
            card={"kind": "text", "payload": {"action": action, "draft": draft}},
        )

    return Tool(
        name=f"settings_hooks_{action}",
        kind="card",
        feature_key="settings-ai-fields",
        parameters={"type": "object", "properties": {}},
        description=desc,
        fn=_fn,
    )


# 题材四问（generate_field 直调；genre field 白名单见 _GENRE_PROMPTS）
def _make_genre_tool(field: str, desc: str) -> Tool:
    async def _fn(ctx: ToolContext, **_model_extra: Any) -> ToolResult:
        return await _settings_field(
            ctx, "genre", field, desc.split("：")[0].replace("题材·", "")
        )

    return Tool(
        name=f"settings_genre_{field}",
        kind="card",
        feature_key="settings-ai-fields",
        parameters={"type": "object", "properties": {}},
        description=desc,
        fn=_fn,
    )




# ── 当前设定页字段（c-agent-page-fields-tool）────────────────────────────
# 只读工具：agent 在作家说「这个/这格/这里」时自己调；不自动注入提示词。
# 当前面板由请求 thread（set:<panel>）决定，模型零参数。


async def _read_page_fields(ctx: ToolContext) -> ToolResult:
    from assistant.page_context import build_panel_fields

    thread = str(getattr(ctx, "thread", "") or "").strip()
    panel = thread.split(":", 1)[1] if thread.startswith("set:") else ""
    text = await build_panel_fields(
        ctx.root_path,
        ctx.novel_id,
        panel,
        tuple(getattr(ctx, "page_unsaved", ()) or ()),
    )
    return ToolResult(ok=True, summary=text)


# ── 01 题材目录（c-agent-genre-pick）──────────────────────────────────────
# 「题材」有两层：01 目录（theme/sub_genre）与 02-05 四格。四问工具不能代替
# 选题材——模型没有目录时只能拿 core_promise 顶替（2026-11-21 真机实锤）。


async def _read_genre_catalog(ctx: ToolContext, **_model_extra: Any) -> ToolResult:
    """读封闭题材目录（大类+子类+解读/案例）——供模型按标题判断，读类不落库。"""
    from genres.theme_catalog import THEMES

    lines: list[str] = []
    for theme in THEMES:
        lines.append(f"{theme['name']}：{theme['desc']}")
        for sub in theme["sub_types"]:
            lines.append(
                f"  - {sub['name']}：{sub['desc']}（例：{sub['example']}）"
            )
    return ToolResult(
        ok=True,
        summary=(
            "题材目录（只能从这里选）：\n"
            + "\n".join(lines)
            + "\n\n下一步：从上面选一个最贴合书名的 theme（可带 sub_genre），"
            "调 settings_genre_pick 出采纳卡；不要用题材四问代替选题材。"
            "作家只让『根据标题选』时直接给一张首选卡（可附一句备选），"
            "不要先追问世界观；拿不准的假设写进 note，让作家在卡上改。"
        ),
    )


async def _settings_genre_pick(
    ctx: ToolContext,
    theme: str = "",
    sub_genre: str = "",
    note: str = "",
) -> ToolResult:
    """题材目录推荐卡：只产卡不写库；theme/sub_genre 按封闭目录校验。"""
    from genres.theme_catalog import THEMES, sub_type_entry, theme_entry

    th = str(theme or "").strip()
    sub = str(sub_genre or "").strip()
    why = _clip(str(note or "").strip(), 400)
    entry = theme_entry(th)
    if entry is None:
        names = "、".join(t["name"] for t in THEMES)
        return ToolResult(
            ok=False,
            summary=(
                f"没有「{th or '空'}」这个题材。只能从目录里选：{names}。"
                "先调 read_genre_catalog 看每类写的是什么，再选一个。"
            ),
        )
    if sub and sub_type_entry(th, sub) is None:
        subs = "、".join(s["name"] for s in entry["sub_types"])
        return ToolResult(
            ok=False,
            summary=(
                f"「{th}」下没有「{sub}」这个子类。可选：{subs}；"
                "也可以只定大类（sub_genre 留空）。"
            ),
        )
    label = f"{th} / {sub}" if sub else th
    tail = f"。{why}" if why else ""
    return ToolResult(
        ok=True,
        summary=f"题材建议：{label}{tail}（过目后采纳写入 01 题材）",
        card={
            "kind": "text",
            "payload": {
                "stype": "genre",
                "field": "catalog",
                "value": {"theme": th, "sub_genre": sub, "note": why},
            },
        },
    )


# ── 章纲补全缺失（#5 样板：agent 识别→直调 fill-gaps 核→产物卡）──────────────

_FILLABLE = ("summary", "characters", "changes", "prohibitions", "mood")
_GAP_LABELS = {
    "summary": "一句话概要",
    "characters": "出场角色",
    "changes": "必须完成的变化",
    "prohibitions": "必须维持悬念",
    "mood": "阶段",
}


async def _settings_og_fill(ctx: ToolContext, chapter_ref: str) -> ToolResult:
    """补全章纲缺失字段（openwriter fill-gaps 核直调；产物不落库，作家过目后
    在章纲表单采纳——写回走前端既有保存链）。"""
    if not await _project_ok(ctx):
        return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
    from chapters.ai_draft import _FILLABLE_KEYS, fill_outline_gaps

    async with async_session() as db:
        body = {"missing": list(_FILLABLE_KEYS)}
        try:
            result = await fill_outline_gaps(
                ctx.novel_id, chapter_ref, body,
                {"id": ctx.user_id}, True, True, db,
            )
        except HTTPException as e:
            return ToolResult(ok=False, summary=str(e.detail))
    fills = result.get("fills") or {}
    if not fills:
        return ToolResult(ok=True, summary=f"{chapter_ref} 章纲五项齐全，没有要补的。")
    lines = [f"{_GAP_LABELS.get(k, k)}：{_clip(str(v), 300)}" for k, v in fills.items()]
    return ToolResult(
        ok=True,
        summary=digest_candidates(
            f"{chapter_ref} 章纲补全",
            lines,
            lambda x: x,
            tail="（还没写进书里，过目后在章纲表单采纳）",
        ),
        card={"kind": "text", "payload": {"chapter_ref": chapter_ref, "fills": fills}},
    )


def _make_og_fill_tool() -> Tool:
    async def _fn(ctx: ToolContext, chapter_ref: str = "") -> ToolResult:
        # 章锚：作家给章 ref 就用；没给则用聚焦对象/当前 frontier
        from chapters.frontier import frontier_info
        from db import async_session

        ref = (chapter_ref or "").strip() or (ctx.focus_ref or "").strip()
        if not ref:
            async with async_session() as db:
                info = await frontier_info(db, ctx.novel_id)
            fr = info.get("frontier") or {}
            ref = str(fr.get("ref") or "")
        if not ref:
            return ToolResult(ok=False, summary="定位不到章——给我章号或章名。")
        return await _settings_og_fill(ctx, ref)

    return Tool(
        name="settings_og_fill",
        kind="card",
        feature_key="settings-ai-fields",
        parameters={
            "type": "object",
            "properties": {
                "chapter_ref": {"type": "string", "description": "章 ref，如 vol-1-ch-7（可空＝当前章）"},
            },
        },
        description="章纲补全缺失：查本章章纲五项（概要/角色/变化/悬念/阶段）缺什么，AI 补候选（不落库，过目后采纳）",
        fn=_fn,
        risk_level="low",
    )


OG_FILL_TOOL = _make_og_fill_tool()


# ── 创建角色（boss 拍板 2026-11-15）：访谈→拿稳→确认卡→确认后才建卡──────────
# 必需要素评估在工具侧（不是模型自觉）：缺一项就返回追问清单，agent 继续访谈；
# 齐了才出草案确认卡（confirmed=False），作家点确认后前端调建卡 API 落卡。

_CHAR_REQUIRED = ("identity", "relation", "function")  # 身份背景/与现有角色关系/剧情功能
_CHAR_LABELS = {
    "name": "名字",
    "gender_age": "性别与年龄",
    "identity": "身份背景",
    "relation": "与现有角色的关系",
    "function": "剧情功能",
    "personality": "性格特质",
}


async def _cast_names(ctx: ToolContext) -> list[str]:
    from assistant.tools import _read_settings

    res = await _read_settings(ctx, area="cast")
    names = []
    for line in (res.summary or "").split("\n"):
        line = line.lstrip("- ")
        if "（" in line:
            names.append(line.split("（")[0].strip())
        elif line:
            names.append(line.strip())
    return names


async def _draft_character(
    ctx: ToolContext,
    fields: dict[str, Any] | None = None,
) -> ToolResult:
    """创建角色·评估与草案（两态）：
    - 必需要素没拿齐 → 返回追问清单（agent 转问作家，继续访谈）
    - 拿齐 → 校验＋撞名检查 → 出草案确认卡（confirmed=False；作家点确认才建卡）"""
    fields = {k: str(v).strip() for k, v in (fields or {}).items() if str(v or "").strip()}
    names = await _cast_names(ctx)

    missing = [k for k in _CHAR_REQUIRED if not fields.get(k)]
    if missing:
        labels = "、".join(_CHAR_LABELS.get(k, k) for k in missing)
        have = {k: v for k, v in fields.items() if v}
        return ToolResult(
            ok=True,
            summary=(
                f"创建角色还缺：{labels}。"
                + (f"已记下：{'、'.join(f'{_CHAR_LABELS.get(k, k)}={v}' for k, v in have.items())}。" if have else "")
                + "逐项问作家，别一次全问。"
            ),
            meta={
                "char_intake": {"missing": missing, "collected": have},
                "_display": {"stage": "intake"},
            },
        )

    name = fields.get("name") or ""
    collide = name in names
    if collide:
        return ToolResult(
            ok=False,
            summary=f"名字「{name}」和现有角色撞了——换个名字再出草案。",
        )

    draft = {
        "name": name or "（待定）",
        "gender_age": fields.get("gender_age", ""),
        "identity": fields["identity"],
        "relation": fields["relation"],
        "function": fields["function"],
        "personality": fields.get("personality", ""),
    }
    summary = (
        f"角色草案拿稳了：{draft['name']}（{draft['gender_age']}）——"
        f"{_clip(draft['identity'], 120)}。推确认卡给作家。"
    )
    return ToolResult(
        ok=True,
        summary=summary,
        card={
            "kind": "text",
            "payload": {"character_draft": draft, "confirmed": False, "collide_check": "ok"},
        },
    )


def _make_draft_character_tool() -> Tool:
    async def _fn(ctx: ToolContext, fields: dict[str, Any] | None = None) -> ToolResult:
        return await _draft_character(ctx, fields)

    return Tool(
        name="draft_character",
        kind="card",
        feature_key="settings-ai-fields",
        parameters={
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": "已收集的角色要素（缺什么传什么，工具评估必需要素）",
                    "properties": {
                        "name": {"type": "string", "description": "名字"},
                        "gender_age": {"type": "string", "description": "性别与年龄"},
                        "identity": {"type": "string", "description": "身份背景"},
                        "relation": {"type": "string", "description": "与现有角色的关系"},
                        "function": {"type": "string", "description": "剧情功能"},
                        "personality": {"type": "string", "description": "性格特质"},
                    },
                },
            },
            "required": ["fields"],
        },
        description=(
            "创建角色·评估与草案。作家想新建角色时调用：传入已收集的 fields，"
            "工具评估必需要素（身份背景/与现有角色关系/剧情功能必填）——没拿齐会返回"
            "追问清单（逐项问作家，别一次全问）；拿齐才出草案确认卡，作家点确认后才真正建卡。"
        ),
        fn=_fn,
        risk_level="low",  # 只出草案卡不落库——建卡执行在作家确认之后（前端采纳）
    )


DRAFT_CHARACTER_TOOL = _make_draft_character_tool()
SETTINGS_FIELD_TOOLS: tuple[Tool, ...] = (
    DRAFT_CHARACTER_TOOL,
    OG_FILL_TOOL,
    Tool(
        name="read_page_fields",
        kind="read",
        parameters={"type": "object", "properties": {}},
        description=(
            "读当前设定页的面板字段清单与已保存现值（题材五格/简介/世界八格/主线/文风/"
            "角色/伏笔）。作家说「这个/这格/这里/这一项」没点名字段、要按现值改/补、"
            "问本页哪些填了哪些没填、或写前不确定写哪个字段时，先调它。"
            "不返回别的面板/书、正文或章纲全文、未保存的输入、选中的文字、题材可选目录；"
            "这些用 read_settings/read_chapter/read_outline/read_genre_catalog。"
            "只在需要本页字段现值时调，不要当开场例行读取。"
        ),
        fn=_read_page_fields,
    ),
    Tool(
        name="read_genre_catalog",
        kind="read",
        parameters={"type": "object", "properties": {}},
        description=(
            "读题材目录（36 个大类+子类，含每类的解读与案例）。作家说「根据标题选/定/"
            "判断题材」「这本书算什么题材」「推荐个题材」时，先调本工具看目录，再用 "
            "settings_genre_pick 出采纳卡。不要用题材四问（爽点/红线/代价/斗什么）代替选题材。"
        ),
        fn=_read_genre_catalog,
    ),
    Tool(
        name="settings_genre_pick",
        kind="card",
        feature_key="settings-ai-fields",
        parameters={
            "type": "object",
            "properties": {
                "theme": {"type": "string", "description": "题材大类（必须来自 read_genre_catalog）"},
                "sub_genre": {"type": "string", "description": "子类（可空；必须属于该大类）"},
                "note": {"type": "string", "description": "推荐理由（一句话，给作家看）"},
            },
            "required": ["theme"],
        },
        description=(
            "把选定的 01 题材（大类+子类）做成采纳卡，作家点「采纳·写入」后落到题材面板。"
            "只用于选题材；爽点/红线/吃苦/战场用对应的题材四问工具。"
        ),
        fn=_settings_genre_pick,
    ),
    _make_genre_tool("core_promise", "题材·主要看什么：给几个核心看点候选（勾选采纳）"),
    _make_genre_tool("forbidden_list", "题材·绝对禁止：这本书绝不出现什么（红线清单候选）"),
    _make_genre_tool("cost_ratio", "题材·吃苦指数：主角得到好处要付多大代价（代价配比建议）"),
    _make_genre_tool("battlefield", "题材·本小说斗什么：全书主要斗的是什么（对抗物候选）"),
    _make_hooks_tool("draft", "伏笔·起草：按简介＋题材＋世界＋主线给 3 条候选，配收束章"),
    _make_hooks_tool("check", "伏笔·埋坑体检：扫活跃伏笔×已写章纲，埋了没还的点名"),
    Tool(
        name="settings_intro",
        kind="card",
        feature_key="settings-ai-fields",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["draft", "check"],
                    "description": "draft 起草候选 / check 体检",
                },
            },
            "required": ["action"],
        },
        description="简介 AI：draft 按三问起草候选；check 体检简介是否只有设定没钩子",
        fn=_settings_intro,
    ),
)
