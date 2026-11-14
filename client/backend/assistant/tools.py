"""工具注册表（c-writing-agent 批A 1.2 结构＋批A 读类五工具）。

能力围栏的物理实现（拍板④）：注册表物理封闭——只登记书内读/写/改与本地知识库
读/写/改；清单外的动作 agent 「够不着」。批A 落地读类五工具＋注册表结构；产卡
（起草/体检/发散）与写类（write_gate 管控）在批B 挂载，注册表结构此期定型。

每个工具 = {name, kind, discipline, feature_key, args_hint, fn}：
  - kind:   read（自主连环调，无档位闸）| card（生成只产卡，成本闸）| write（授权梯度）
  - discipline: anchored（锚定设定）| divergent（可添人添事，产物打标）
  - feature_key: 档位 key（读类为空串；card/write 系对齐 frontend features.ts）
  - fn: async (ctx: ToolContext, **args) -> ToolResult；工具自开自关短会话（循环体不持事务）
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

# 转写预算（write/chapter_writer.py 判例同风格：按中文字符预算，不按 token）
READ_CHAPTER_BUDGET_CHARS = 1500
READ_SETTINGS_BUDGET_CHARS = 800


@dataclass
class ToolContext:
    """一次执行的上下文（只读快照；工具内部需要 DB 时自开自关短会话）。"""

    novel_id: str
    root_path: str
    user_id: str
    page: str = ""


@dataclass
class ToolResult:
    ok: bool
    # 给模型看的结果摘要（进转写前再按预算裁剪）
    summary: str
    # 结构化载荷（进事件流/产物卡；读类通常 None）
    card: dict | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    kind: str  # read | card | write
    args_hint: str  # 进协议模板的入参说明（封闭字段名清单）
    description: str  # 模型侧契约（工具描述=契约；发散类写明「可新增、须标记」）
    discipline: str = "anchored"  # anchored | divergent
    feature_key: str = ""  # 读类空串；对齐 frontend/src/lib/features.ts
    fn: Callable[..., Awaitable[ToolResult]] | None = None


# ── 读类工具实现（全部薄包装既有实现；工具自开自关短会话）─────────────────


def _clip(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    return text[: budget - 1] + "…"


async def _read_chapter(ctx: ToolContext, chapter_ref: str) -> ToolResult:
    from chapters.store import load_chapter

    data = await load_chapter(ctx.root_path, str(chapter_ref or "").strip())
    if not data:
        return ToolResult(ok=False, summary=f"章节 {chapter_ref} 不存在或为空。")
    title = str(data.get("title") or "")
    outline = str(data.get("outline") or "")
    content = str(data.get("content") or "")
    lines = [f"《{title}》（{chapter_ref}）"]
    if outline:
        lines.append(f"章纲：{_clip(outline, 300)}")
    if content:
        lines.append(f"正文：{_clip(content, READ_CHAPTER_BUDGET_CHARS)}")
    else:
        lines.append("（正文未写）")
    return ToolResult(ok=True, summary="\n".join(lines))


async def _read_outline(ctx: ToolContext, scope: str = "volume", ref: str = "") -> ToolResult:
    """卷纲（六段文本）或章纲。scope=volume|chapter。"""
    from db import async_session
    from repositories import volume_repo
    from volumes.render import volume_outline_text

    scope = str(scope or "volume")
    if scope == "volume":
        async with async_session() as session:
            vols = await volume_repo.list_by_project(session, ctx.novel_id)
        vols.sort(key=lambda v: v.volume_no)
        wanted = str(ref or "").strip()
        picked = [
            v
            for v in vols
            if not wanted or wanted in (str(v.volume_no), f"第{v.volume_no}卷", v.title or "")
        ]
        if not picked:
            return ToolResult(ok=False, summary="还没有任何卷。")
        blocks = [f"第{v.volume_no}卷·{v.title or ''}\n{volume_outline_text(v)}" for v in picked]
        return ToolResult(ok=True, summary=_clip("\n\n".join(blocks), 2000))
    # chapter：章纲字段在章全量里
    result = await _read_chapter(ctx, ref)
    return result


async def _read_settings(ctx: ToolContext, area: str = "cast") -> ToolResult:
    """书内设定分区读取：premise（主线）/world（世界）/cast（名册）/hooks（伏笔）。"""
    area = str(area or "cast").strip()
    if area == "cast":
        from characters.character_service import list_characters

        from db import async_session

        async with async_session() as session:
            data = await list_characters(session, ctx.novel_id)
        items = list(data.get("items", []))
        items.sort(key=lambda it: 0 if it.get("role") == "主角" else 1)
        lines = [
            f"- {it.get('name', '')}（{it.get('role', '')}）：{it.get('persona') or ''}"
            for it in items
        ]
        if not lines:
            return ToolResult(ok=True, summary="（名册为空）")
        return ToolResult(ok=True, summary=_clip("\n".join(lines), READ_SETTINGS_BUDGET_CHARS * 2))

    from filesystem.storage import get_storage
    from volumes.ai_plan import render_red_lines, world_summary_text

    storage = get_storage()
    if area == "premise":
        story = await storage.read_yaml(ctx.root_path, "story.yaml") or {}
        arc = story.get("story_arc") or {}
        if not arc:
            return ToolResult(ok=True, summary="（主线还没有内容）")
        text = json.dumps(arc, ensure_ascii=False)
        return ToolResult(ok=True, summary=_clip(text, READ_SETTINGS_BUDGET_CHARS))
    if area == "world":
        world = await storage.read_yaml(ctx.root_path, "settings/world-setting.yaml") or {}
        if not world:
            return ToolResult(ok=True, summary="（世界设定还没有内容）")
        rules = "\n".join(render_red_lines(world))
        brief = world_summary_text(world)
        return ToolResult(
            ok=True,
            summary=_clip((f"铁律：\n{rules}\n\n" if rules else "") + brief, READ_SETTINGS_BUDGET_CHARS),
        )
    if area == "hooks":
        from prompt.context import load_active_hooks

        hooks = await load_active_hooks(ctx.novel_id)
        if not hooks:
            return ToolResult(ok=True, summary="（没有在途伏笔）")
        text = json.dumps(hooks, ensure_ascii=False, default=str)
        return ToolResult(ok=True, summary=_clip(text, READ_SETTINGS_BUDGET_CHARS))
    return ToolResult(ok=False, summary=f"未知的设定分区：{area}（可选 premise/world/cast/hooks）")


async def _read_story_state(ctx: ToolContext, upto_chapter_ref: str = "") -> ToolResult:
    from write.story_state import story_state_upto

    ref = str(upto_chapter_ref or "").strip() or None
    state = await story_state_upto(ctx.novel_id, ref)
    parts: list[str] = []
    for domain in ("settings", "relations", "items", "knowledge"):
        entries = state.get(domain) or []
        if entries:
            parts.append(f"{domain}：{json.dumps(entries, ensure_ascii=False, default=str)}")
    if not parts:
        return ToolResult(ok=True, summary="（还没有累计设定变化）")
    return ToolResult(ok=True, summary=_clip("\n".join(parts), READ_SETTINGS_BUDGET_CHARS * 2))


async def _read_progress(ctx: ToolContext) -> ToolResult:
    from chapters.frontier import frontier_info
    from db import async_session

    async with async_session() as session:
        info = await frontier_info(session, ctx.novel_id)
    chapters = info.get("chapters")
    if isinstance(chapters, list) and not chapters:
        return ToolResult(ok=True, summary="（空书：还没有任何章节）")
    summary = (
        f"frontier 章：{info.get('ref')}（第 {info.get('global_no')} 章）"
        f"｜状态：{info.get('state')}｜可写：{info.get('writable')}"
    )
    return ToolResult(ok=True, summary=summary)


# ── 写类工具（kind="write"，经 write_gate 授权梯度；走既有写服务，校验链原样生效）──

# 卷字段白名单（VolumeUpdate 字段交集；写前记 previous 供撤销）
VOLUME_FIELD_WHITELIST = (
    "title",
    "summary",
    "core_conflict",
    "ending",
    "chapter_target",
    "antagonist_type",
    "antagonist_line",
)


async def _write_volume_fields(ctx: ToolContext, ref: str, fields: dict[str, Any]) -> ToolResult:
    """改一卷的字段（白名单内）。走 volumes.service.update_volume 既有校验链；
    写前抓 previous 值进 write_log（撤销=按 previous 回写）。"""
    from db import async_session
    from novels.service import get_novel
    from volumes.schemas import VolumeUpdate
    from volumes.service import update_volume

    clean_ref = str(ref or "").strip()
    if not clean_ref.startswith("vol-"):
        clean_ref = f"vol-{clean_ref}"
    fields = fields or {}
    bad = [k for k in fields if k not in VOLUME_FIELD_WHITELIST]
    if bad:
        return ToolResult(
            ok=False, summary=f"字段不在白名单：{bad}（可写：{list(VOLUME_FIELD_WHITELIST)}）"
        )
    if not fields:
        return ToolResult(ok=False, summary="没有给出要写的字段。")

    async with async_session() as session:
        project = await get_novel(session, ctx.novel_id, ctx.user_id)
        if project is None:
            return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
        from repositories import volume_repo

        vol_no = int(clean_ref.replace("vol-", ""))
        vol = await volume_repo.get_by_volume_no(session, project.id, vol_no)
        if vol is None:
            return ToolResult(ok=False, summary=f"卷不存在：{clean_ref}")
        previous = {k: getattr(vol, k, None) for k in fields}
        body = VolumeUpdate(**fields)
        await update_volume(session, project, clean_ref, body)
    return ToolResult(
        ok=True,
        summary=f"已写入 {clean_ref}：{'、'.join(fields)}",
        meta={
            "write_log": {
                "entity": f"volume:{clean_ref}",
                "fields": fields,
                "previous": _jsonable(previous),
            }
        },
    )


def _jsonable(value: Any) -> Any:
    """SQL 标量→JSON 安全（Decimal/datetime 等 str 化）。"""
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return str(value)


# ── 注册表（封闭清单；扩展只准书内/知识库域，见能力围栏）─────────────────────

TOOL_REGISTRY: tuple[Tool, ...] = (
    Tool(
        name="read_chapter",
        kind="read",
        args_hint='{"chapter_ref": "第1章 或 ref"}',
        description="读一章的章纲与正文（截断到预算）。回答涉及具体章节内容前先调它。",
    ),
    Tool(
        name="read_outline",
        kind="read",
        args_hint='{"scope": "volume|chapter", "ref": "卷号或章 ref（可空）"}',
        description="读卷纲（六段文本）或章纲。",
    ),
    Tool(
        name="read_settings",
        kind="read",
        args_hint='{"area": "premise|world|cast|hooks"}',
        description="读书内设定分区：主线前提/世界与铁律/角色名册/在途伏笔。",
    ),
    Tool(
        name="read_story_state",
        kind="read",
        args_hint='{"upto_chapter_ref": "章 ref（可空＝全部）"}',
        description="读截至某章的累计设定/关系/物品/知识变化。",
    ),
    Tool(
        name="read_progress",
        kind="read",
        args_hint="{}",
        description="读写作进度与当前 frontier 章。",
    ),
    Tool(
        name="write_volume_fields",
        kind="write",
        args_hint='{"ref": "vol-1", "fields": {"summary": "…", "ending": "…"}}',
        description=(
            "改一卷的字段（可写：title/summary/core_conflict/ending/chapter_target/"
            "antagonist_type/antagonist_line）。受作家授权梯度管控；写入后有回执可撤销。"
        ),
        feature_key="ai-plan",
        fn=_write_volume_fields,
    ),
)

_TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOL_REGISTRY}


def get_tool(name: str) -> Tool | None:
    return _TOOLS_BY_NAME.get(str(name or "").strip())


def tool_catalog_text() -> str:
    """进动作协议 system 段的工具清单文本（封闭集——协议模板引用它）。"""
    lines = []
    for t in TOOL_REGISTRY:
        gate = f"（{t.feature_key}）" if t.feature_key else ""
        lines.append(f"- {t.name}{gate}：{t.description} 入参示例：{t.args_hint}")
    return "\n".join(lines)


async def run_tool(ctx: ToolContext, name: str, args: dict) -> ToolResult:
    """执行一个工具；未知工具返回错误结果（调用方按 final 降级的依据之一）。"""
    tool = get_tool(name)
    if tool is None or tool.fn is None:
        return ToolResult(ok=False, summary=f"未知工具：{name}")
    try:
        return await tool.fn(ctx, **(args or {}))
    except TypeError as e:
        return ToolResult(ok=False, summary=f"参数不匹配：{e}")
    except Exception as e:  # 工具失败不炸循环，作为结果回填（BLE001 豁免）
        return ToolResult(ok=False, summary=f"工具执行失败：{e}")
