"""工具注册表（c-writing-agent 批A 1.2 结构＋批A 读类五工具）。

能力围栏的物理实现（拍板④）：注册表物理封闭——只登记书内读/写/改与本地知识库
读/写/改；清单外的动作 agent 「够不着」。批A 落地读类五工具＋注册表结构；产卡
（起草/体检/发散）与写类（write_gate 管控）在批B 挂载，注册表结构此期定型。

每个工具 = {name, kind, discipline, feature_key, args_hint, fn}：
  - kind:   read（自主连环调，无档位闸）| card（生成只产卡，成本闸）| write（授权梯度）
  - discipline: anchored（锚定设定）| divergent（可添人添事，产物打标）
  - feature_key: 档位 key（读类为空串；card/write 系对齐 frontend features.ts）
  - fn: async (ctx: ToolContext, **args) -> ToolResult；工具自开自关短会话（循环体不持事务）

执行契约（c-tool-flow 批1，对齐 openworker 工具体系）：
  1. dict 契约——fn 内失败不 raise 穿透：run_tool 兜异常归一为 ToolResult(ok=False)
     （引擎侧永不见裸异常）；fn 自身可抛 CapabilityError 之类领域错误，同样被兜。
  2. 职责分离——summary 给模型（含「已交付＋任务完成」收口语义，生成类必带）；
     card.payload 给人看（产物一律人话 draft/结构化键，禁裸 JSON 上对话）。
  3. `_display` 侧车——payload 上 `_display` 键＝只给人看的元数据（模型不可见），
     apiCalls/计数类迁此键（openworker _record_result 同款语义）。
  4. 权限不在注册表——write_gate 由 loop 逐调用应用（openworker PermissionEngine
     同款分层）；域校验/去重守卫同为循环层职责，工具本体不含。
  5. 能力核单源——大模型管线抽 caps/<域>.py 纯能力函数（业务语义入参、结构化出参），
     HTTP 端点（面板）与工具同调一层；工具层禁止直调路由 handler（守卫测试钉）。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from assistant.scopes import tools_for_thread

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
    # 聚焦对象 ref（章视图当前章——「这章」的锚；router 从消息 focus 注入）
    focus_ref: str = ""
    # 页签线程（c-agent-fleet：每页签独立流程——工具声明面/域纪律按此收敛）
    thread: str = ""
    # 本 run 私有暂存（抽卡排除上次卡名等跨调用协作；随请求生灭）
    scratch: dict = field(default_factory=dict)


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
    description: str  # 模型侧契约（工具描述=契约；发散类写明「可新增、须标记」）
    # 参数 JSON Schema（c-agent-harness ToolSpec：native FC 下发供应商；text 协议
    # 模板的 args_hint 由本 schema 派生——单一参数源，勿再手写两份）
    parameters: dict | None = None
    args_hint: str = ""  # 派生缓存：__post_init__ 自 parameters 生成（入参示例）
    discipline: str = "anchored"  # anchored | divergent
    feature_key: str = ""  # 读类空串；对齐 frontend/src/lib/features.ts
    fn: Callable[..., Awaitable[ToolResult]] | None = None
    # 调度元数据（openworker _parallel_safe 同款）：low=只读低风险可并行，
    # 写类/发散类串行保序（boss 拍板 2026-11-15 调度对齐 openworker）
    risk_level: str = "high"

    def __post_init__(self) -> None:
        if not self.args_hint:
            self.args_hint = _args_hint_from_schema(self.parameters)

    def openai_spec(self) -> dict:
        """native FC 下发形态（tasks 3.1）：openai 兼容 tools 数组元素。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
                or {"type": "object", "properties": {}},
            },
        }


_TYPE_HINTS = {
    "string": "字符串",
    "integer": "整数",
    "number": "数字",
    "boolean": "布尔",
    "array": "数组",
}


def _hint_of(prop: dict) -> str:
    """单属性→入参示例文案：description 优先，枚举平铺，类型兜底。"""
    if prop.get("description"):
        return str(prop["description"])
    if prop.get("enum"):
        return "|".join(str(v) for v in prop["enum"])
    return _TYPE_HINTS.get(str(prop.get("type")), "值")


def _args_hint_from_schema(schema: dict | None) -> str:
    """JSON Schema → text 协议模板的入参示例串（嵌套对象展开一层）。"""
    if not schema:
        return "{}"
    props = schema.get("properties") or {}
    if not props:
        return "{}"
    parts: list[str] = []
    for key, spec in props.items():
        spec = spec if isinstance(spec, dict) else {}
        if spec.get("type") == "object" and spec.get("properties"):
            inner = ", ".join(
                f'"{ik}": "{_hint_of(ispec if isinstance(ispec, dict) else {})}"'
                for ik, ispec in spec["properties"].items()
            )
            parts.append(f'"{key}": {{{inner}}}')
        else:
            parts.append(f'"{key}": "{_hint_of(spec)}"')
    return "{" + ", ".join(parts) + "}"


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
    # 字段对齐 assemble_chapter 实际键（review 判例 2026-11-15：曾读 content——
    # 真键是顶层 prose（outline 本就正确），模型被喂「正文未写」假象）
    title = str(data.get("title") or "")
    outline = str(data.get("outline") or "")
    prose = str(data.get("prose") or "")
    lines = [f"《{title}》（{chapter_ref}）"]
    if outline:
        lines.append(f"章纲：{_clip(outline, 300)}")
    if prose:
        lines.append(f"正文：{_clip(prose, READ_CHAPTER_BUDGET_CHARS)}")
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
        from db import async_session
        from settings.character_service import list_characters

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
    chapters = info.get("chapters") or []
    if not chapters:
        return ToolResult(ok=True, summary="（空书：还没有任何章节）")
    # frontier 细节在 info["frontier"]（review 判例 2026-11-15：曾读顶层 ref——
    # 恒 None，模型被喂「frontier 章：None」误判书是空的）
    fr = info.get("frontier") or {}
    prose = sum(1 for ch in chapters if ch.get("has_prose"))
    archived = sum(1 for ch in chapters if ch.get("archived"))
    state = fr.get("state") or ("pending" if fr.get("pending") else "draft")
    summary = (
        f"frontier 章：{fr.get('ref')}（全书第 {fr.get('global_no')} 章）"
        f"｜状态：{state}｜可写：{fr.get('writable')}｜正文：{fr.get('ref') and ('已写' if fr.get('has_prose') else '未写')}"
        f"｜全书 {len(chapters)} 章（已归档 {archived}、有正文 {prose}）"
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
        risk_level="low",
        parameters={
            "type": "object",
            "properties": {
                "chapter_ref": {"type": "string", "description": "第1章 或 ref"},
            },
            "required": ["chapter_ref"],
        },
        description="读一章的章纲与正文（截断到预算）。回答涉及具体章节内容前先调它。",
        fn=_read_chapter,
    ),
    Tool(
        name="read_outline",
        kind="read",
        risk_level="low",
        parameters={
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["volume", "chapter"]},
                "ref": {"type": "string", "description": "卷号或章 ref（可空）"},
            },
            "required": ["scope"],
        },
        description="读卷纲（六段文本）或章纲。",
        fn=_read_outline,
    ),
    Tool(
        name="read_settings",
        kind="read",
        risk_level="low",
        parameters={
            "type": "object",
            "properties": {
                "area": {
                    "type": "string",
                    "enum": ["premise", "world", "cast", "hooks"],
                },
            },
            "required": ["area"],
        },
        description="读书内设定分区：主线前提/世界与铁律/角色名册/在途伏笔。",
        fn=_read_settings,
    ),
    Tool(
        name="read_story_state",
        kind="read",
        risk_level="low",
        parameters={
            "type": "object",
            "properties": {
                "upto_chapter_ref": {"type": "string", "description": "章 ref（可空＝全部）"},
            },
        },
        description="读截至某章的累计设定/关系/物品/知识变化。",
        fn=_read_story_state,
    ),
    Tool(
        name="read_progress",
        kind="read",
        risk_level="low",
        parameters={"type": "object", "properties": {}},
        description="读写作进度与当前 frontier 章。",
        fn=_read_progress,
    ),
    Tool(
        name="write_volume_fields",
        kind="write",
        parameters={
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "卷 ref，如 vol-1"},
                "fields": {
                    "type": "object",
                    "description": "要改的字段与值（可写字段见描述）",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "core_conflict": {"type": "string"},
                        "ending": {"type": "string"},
                        "chapter_target": {"type": "integer"},
                        "antagonist_type": {"type": "string"},
                        "antagonist_line": {"type": "string"},
                    },
                },
            },
            "required": ["ref", "fields"],
        },
        description=(
            "改一卷的字段（可写：title/summary/core_conflict/ending/chapter_target/"
            "antagonist_type/antagonist_line）。受作家授权梯度管控；写入后有回执可撤销。"
        ),
        feature_key="ai-plan",
        fn=_write_volume_fields,
    ),
)

# 产卡工具并入封闭清单（tools_cards 复用本模块的 Tool/ToolContext/ToolResult，
# 在本行之后导入避免环； Capability 围栏不变——清单仍只含书内/知识库域）
from assistant.tools_cards import CARD_TOOLS  # noqa: E402

# ── 画像工具（agent 私有；openwriter memory 模式：零审批、透明告知、可暂停）────


async def _profile_read(ctx: ToolContext) -> ToolResult:
    from assistant.profile import load_sections
    from db import async_session

    async with async_session() as session:
        sections = await load_sections(session, ctx.user_id)
    if not sections:
        return ToolResult(ok=True, summary="（画像还是空的——聊得多了我会自己记。）")
    return ToolResult(
        ok=True, summary="作家画像：" + _clip(json.dumps(sections, ensure_ascii=False), 600)
    )


async def _profile_update(
    ctx: ToolContext, updates: dict[str, Any], novel_id: str = ""
) -> ToolResult:
    """写画像（不弹授权卡；透明告知在返回摘要里；敏感类目带先问提示）。"""
    from assistant.profile import update_sections
    from db import async_session

    async with async_session() as session:
        result = await update_sections(
            session, user_id=ctx.user_id, novel_id=novel_id or ctx.novel_id, updates=updates or {}
        )
    return ToolResult(ok=bool(result.get("ok")), summary=str(result.get("notice", "")), meta=result)


PROFILE_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="profile_read",
        kind="read",
        risk_level="low",
        parameters={"type": "object", "properties": {}},
        description="读作家画像（口味/雷点/节奏/文风）。起草前先读它，别踩雷点。",
        fn=_profile_read,
    ),
    Tool(
        name="profile_update",
        kind="read",
        risk_level="high",  # 写画像（非只读）——串行保序；不弹授权卡（拍板⑤）
        parameters={
            "type": "object",
            "properties": {
                "updates": {
                    "type": "object",
                    "description": "要记住的画像字段与值（pet_peeves 雷点/naming 命名口味/节奏/文风等）",
                    "properties": {
                        "pet_peeves": {"type": "array", "items": {"type": "string"}},
                        "naming": {"type": "object"},
                    },
                },
            },
            "required": ["updates"],
        },
        description=(
            "记住作家的口味/雷点/习惯进画像（越用越懂作家）。写入时透明告知作家；"
            "敏感信息先问再记。"
        ),
        fn=_profile_update,
    ),
)

TOOL_REGISTRY: tuple[Tool, ...] = TOOL_REGISTRY + CARD_TOOLS + PROFILE_TOOLS

# 知识库工具并入（能力围栏拍板④：书内＋知识库读写改同级合法域）
from assistant.tools_kb import KB_TOOLS  # noqa: E402

TOOL_REGISTRY: tuple[Tool, ...] = TOOL_REGISTRY + KB_TOOLS

# 设定字段 AI 工具并入（boss 拍板 2026-11-15：设定卡 16 行能力走 agent——
# agent 识别任务→调工具→产物卡回对话；写回仍由作家过目后在前端完成）
from assistant.tools_settings import SETTINGS_FIELD_TOOLS  # noqa: E402

TOOL_REGISTRY: tuple[Tool, ...] = TOOL_REGISTRY + SETTINGS_FIELD_TOOLS

# 章内三面板收编（c-agent-fleet：推演/抽卡/盘点走 agent 对话——boss 拍板）
from assistant.tools_fleet import FLEET_TOOLS  # noqa: E402

TOOL_REGISTRY: tuple[Tool, ...] = TOOL_REGISTRY + FLEET_TOOLS

_TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOL_REGISTRY}


def get_tool(name: str) -> Tool | None:
    return _TOOLS_BY_NAME.get(str(name or "").strip())


def tool_catalog_text(thread: str = "") -> str:
    """进动作协议 system 段的工具清单文本（封闭集——协议模板引用它）。

    thread 非空＝按页签域收窄（c-agent-fleet：每页签独立流程——共享读＋域内
    清单）；空＝全量（兼容旧调用与启动校验路径）。"""
    allowed = tools_for_thread(thread) if thread else None
    lines = []
    for t in TOOL_REGISTRY:
        if allowed is not None and t.name not in allowed:
            continue
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
