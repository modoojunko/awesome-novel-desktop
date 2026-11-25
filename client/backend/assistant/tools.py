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

from assistant.caps.settings import SETTINGS_FIELD_WRITE, SETTINGS_PANEL_ZH
from assistant.card_digest import (
    digest_candidates,
    digest_report,
    digest_text,
)
from assistant.scopes import tools_for_thread

# 转写预算（write/chapter_writer.py 判例同风格：按中文字符预算，不按 token）
READ_CHAPTER_BUDGET_CHARS = 1500
# 设定分区读取预算（2026-11-25 boss 拍板 800→2000）：800 字读世界/主线长文会截半，
# 且本工具没有续读参数——截了模型就再也拿不到后半段（read_settings spec 同源）。
READ_SETTINGS_BUDGET_CHARS = 2000
# 名册单独上限（不跟随主基数漂移）：diverge_character_group 会把这段原样拼进生成
# 提示词，2000×2 会把名册注入从 1600 抬到 4000，属于改预算时不该顺带发生的事。
READ_SETTINGS_CAST_BUDGET_CHARS = 1600
# 检测问题行明细预算（人味 findings 的段号/原句/why/fix；朱雀段另列）
READ_PROSE_CHECKS_BUDGET_CHARS = 2000


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
    # 页面未保存标记（c-agent-page-fields-tool：read_page_fields 结果头如实标注）
    page_unsaved: tuple[str, ...] = ()
    # 屏上正文（c-agent-prose-checks：页面态上行；只进工具上下文，绝不进提示词）
    page_prose: str = ""
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


class PreviewRejected(Exception):
    """授权卡 preview 发现入参本身不合法（字段名不存在等）。

    与「读现值失败」不同：这里不该弹卡让作家看到一张写不成的授权单——router
    拦下后作为拒绝语回喂模型，让它改对参数再来（不执行、不落库）。
    """


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
    # 执行门（c-writing-agent-tier）：写类工具必需（assistant-execute，标准起）；
    # 启动校验缺声明即 fail loud；读类/产卡类恒空。
    requires_feature: str = ""
    fn: Callable[..., Awaitable[ToolResult]] | None = None
    # 调度元数据（openworker _parallel_safe 同款）：low=只读低风险可并行，
    # 写类/发散类串行保序（boss 拍板 2026-11-15 调度对齐 openworker）
    risk_level: str = "high"
    # Effect 声明（c-agent-effects）：写类工具执行成功后告知前端刷新哪个数据域
    effect_domain: str = ""  # chapters|volumes|settings|characters|hooks|""(不触发刷新)
    # Effect 动作与 target 来源（c-agent-nav）：navigate 类前端动作声明动作名＋从哪个
    # 入参取 target（例：switch_tab 声明 navigate/ui/tab）；refresh 类用默认值零声明
    effect_action: str = "refresh"  # refresh|navigate
    effect_target_from: str = ""  # 入参键名（空＝无 target）
    # 授权卡 preview 增强（c-agent-page-ops）：可选钩子（args, project→dict）。写工具
    # 用它读现值构造「字段：写入前→写入后」对比（比默认 {"tool","args"} 裸形状可读）；
    # 缺省走 write_gate._preview（人话摘要）；参数不合法时抛 PreviewRejected 不弹卡。
    preview_builder: Callable[..., Awaitable[dict] | dict] | None = None

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


async def _render_zhuque_checks(
    ctx: ToolContext, ref: str, prose: str, paras: list[str]
) -> list[str]:
    """朱雀存档段（c-agent-prose-checks）：零额度只读存档，判 AI/疑似的段列原句。

    存档只是「检测时刻」的结论：正文改过（指纹不一致）就标过期——段号与原句
    都可能对不上，只出段号/级别不出原句，防模型按错句改。
    """
    from db import async_session
    from zhuque.segmentation import fingerprint
    from zhuque.service import get_stored_result

    try:
        async with async_session() as session:
            stored = await get_stored_result(
                session, project_id=ctx.novel_id, chapter_ref=ref
            )
    except Exception:  # noqa: BLE001 — 读档失败不挡人味主体
        return ["朱雀检测：读存档失败（不影响上面的现算结果）。"]
    if not stored.get("stored"):
        return ["朱雀检测：这章没有存档（没测过或已清除）。"]
    segments = (stored.get("result") or {}).get("segments") or []
    flagged = [s for s in segments if int(s.get("label") or 0) in (1, 2)]
    checked = str(stored.get("checked_at") or "")[:16].replace("T", " ")
    stale = fingerprint(prose) != str(stored.get("prose_hash") or "")
    verdict = (
        "正文改过，结果已过期——要看准的请重新检测"
        if stale
        else "与当前正文一致"
    )
    if not flagged:
        return [f"朱雀检测（{checked} 存档｜{verdict}）：没有判 AI/疑似的段。"]
    lines = [f"朱雀检测（{checked} 存档｜{verdict}）：{len(flagged)} 段被判 AI/疑似"]
    for s in flagged:
        label = "AI" if int(s.get("label") or 0) == 1 else "疑似"
        para = int(s.get("paragraph_index") or 0)
        if stale:
            lines.append(f"- 第{para + 1}段〔{label}〕（过期档，原句不可靠，只给段号）")
        else:
            text = paras[para] if 0 <= para < len(paras) else ""
            lines.append(f"- 第{para + 1}段〔{label}〕：「{_clip(text, 120)}」")
    return lines


async def _read_prose_checks(ctx: ToolContext, chapter_ref: str = "") -> ToolResult:
    """读一章正文的检测问题行：人味检测现算＋朱雀检测存档（c-agent-prose-checks）。

    正文源：请求的正是屏上这章（focus_ref）且有屏上文本 → 用未保存文本现算，
    保证与作家屏上标注同口径；跨章问别章时只用已保存正文（绝不拿屏上文本
    冒充别章）。只读低风险；不写库、不耗额度、不外发。
    """
    from chapters.store import load_chapter
    from write.renwei_check import check_prose, split_paragraphs

    ref = str(chapter_ref or "").strip() or ctx.focus_ref.strip()
    if not ref:
        return ToolResult(
            ok=False,
            summary="没指明是哪一章——告诉我是第几章，或先打开那一章再问。",
        )
    data = await load_chapter(ctx.root_path, ref)
    if not data:
        return ToolResult(ok=False, summary=f"章节 {ref} 不存在或为空。")
    title = str(data.get("title") or "")
    saved = str(data.get("prose") or "")

    # 屏上文本只属于 focus_ref 那章：跨章请求一律回落到已保存正文
    screen = ctx.page_prose.strip() if ctx.focus_ref.strip() == ref else ""
    prose = screen or saved
    if screen:
        source = "按屏上当前正文现算（可能有未保存改动）"
    elif "正文未保存" in ctx.page_unsaved:
        source = "按已保存正文现算（屏上有未保存改动，结果可能与屏上标注不一致）"
    else:
        source = "按已保存正文现算"
    if not prose:
        return ToolResult(
            ok=True, summary=f"《{title}》（{ref}）正文还是空的，没有可检的问题行。"
        )

    paras = split_paragraphs(prose)
    report = check_prose(prose)
    findings = report.get("findings") or []
    n_err = sum(1 for f in findings if f.get("sev") == "err")
    n_warn = len(findings) - n_err
    score = report.get("score")
    score_line = (
        f"人味率 {score.get('rate')} / 100（{score.get('band')}）"
        if score
        else "短章，打不了分（先写完再测）"
    )
    if findings:
        human = (
            f"人味检测：{score_line}；问题 {len(findings)} 条"
            f"（一票否决 {n_err} · 提示 {n_warn}）"
        )
    else:
        human = f"人味检测：{score_line}；没查出问题行。"

    # 明细按预算收敛：findings 按文档顺序排（段号＋段内 err 优先）。预算放不下
    # 就从第一条放不下的起整体停——不跳过首条去捞后面的短行，否则会「跳过 err
    # 收进 warn」，与「先看上面的」的文案相悖（review P3 判例）
    detail: list[str] = []
    used = 0
    for f in findings:
        para = int(f.get("para") or 0)
        text = paras[para] if 0 <= para < len(paras) else str(f.get("hit") or "")
        level = "一票否决" if f.get("sev") == "err" else "提示"
        line = (
            f"- 第{para + 1}段〔{level}〕{f.get('rule')}：「{_clip(text, 120)}」\n"
            f"  为什么：{f.get('why')}｜改法：{f.get('fix')}"
        )
        if used + len(line) > READ_PROSE_CHECKS_BUDGET_CHARS:
            break
        detail.append(line)
        used += len(line)
    omitted = len(findings) - len(detail)
    if omitted:
        detail.append(f"（后面 {omitted} 条先不展开——先改上面的，重扫后看剩下的）")

    zq_lines = await _render_zhuque_checks(ctx, ref, prose, paras)
    head = f"《{title}》（{ref}）检测问题行·{source}"
    return ToolResult(ok=True, summary="\n".join([head, human, *detail, *zq_lines]))


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
    """书内设定分区读取：premise（主线）/world（世界）/cast（名册）/hooks（伏笔）/
    genre（题材五格现值含未填点名）/intro（简介）。"""
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
        return ToolResult(ok=True, summary=_clip("\n".join(lines), READ_SETTINGS_CAST_BUDGET_CHARS))

    if area == "genre":
        # 题材五格现值＋未填点名（c-agent-page-field-truth）——读「这本书现在填了
        # 什么」；可选值目录走 read_genre_catalog，分工不混。
        from genres.service import build_genre_truth_segments, resolve_genre_context

        gctx = await resolve_genre_context(ctx.root_path, ctx.novel_id)
        return ToolResult(ok=True, summary="\n".join(build_genre_truth_segments(gctx)))

    from filesystem.storage import get_storage
    from volumes.ai_plan import render_red_lines, world_summary_text

    storage = get_storage()
    if area == "intro":
        story = await storage.read_yaml(ctx.root_path, "story.yaml") or {}
        synopsis = str(story.get("synopsis", "") or "").strip()
        if not synopsis:
            return ToolResult(ok=True, summary="（简介还没有内容）")
        return ToolResult(ok=True, summary=_clip(synopsis, READ_SETTINGS_BUDGET_CHARS))
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
        text = (f"铁律：\n{rules}\n\n" if rules else "") + brief
        # 世界 yaml 存在但八格全空时 rules/brief 都是空串——不能回空结果给模型
        # （2026-11-25 真机：工具行空白，模型只能猜「世界观空白」）
        if not text.strip():
            return ToolResult(ok=True, summary="（世界设定还没有内容）")
        return ToolResult(ok=True, summary=_clip(text, READ_SETTINGS_BUDGET_CHARS))
    if area == "hooks":
        from prompt.context import load_active_hooks

        hooks = await load_active_hooks(ctx.novel_id)
        if not hooks:
            return ToolResult(ok=True, summary="（没有在途伏笔）")
        text = json.dumps(hooks, ensure_ascii=False, default=str)
        return ToolResult(ok=True, summary=_clip(text, READ_SETTINGS_BUDGET_CHARS))
    return ToolResult(
        ok=False,
        summary=f"未知的设定分区：{area}（可选 premise/world/cast/hooks/genre/intro）",
    )


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
    # 三态真值（c-agent-writing-flow-context）：「草稿」一词掩盖「已写完未归档」与
    # 「没写」的差异——事故实锤模型据此锚死当前章。人话口径（boss 走查 2026-11-17：
    # 内部词禁出模型口）。一次调用给全「下一章落点」决策依据。
    head = f"全书 {len(chapters)} 章（已归档 {archived}、有正文 {prose}）"
    state = str(fr.get("state") or "")
    if state == "pending":  # 占位：主线全部归档——frontier 自己就是下一章
        return ToolResult(
            ok=True,
            summary=(
                f"{head}；各章均已归档，"
                f"下一章是 第 {fr.get('global_no')} 章（待拆纲，可以开写）"
            ),
        )
    if state == "planned":
        state_note = "已排定·正文未写·未归档，可以开写"
    else:  # draft：有正文未归档
        state_note = f"正文已写 {int(fr.get('word_count') or 0):,} 字·未归档，可以继续写"
    next_ch = int(fr.get("global_no") or 0) + 1
    summary = (
        f"{head}；当前写到 第 {fr.get('global_no')} 章（{state_note}）；"
        f"再往后是 第 {next_ch} 章（还没建）"
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


# ── 正文方案读侧（c-agent-dialog-prose）：服务端组装稿＝结论卡提示词基底 ──────


async def _read_write_prompt(ctx: ToolContext, chapter_ref: str) -> ToolResult:
    """读服务端组装的本章用户提示词全文（c-agent-dialog-prose）。

    与 GET /write/prompt、生成端点同调 assemble_write_prompt 单源——卡上展示的
    提示词与实际发给正文模型的东西永不漂移。对话流恒 fresh（按当前素材重组，
    不读 write-prompt 存稿）。"""
    from db import async_session
    from novels.service import get_novel
    from write.chapter_writer import assemble_write_prompt

    chapter_ref = str(chapter_ref or "").strip()
    if not chapter_ref:
        return ToolResult(ok=False, summary="缺 chapter_ref——先确认要生成哪一章。")
    async with async_session() as db:
        project = await get_novel(db, ctx.novel_id, ctx.user_id)
        if project is None:
            return ToolResult(ok=False, summary="书不存在或不属于当前作家。")
    data = await assemble_write_prompt(
        project.root_path, chapter_ref, project.name, novel_id=project.id, fresh=True
    )
    prompt = str(data.get("prompt") or "")
    if not prompt.strip():
        return ToolResult(
            ok=False, summary="提示词组装结果为空（章纲可能还没拆）——先补章纲再生成。"
        )
    warns = list(data.get("warnings") or [])
    lines = [f"本章用户提示词（{len(prompt)} 字，服务端组装稿——方案卡提示词的基底）：", prompt]
    if not data.get("has_outline"):
        # 章纲空信号透出（review P2）：agent 据此先补章纲再出卡，别对空章纲硬生成
        lines.append("注意：本章章纲还是空的（概要/剧情条目都没有）——先补章纲再出方案卡。")
    if warns:
        lines.append("组装告警：" + "；".join(str(w) for w in warns))
    # 读侧余量 ≥ 方案卡上限（c-agent-dialog-prose：卡上限 20000）——转录里拿到全文，
    # 代理才能按需精简；曾 18000 与卡 16000 两套口径不一（review 残余风险）
    return ToolResult(ok=True, summary=_clip("\n".join(lines), 24000))


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
        name="read_prose_checks",
        kind="read",
        risk_level="low",
        parameters={
            "type": "object",
            "properties": {
                "chapter_ref": {"type": "string", "description": "第1章 或 ref；不填＝当前章"},
            },
        },
        description=(
            "看一章正文被检测标出的问题行：人味检测（本地现算：段号/原句/"
            "为什么/改法）＋朱雀检测存档（判 AI/疑似的段、结果是否过期）。"
            "作家提到人味检测、朱雀检测、标红/标黄/标记的问题行，要你复述、"
            "解释或按这几行改时，先调它。缺省当前章；要整章正文用 read_chapter。"
        ),
        fn=_read_prose_checks,
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
                    "enum": ["premise", "world", "cast", "hooks", "genre", "intro"],
                },
            },
            "required": ["area"],
        },
        description=(
            "读书内设定分区：主线前提/世界与铁律/角色名册/在途伏笔/"
            "题材五格现值（含哪些没填）/简介。"
        ),
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
        description=(
            "作家写到哪里了（各章归档/正文进度真值）。"
            "「下一章／继续写／规划」类请求拿不准落点时先查这个。"
        ),
        fn=_read_progress,
    ),
    Tool(
        name="read_write_prompt",
        kind="read",
        risk_level="low",
        parameters={
            "type": "object",
            "properties": {
                "chapter_ref": {"type": "string", "description": "章 ref（如 vol-1-ch-3）"},
            },
            "required": ["chapter_ref"],
        },
        description=(
            "读服务端组装的本章用户提示词全文（与写作端点同源；可带组装告警）。"
            "出正文方案卡前必调——方案卡里展示给作家的提示词以这份为基底，"
            "只做增改，不凭空拼装全文。"
        ),
        fn=_read_write_prompt,
    ),
    Tool(
        name="write_volume_fields",
        kind="write",
        requires_feature="assistant-execute",
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


# ── 章节版本历史读工具（c-agent-chat-memory 批9：页面有、agent 摸不到的 API 收编）──


async def _read_chapter_versions(ctx: ToolContext, chapter_ref: str = "") -> ToolResult:
    """读一章的版本历史（版本数＋最新版本字数）——作家问「写过几版」时答得出来。"""
    import datetime as _dt

    from models.chapters import Chapter, ChapterVersion
    from sqlalchemy import select as sa_select

    from db import async_session
    from models.project import Novel

    ref = str(chapter_ref or "").strip()
    if not ref:
        return ToolResult(ok=False, summary="告诉我章号（例：vol-1-ch-7）。")
    async with async_session() as session:
        rows = (
            await session.scalars(
                sa_select(ChapterVersion)
                .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
                .join(Novel, Novel.id == Chapter.project_id)
                .where(Novel.id == ctx.novel_id, Chapter.ref == ref)
                .order_by(ChapterVersion.version.desc())
            )
        ).all()
    if not rows:
        return ToolResult(ok=True, summary=f"《{ref}》还没有版本历史（版本在改稿时自动留存）。")
    import json as _json

    words_list = []
    for r in rows:
        try:
            words_list.append(len(str(_json.loads(r.snapshot or "{}").get("prose", ""))))
        except Exception:  # noqa: BLE001
            words_list.append(0)
    times = [
        _dt.datetime.fromtimestamp(r.version / 1000).strftime("%m-%d %H:%M")
        if r.version > 10**12
        else str(r.version)
        for r in rows
    ]
    lines = [f"共 {len(rows)} 个版本（新→旧）："]
    lines += [f"- {t}（约 {w} 字）" for t, w in zip(times, words_list)]
    return ToolResult(ok=True, summary="\n".join(lines[:6]))


# ── 书级记忆工具（c-agent-chat-memory 批4：四层记忆 scope 的「按书」新增层）──
# agent 自主维护的自身记忆（写作规矩）与项目决策留痕；profile_update 同款：
# kind="read"＝结构性免授权（只影响后续提示词，不碰书稿，不进写回梯度），
# risk_level="high"＝串行保序。

async def _memory_recall(ctx: ToolContext) -> ToolResult:
    """读本书我记下的全部写作规矩与项目决定（自证口径）。"""
    from assistant.memory import list_decisions, list_memories
    from db import async_session

    async with async_session() as session:
        memories = await list_memories(session, ctx.novel_id)
    decisions = await list_decisions(ctx.novel_id)
    if not memories and not decisions:
        return ToolResult(ok=True, summary="（这本书我还没记下什么规矩或决定。）")
    lines = [f"- 记忆：{m.content}" for m in memories]
    lines += [
        f"- 决定：{d.decision}" + (f"（理由：{d.reason}）" if d.reason else "")
        for d in decisions
    ]
    return ToolResult(ok=True, summary="这本书我记着：\n" + "\n".join(lines[:20]))


async def _memory_remember(ctx: ToolContext, content: str, memory_id: str = "") -> ToolResult:
    """记/改一条本书写作规矩（透明告知一句随返回摘要给作家）。"""
    from assistant.memory import upsert_memory
    from db import async_session

    async with async_session() as session:
        row = await upsert_memory(session, ctx.novel_id, content, memory_id or None)
    verb = "更新了" if memory_id else "记下了"
    return ToolResult(ok=True, summary=f"{verb}一条规矩：「{row.content[:60]}」。之后我都按这个来。")


async def _memory_forget(ctx: ToolContext, memory_id: str) -> ToolResult:
    """删一条本书写作规矩。"""
    from assistant.memory import delete_memory
    from db import async_session

    async with async_session() as session:
        removed = await delete_memory(session, ctx.novel_id, memory_id)
    if not removed:
        return ToolResult(ok=False, summary="这条规矩没找到（可能已经删过了）。")
    return ToolResult(ok=True, summary="好，这条规矩我不再记着了。")


async def _memory_decide(ctx: ToolContext, decision: str, reason: str = "") -> ToolResult:
    """留痕一条项目决定（否了什么/定了什么＋理由；决策档案 append-only）。"""
    from assistant.memory import add_decision

    row = await add_decision(ctx.novel_id, decision, reason)
    extra = f"理由也记了：{reason[:40]}。" if reason else ""
    return ToolResult(
        ok=True,
        summary=f"这个决定我记下了：「{row.decision[:60]}」。{extra}",
        meta={"decision_id": row.id},
    )


async def _memory_recall_decisions(
    ctx: ToolContext, query: str = "", limit: int = 20
) -> ToolResult:
    """查历史决定档案（c-agent-decision-archive）：子串过滤＋条数上限＋单条裁剪。

    注入段的索引层是「日期＋一句话」——agent 看到相关索引就调这里拉全文。"""
    from assistant.memory import list_decisions

    rows = await list_decisions(ctx.novel_id)
    q = (query or "").strip().lower()
    if q:
        # 分词 AND 匹配（走查实锤：模型会拿「血族 弱点」这类带空格的多词查询——
        # 整串子串匹配必 miss）；每个词都命中才算（决策＋理由合看）
        terms = [t for t in q.split() if t]
        rows = [
            d
            for d in rows
            if all(
                t in f"{d.decision} {d.reason}".lower() for t in terms
            )
        ]
    total = len(rows)
    rows = rows[: max(1, min(int(limit or 20), 50))]
    if not rows:
        hint = f"没有含「{query}」的决定。" if q else "这本书还没有留痕的项目决定。"
        return ToolResult(ok=True, summary=hint + "有新口径我随时帮你记下。")
    lines = []
    for d in rows:
        extra = f"（理由：{d.reason[:80]}）" if d.reason else ""
        lines.append(f"- [{(d.created_at or '')[:10]}] {d.decision[:160]}{extra}")
    head = f"共 {total} 条" + (f"，含「{query}」的如下（前 {len(lines)} 条）：" if q else "：")
    return ToolResult(ok=True, summary=head + "\n" + "\n".join(lines))


MEMORY_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="recall_book_memory",
        kind="read",
        risk_level="low",
        parameters={"type": "object", "properties": {}},
        description=(
            "读这本书我记下的全部写作规矩与项目决定。作家问「你记了什么/定了什么」"
            "或拿不准本书约定时先调它，如实回答。"
        ),
        fn=_memory_recall,
    ),
    Tool(
        name="remember_book_memory",
        kind="read",
        risk_level="high",  # 写记忆（非只读）——串行保序；不弹授权卡（免授权层）
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要长期记住的写作规矩或特化知识（如：全程第一人称；结尾留钩子）",
                },
                "memory_id": {
                    "type": "string",
                    "description": "要修改的已有记忆 id（来自 recall；空＝新增）",
                },
            },
            "required": ["content"],
        },
        description=(
            "作家说「记住……」「以后都……」类要求时，把规矩记到这本书上（增改皆此工具）。"
            "写入后透明告知一句。只记长期成立的约定（视角/禁忌/手法这类），"
            "一次性任务指令不进记忆——任务活在当前会话里。"
        ),
        fn=_memory_remember,
    ),
    Tool(
        name="forget_book_memory",
        kind="read",
        risk_level="high",
        parameters={
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "要删除的记忆 id（来自 recall）"},
            },
            "required": ["memory_id"],
        },
        description="作家要求忘掉某条规矩时删除对应记忆（先 recall 拿 id）。",
        fn=_memory_forget,
    ),
    Tool(
        name="remember_decision",
        kind="read",
        risk_level="high",
        parameters={
            "type": "object",
            "properties": {
                "decision": {"type": "string", "description": "方向性结论（否了什么方向/定了什么调子）"},
                "reason": {"type": "string", "description": "理由（可空）"},
            },
            "required": ["decision"],
        },
        description=(
            "作家明确拍板或否决某个方向时留痕（带理由更好），之后同类建议不再重复。"
            "写入后透明告知一句。"
        ),
        fn=_memory_decide,
    ),
    Tool(
        name="recall_decisions",
        kind="read",
        risk_level="low",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "关键词（按决定/理由子串过滤；空＝最近的）"},
                "limit": {"type": "integer", "description": "最多返回条数（默认 20）"},
            },
            "required": [],
        },
        description=(
            "查这本书的历史项目决定档案（含很久以前的）。作家提起旧决定/旧口径"
            "（「之前不是说…」「上次定的…」）或注入段索引里那条相关时调它拉全文，"
            "如实按档案回答，不凭印象编。"
        ),
        fn=_memory_recall_decisions,
    ),
)

# 章节版本历史读工具并入（批9：版本历史页面有、agent 摸不到——收编）
VERSIONS_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="read_chapter_versions",
        kind="read",
        risk_level="low",
        parameters={
            "type": "object",
            "properties": {
                "chapter_ref": {"type": "string", "description": "章 ref（例：vol-1-ch-7）"},
            },
            "required": ["chapter_ref"],
        },
        description=(
            "读一章的版本历史（改稿自动留存的版本数＋最新一版字数）。"
            "作家问「写过几版/之前那版还在吗」时先调它。"
        ),
        fn=_read_chapter_versions,
    ),
)
TOOL_REGISTRY: tuple[Tool, ...] = TOOL_REGISTRY + VERSIONS_TOOLS


# ── 结构管理动作（c-agent-tools-expand：写类走授权梯度）──────────────
async def _confirm_chapter(ctx, chapter_ref: str = ""):
    from assistant.caps.chapter import confirm_chapter_cap

    ref = str(chapter_ref or "").strip()
    if not ref:
        return _struct_fail("告诉我章号（例：vol-1-ch-7）。")
    result = await confirm_chapter_cap(ctx.novel_id, ref, ctx.user_id)
    warnings = result.get("warnings") or []
    extra = f"门槛提醒：{'、'.join(warnings)}" if warnings else "门槛已满足。"
    return _struct_ok(f"已确认《{ref}》的章纲。{extra}")


async def _unconfirm_chapter(ctx, chapter_ref: str = ""):
    from assistant.caps.chapter import unconfirm_chapter_cap

    ref = str(chapter_ref or "").strip()
    if not ref:
        return _struct_fail("告诉我章号。")
    await unconfirm_chapter_cap(ctx.novel_id, ref, ctx.user_id)
    return _struct_ok(f"《{ref}》的章纲确认已撤回，回到草稿态，改完可以再确认。")


async def _archive_chapter(ctx, chapter_ref: str = ""):
    from assistant.caps.chapter import archive_chapter_cap

    ref = str(chapter_ref or "").strip()
    if not ref:
        return _struct_fail("告诉我章号。")
    result = await archive_chapter_cap(ctx.novel_id, ref, ctx.user_id)
    note = "已归档。" if result.get("status") == "archived" else "已受理归档。"
    return _struct_ok(f"《{ref}》{note}")


async def _unarchive_chapter(ctx, chapter_ref: str = ""):
    from assistant.caps.chapter import unarchive_chapter_cap

    ref = str(chapter_ref or "").strip()
    if not ref:
        return _struct_fail("告诉我章号。")
    await unarchive_chapter_cap(ctx.novel_id, ref, ctx.user_id)
    return _struct_ok(f"《{ref}》已恢复为可编辑态。")


async def _add_volume(ctx, title: str = ""):
    from assistant.caps.chapter import add_volume_cap

    result = await add_volume_cap(ctx.novel_id, ctx.user_id, str(title or "").strip())
    vol = result.get("volume") or {}
    return _struct_ok(f"已新建 {vol.get('title') or '新卷'}，可以开始铺这一卷了。")


async def _add_chapter(ctx, volume_ref: str = "vol-1", title: str = ""):
    from assistant.caps.chapter import add_chapter_cap

    result = await add_chapter_cap(ctx.novel_id, ctx.user_id, str(volume_ref or "vol-1"), str(title or "").strip())
    ref = result.get("ref") or ""
    return _struct_ok(f"已排上新章 {ref}，可以直接去写正文。")


# ── 世界观三件（读/产卡类，不写回）────────────────────────────────────


async def _draft_worldbuilding(ctx, topic: str = "", shape: str = "text", current: str = ""):
    from assistant.caps.world import draft_world_cap

    if not str(topic or "").strip():
        return _struct_fail("告诉我要素名（力量体系/代价/历史/势力/铁律……）。")
    result = await draft_world_cap(
        ctx.novel_id, ctx.user_id,
        {"topic": str(topic).strip(), "shape": str(shape or "text"), "current": str(current or "")},
    )
    draft = result.get("draft") or result.get("content") or result
    # 生成核偶发把 {value: 文本} 包成 dict 或再包一层 JSON 串（真机实锤）——
    # 剥回纯文本，卡面可读、采纳写回不会把 JSON 串存进世界字段
    # （c-agent-panel-consolidate 走查补刀：dict 形态此前漏剥）
    if isinstance(draft, dict):
        draft = draft.get("value") or draft.get("draft") or draft.get("text") or _json_dump(draft)
    if isinstance(draft, str):
        try:
            inner = json.loads(draft)
            if isinstance(inner, dict):
                draft = inner.get("value") or inner.get("draft") or inner.get("text") or draft
        except (ValueError, TypeError):
            pass
    text = draft if isinstance(draft, str) else _json_dump(draft)
    topic_text = str(topic).strip()
    return ToolResult(
        ok=True,
        summary=digest_text(f"世界观「{topic_text}」候选已出", text),
        card={"kind": "text", "payload": {"topic": topic_text, "draft": text, "origin": "divergent"}},
    )


def _world_check_rows(result: dict) -> list[dict[str, str]]:
    """世界体检行归一：{name,status,note}（各核出参名不同，摘要统一按这三键渲染）。"""
    rows: list[dict[str, str]] = []
    for item in result.get("items") or result.get("checks") or []:
        if isinstance(item, dict):
            rows.append(
                {
                    "name": str(item.get("name") or item.get("code") or "检查项"),
                    "status": str(item.get("status") or item.get("level") or "warn"),
                    "note": str(item.get("note") or item.get("text") or item.get("msg") or ""),
                }
            )
        else:
            rows.append({"name": "检查项", "status": "warn", "note": str(item)})
    return rows


def _world_check_digest(result: dict) -> str:
    """世界观体检摘要：问题条目逐条（带判定），达标条目只计数。"""
    rows = _world_check_rows(result)
    verdict = str(result.get("verdict") or "").strip()
    head = f"世界观体检完成（{verdict}）" if verdict else "世界观体检完成"
    return digest_report(
        head,
        rows,
        status_of=lambda it: it["status"],
        render=lambda it: f"{it['name']}：{it['note'] or '需要处理'}",
    )


async def _check_worldbuilding(ctx):
    from assistant.caps.world import check_world_cap

    result = await check_world_cap(ctx.novel_id, ctx.user_id, {})
    payload_items = _as_check_items(result.get("items") or result.get("checks") or [])
    return ToolResult(
        ok=True,
        summary=_world_check_digest(result),
        card={
            "kind": "report",
            "payload": {"report": [{"name": "世界观一致性", "items": payload_items}]},
        },
    )


async def _default_chapter_ref(ctx: ToolContext) -> str:
    """当前写作章 ref：先聚焦对象，再前沿章；都没有回空串（调用方给人话出口）。"""
    ref = str(ctx.focus_ref or "").strip()
    if ref:
        return ref
    from chapters.frontier import frontier_info
    from db import async_session

    async with async_session() as db:
        info = await frontier_info(db, ctx.novel_id)
    frontier = info.get("frontier") if isinstance(info, dict) else {}
    return str((frontier or {}).get("ref") or "")


async def _lore_suggest(ctx, chapter_ref: str = ""):
    """从指定章（缺省当前写作章）提世界要素建议；只出卡过目，写回走世界面板。"""
    from fastapi import HTTPException

    from assistant.caps.world import lore_suggest_cap

    ref = str(chapter_ref or "").strip() or await _default_chapter_ref(ctx)
    if not ref:
        # 与「正文为空」同一种失败语义（ok=False）：都是「现在提不了」，只差下一步
        return ToolResult(
            ok=False,
            summary="全书还没有写过正文的章——先去正文页写一章，再来提世界要素。",
        )
    try:
        result = await lore_suggest_cap(ctx.novel_id, ctx.user_id, {"chapter_ref": ref})
    except HTTPException as e:
        detail = str(e.detail)
        # 空章是常见入口（刚建章还没写），给可执行的下一步而不是接口原话
        if "正文为空" in detail:
            return ToolResult(
                ok=False,
                summary=f"「{ref}」这章正文还是空的——先写一章正文，再来提世界要素。",
            )
        return ToolResult(ok=False, summary=detail)
    lore = [it for it in (result.get("lore") or result.get("suggestions") or []) if isinstance(it, dict)]
    # pick 卡渲染要 name/rationale；key/value/set/origin 一并保留——
    # 展示映射不许丢数据（写回 /settings/world/lore-apply 认的是这四个键）
    candidates = [
        {
            "name": f"{it.get('set') or '世界'}·{it.get('key') or '要素'}",
            "rationale": str(it.get("value") or ""),
            "key": str(it.get("key") or ""),
            "value": str(it.get("value") or ""),
            "set": str(it.get("set") or ""),
            **({"origin": str(it["origin"])} if it.get("origin") else {}),
        }
        for it in lore
    ]
    if not candidates:
        return ToolResult(
            ok=True,
            summary=f"「{ref}」这章没提出新的世界要素。",
            card={"kind": "pick", "payload": {"candidates": [], "chapter_ref": ref}},
        )
    summary = digest_candidates(
        f"「{ref}」世界要素建议",
        candidates,
        lambda c: f"{c['name']}：{c['rationale']}",
    )
    return ToolResult(
        ok=True,
        summary=summary,
        card={"kind": "pick", "payload": {"candidates": candidates, "chapter_ref": ref}},
    )


def _json_dump(v):
    import json as _json

    return _json.dumps(v, ensure_ascii=False)


def _as_check_items(items):
    out = []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                status = str(it.get("status") or it.get("level") or "warn")
                text = str(it.get("text") or it.get("msg") or "").strip()
                if not text:
                    # 世界体检出参是 {name,status,note}——旧兜底 str(it) 会把 dict
                    # repr 直接画到报告卡上（人话红线）；按 name：note 收口
                    name = str(it.get("name") or "").strip()
                    note = str(it.get("note") or "").strip()
                    text = f"{name}：{note}" if name and note else name or note
                out.append({"status": status, "text": text})
            else:
                out.append({"status": "warn", "text": str(it)})
    return out


# ── fn 绑定（延迟到模块底——工具函数已全量定义）────────────────────────

_confirm_chapter_fn = _confirm_chapter
_unconfirm_chapter_fn = _unconfirm_chapter
_archive_chapter_fn = _archive_chapter
_unarchive_chapter_fn = _unarchive_chapter
_add_volume_fn = _add_volume
_add_chapter_fn = _add_chapter
_draft_worldbuilding_fn = _draft_worldbuilding
_check_worldbuilding_fn = _check_worldbuilding
_lore_suggest_fn = _lore_suggest


STRUCTURE_TOOLS: tuple = (
    Tool(
        name="confirm_chapter", kind="write", risk_level="high", effect_domain="chapters", requires_feature="assistant-execute",
        parameters={"type": "object", "properties": {"chapter_ref": {"type": "string", "description": "章 ref（例：vol-1-ch-7）"}}, "required": ["chapter_ref"]},
        description="确认一章的章纲（作家说「确认章纲」类要求时代办）。授权卡批复后执行。",
        fn=_confirm_chapter_fn,
    ),
    Tool(
        name="unconfirm_chapter", kind="write", risk_level="high", effect_domain="chapters", requires_feature="assistant-execute",
        parameters={"type": "object", "properties": {"chapter_ref": {"type": "string", "description": "章 ref"}}, "required": ["chapter_ref"]},
        description="撤回一章的章纲确认（回到草稿态，改完可再确认）。", fn=_unconfirm_chapter_fn,
    ),
    Tool(
        name="archive_chapter", kind="write", risk_level="high", effect_domain="chapters", requires_feature="assistant-execute",
        parameters={"type": "object", "properties": {"chapter_ref": {"type": "string", "description": "章 ref"}}, "required": ["chapter_ref"]},
        description="归档一章（有正文的章才能归档；归档后进已归档列表）。", fn=_archive_chapter_fn,
    ),
    Tool(
        name="unarchive_chapter", kind="write", risk_level="high", effect_domain="chapters", requires_feature="assistant-execute",
        parameters={"type": "object", "properties": {"chapter_ref": {"type": "string", "description": "章 ref"}}, "required": ["chapter_ref"]},
        description="取消一章的归档（恢复为可编辑态）。", fn=_unarchive_chapter_fn,
    ),
    Tool(
        name="add_volume", kind="write", risk_level="high", effect_domain="volumes", requires_feature="assistant-execute",
        parameters={"type": "object", "properties": {"title": {"type": "string", "description": "卷名（可空，服务端兜底「第N卷」）"}}, "required": []},
        description="新建一卷（作家说「开新卷/新增一卷」类要求时代办）。", fn=_add_volume_fn,
    ),
    Tool(
        name="add_chapter", kind="write", risk_level="high", effect_domain="chapters", requires_feature="assistant-execute",
        parameters={"type": "object", "properties": {"volume_ref": {"type": "string", "description": "卷 ref（例：vol-1；缺省 vol-1）"}, "title": {"type": "string", "description": "章名（可空）"}}, "required": []},
        description="新增一章（排到指定卷的下一章）。", fn=_add_chapter_fn,
    ),
)

WORLD_TOOLS: tuple = (
    Tool(
        name="draft_worldbuilding", kind="card", risk_level="high", feature_key="settings-ai-fields",
        parameters={"type": "object", "properties": {"topic": {"type": "string", "description": "世界要素名（力量体系/代价/历史/势力/铁律……任意）"}, "shape": {"type": "string", "enum": ["text", "kv", "faction"], "description": "落格形状"}, "current": {"type": "string", "description": "当前格已有文字（半稿也算，模板在其上补全不推翻）"}}, "required": ["topic"]},
        description="按主题起草世界观候选（一段话/条目/势力行）。设定·世界观语境用；产物过目采纳。", fn=_draft_worldbuilding_fn,
    ),
    Tool(
        name="check_worldbuilding", kind="card", risk_level="high", feature_key="settings-ai-fields",
        parameters={"type": "object", "properties": {}},
        description="世界观一致性体检：简介×题材×世界三方对照，逐项三态只提醒不拦。", fn=_check_worldbuilding_fn,
    ),
    Tool(
        name="lore_suggest", kind="card", risk_level="high", feature_key="settings-ai-fields",
        parameters={
            "type": "object",
            "properties": {
                "chapter_ref": {
                    "type": "string",
                    "description": "章 ref（例：vol-1-ch-7；缺省＝当前写作章）",
                },
            },
        },
        description="从指定章（缺省当前写作章）提世界观要素建议（传说/设定候选，不落库，写回走世界面板）。",
        fn=_lore_suggest_fn,
    ),
)



def _struct_fail(msg: str):
    return ToolResult(ok=False, summary=msg)


def _struct_ok(msg: str):
    return ToolResult(ok=True, summary=msg)


# 书结构总览读工具并入（零内容元数据——agent 不拉全文也能答进度/状态问题）
from assistant.tools import Tool as _ToolCls  # noqa: E402


async def _read_book_structure(ctx: ToolContext) -> ToolResult:
    """全书卷章结构总览（零内容——只有元数据：标题/状态/字数/归档/章纲确认）。

    作家问「写到哪了/第几章有多少字/哪些章还没归档/每卷什么状态」时调它，
    不需要逐章 read_chapter 拉 full text 烧 token。"""
    from sqlalchemy import select

    from db import async_session
    from models.chapter import Chapter
    from models.volume import Volume

    _STATUS_ZH = {"draft": "草稿", "confirmed": "章纲已确认", "archived": "已归档"}
    _OUTLINE_ZH = {"unfilled": "未填", "in_progress": "写中", "confirmed": "已确认", "draft": "草稿"}

    async with async_session() as session:
        vols = (
            await session.scalars(
                select(Volume).where(Volume.project_id == ctx.novel_id).order_by(Volume.volume_no)
            )
        ).all()
        chs = (
            await session.scalars(
                select(Chapter)
                .where(Chapter.project_id == ctx.novel_id, Chapter.ghost_of.is_(None))
                .order_by(Chapter.volume_id, Chapter.chapter_no)
            )
        ).all()

    lines = [f"全书 {len(vols)} 卷 {len(chs)} 章："]
    for v in vols:
        vol_chs = [c for c in chs if c.volume_id == v.id]
        archived = sum(1 for c in vol_chs if c.status == "archived")
        words = sum(c.word_count for c in vol_chs)
        lines.append(
            f"第 {v.volume_no} 卷《{v.title}》：{len(vol_chs)} 章（已归档 {archived}）、共 {words} 字"
        )
    for c in chs:
        st = _STATUS_ZH.get(c.status, c.status)
        ol = _OUTLINE_ZH.get(c.outline_status, c.outline_status)
        wc = f"{c.word_count} 字" if c.word_count else "空"
        lines.append(f"- {c.ref}《{c.title}》{st}·{wc}·章纲{ol}")
    return ToolResult(ok=True, summary="\n".join(lines))

BOOK_STRUCTURE_TOOLS: tuple[Tool, ...] = (
    _ToolCls(
        name="read_book_structure",
        kind="read",
        risk_level="low",
        parameters={"type": "object", "properties": {}},
        description=(
            "读全书卷章结构总览（零内容元数据：每卷章数/归档数/字数；"
            "每章标题/状态/字数/章纲确认态）。作家问「写到哪了/第几章多少字/"
            "哪些章还没归档/卷一什么状态」类问题时调它——不用逐章 read_chapter。"
        ),
        fn=_read_book_structure,
    ),
)
TOOL_REGISTRY: tuple[Tool, ...] = TOOL_REGISTRY + BOOK_STRUCTURE_TOOLS


# ── 页签切换（c-agent-nav）：服务端只做白名单校验＋发 navigate effect（前端真实
# 切页签）；kind=read 免授权；域封闭＝七章节页签域可见（scopes._DOMAIN_TOOLS），
# 卷纲/设定/预览/默认域不见此工具。话术契约进 description——调用前话术用进行时
# （「我切过去」），SHALL NOT 预告「已切」：切成没切成由系统做。

_TAB_ZH = {
    "og": "章纲",
    "prose": "正文",
    "settings": "设定",
    "relations": "角色关系",
    "hooks": "伏笔",
    "actions": "操作",
    "style": "文风",
}


async def _switch_tab(ctx, tab: str = ""):
    tab = str(tab or "").strip()
    if tab not in _TAB_ZH:
        opts = "、".join(f"{k}（{v}）" for k, v in _TAB_ZH.items())
        return ToolResult(ok=False, summary=f"没有「{tab or '（空）'}」这个页签——可选的是：{opts}。")
    thread = str(getattr(ctx, "thread", "") or "")
    if not thread.startswith("ch:"):
        return ToolResult(ok=False, summary="这里不是章节页——打开左侧某一章后，我再帮你切页签。")
    return ToolResult(ok=True, summary=f"已切到{_TAB_ZH[tab]}页签。")


async def _navigate(ctx, target: str = ""):
    target = str(target or "").strip()
    parts = [p for p in target.split(":") if p]
    _VIEW_ZH = {"novels": "书架", "workbench": "写作工作台", "settings": "设定面板", "preview": "预览"}
    if not parts or parts[0] not in _VIEW_ZH:
        opts = "、".join(f"{k}（{v}）" for k, v in _VIEW_ZH.items())
        return ToolResult(
            ok=False,
            summary=f"目标不认识——格式：视图，或 视图:章ref[:页签]。视图可选：{opts}。",
        )
    view = parts[0]
    if len(parts) > 1 and view != "workbench":
        return ToolResult(ok=False, summary="章定位只在写作工作台里支持——target 写成 workbench:章ref[:页签]。")
    if len(parts) > 2 and parts[2] not in _TAB_ZH:
        opts = "、".join(_TAB_ZH)
        return ToolResult(ok=False, summary=f"没有「{parts[2]}」这个页签——可选的是：{opts}。")
    # 章存在性校验（review P3）：格式合法≠章存在——不存在的 ref 会让前端选到空
    if len(parts) > 1:
        from sqlalchemy import select

        from db import async_session
        from models.chapter import Chapter
        from models.project import Novel

        async with async_session() as db:
            row = (
                await db.scalars(
                    select(Chapter)
                    .join(Novel, Novel.id == Chapter.project_id)
                    .where(Novel.id == ctx.novel_id, Chapter.ref == parts[1])
                )
            ).first()
        if row is None:
            return ToolResult(ok=False, summary=f"没有「{parts[1]}」这一章——确认一下章号再试。")
    return ToolResult(ok=True, summary=f"已切到{_VIEW_ZH[view]}" + ("（系统执行跳转）。"))


NAV_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="switch_tab", kind="read", risk_level="low",
        effect_action="navigate", effect_domain="ui", effect_target_from="tab",
        parameters={"type": "object", "properties": {"tab": {"type": "string", "enum": list(_TAB_ZH), "description": "目标页签：og=章纲、prose=正文、settings=设定、relations=角色关系、hooks=伏笔、actions=操作、style=文风"}}, "required": ["tab"]},
        description=(
            "切换作家正在看的章节页签（作家说「切到正文/给我看章纲」类要求时调）。"
            "调用前的话术用进行时（「我切过去」），不要说「已切」——切换由系统执行。"
            "只在当前这一章的页签间切换；跨章、跨大页签（写作/设定/预览）做不到就直说。"
        ),
        fn=_switch_tab,
    ),
    # 跨视图/跨章导航（c-agent-page-ops）：switch_tab 的泛化——大视图切换＋打开
    # 任意章任意页签。target 编码「view[:chapter_ref[:tab]]」，前端 onEffect 解析
    # （dirty 守卫照手点语义）。kind=read 免授权；_SHARED_TOOLS 全域可见。
    Tool(
        name="navigate", kind="read", risk_level="low",
        effect_action="navigate", effect_domain="ui", effect_target_from="target",
        parameters={
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "目标位置编码：view 或 view:章ref[:页签]。"
                        "view=novels(书架)|workbench(写作)|settings(设定)|preview(预览)；"
                        "章 ref 形如 vol-1-ch-3；页签=og|prose|settings|relations|hooks|actions|style。"
                        "例：workbench:vol-1-ch-3:prose（打开第3卷第3章的正文）、settings（设定面板）。"
                    ),
                }
            },
            "required": ["target"],
        },
        description=(
            "跳转到指定页面（作家说「打开第3章正文/去设定面板/回书架」类要求时调）。"
            "调用前的话术用进行时（「我切过去」），不要说「已切」——切换由系统执行。"
            "页面有未保存修改时系统会照手点语义拦截，作家确认后才走。"
        ),
        fn=_navigate,
    ),
)
TOOL_REGISTRY: tuple[Tool, ...] = TOOL_REGISTRY + NAV_TOOLS

TOOL_REGISTRY: tuple[Tool, ...] = TOOL_REGISTRY + STRUCTURE_TOOLS + WORLD_TOOLS + MEMORY_TOOLS

from assistant.tools_plan import PLAN_TOOLS  # noqa: E402

TOOL_REGISTRY: tuple[Tool, ...] = TOOL_REGISTRY + PLAN_TOOLS



_KIND_LABEL = {"read": "读", "card": "产卡·不写书", "write": "写·授权"}

# 能力边界块：与注册表同源注入（c-agent-action-contract）。字节稳定，不依赖
# 提示词包更新——缺包/旧包在位时同样生效。
_BOUNDARY_LINES = (
    "清单外不存在：不得声称调用或承诺清单外的工具。",
    (
        "生成正文走方案卡：先按本章剧情取材（read_chapter＋kb_search_craft 匹配写法条目），"
        "再 read_write_prompt 取提示词基底，draft_prose_plan 出卡（含提示词全文与选中条目）；"
        "作家点卡上「开始生成」才生成——不得在对话里直接输出章节正文代笔。"
    ),
    (
        "产卡类工具只出草稿，不写书：不得说「已落库／已保存／我写完了」；"
        "写入走对应面板或授权卡。"
    ),
)


def tool_catalog_text(thread: str = "") -> str:
    """进动作协议 system 段的工具清单文本（封闭集——协议模板引用它）。

    thread 非空＝按页签域收窄（c-agent-fleet：每页签独立流程——共享读＋域内
    清单）；空＝全量（兼容旧调用与启动校验路径）。清单末尾附能力边界块
    （c-agent-action-contract）：负向能力与产卡语义不靠模型自行推断。"""
    allowed = tools_for_thread(thread) if thread else None
    lines = []
    has_plan = False
    for t in TOOL_REGISTRY:
        if allowed is not None and t.name not in allowed:
            continue
        gate = f"（{t.feature_key}）" if t.feature_key else ""
        kind = _KIND_LABEL.get(t.kind, t.kind)
        lines.append(
            f"- {t.name}〔{kind}〕{gate}：{t.description} 入参示例：{t.args_hint}"
        )
        if t.name == "update_plan":
            has_plan = True
    boundary = list(_BOUNDARY_LINES)
    if has_plan:
        boundary.append(
            "一条消息有多件独立交付物时，先调 update_plan 建清单，再逐件做；"
            "收口说清哪几件没做。"
        )
    return "\n".join(lines) + "\n\n边界：\n" + "\n".join(f"- {b}" for b in boundary)


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


# ── 书结构总览读工具（c-agent-tools-expand 批9 续：agent 不拉全文也能答进度/状态问题）──



# ── 字段级页面写（c-agent-page-ops）：作家字段级写改，全过 write_gate 授权策略 ──
# 形态：读现值→构造字段前后对比 preview（确认档弹卡逐字段可见）→caps 落库
# （patch-gates/merge，未提及字段零触碰）→write_log 进撤销数据源。均无 feature_key
# （作家改自己的字段不吃付费闸，同结构工具惯例）。effect：写后域刷新（dirty 守卫
# 在前端）。

async def _preview_write_chapter_fields(args: dict, project):
    """授权卡 preview：读现值构造「字段：写入前→写入后」。

    章不存在/字段名不在白名单→PreviewRejected（不弹卡，回喂模型改对再来）；
    读现值阶段的其余失败回落默认形状。
    """
    from sqlalchemy import select

    from assistant.caps.chapter import CHAPTER_FIELD_WRITE_KEYS, _chapter_prev_value
    from chapters.store import load_chapter
    from db import async_session
    from models.project import Novel

    ref = str(args.get("chapter_ref") or "")
    fields = args.get("fields") if isinstance(args.get("fields"), dict) else {}
    if not ref:
        raise PreviewRejected("没说要改哪一章，这一步先不写（章 ref 如 vol-1-ch-3）。")
    if not fields:
        raise PreviewRejected("没说要改这一章的哪些字段，这一步先不写。")
    unknown = [k for k in fields if k not in CHAPTER_FIELD_WRITE_KEYS]
    if unknown:
        raise PreviewRejected(
            f"章纲里没有这些字段：{'、'.join(map(str, unknown))}，这一步先不写。能写的是："
            + "、".join(CHAPTER_FIELD_WRITE_KEYS.values())
            + "。"
        )
    if project is None:
        return {}
    async with async_session() as db:
        project_row = (
            await db.scalars(select(Novel).where(Novel.id == project.id))
        ).first()
    if project_row is None:
        return {}
    current = await load_chapter(project_row.root_path, ref)
    if not current:
        raise PreviewRejected(f"没找到 {ref} 这一章——先确认章 ref 再来。")

    changes = []
    for key, value in fields.items():
        changes.append(
            {
                "field": key,
                "label": CHAPTER_FIELD_WRITE_KEYS[key],
                "before": _chapter_prev_value(current, key),
                "after": value,
            }
        )
    return {"tool": "write_chapter_fields", "entity": f"chapter:{ref}", "changes": changes}


async def _preview_write_settings_field(args: dict, project):
    """授权卡 preview：读现值构造字段前后对比。

    参数本身不合法（面板/字段名不存在）→ PreviewRejected：router 不弹卡，把可选
    字段回喂模型改对再来——作家不该看到一张写不成的授权单（2026-11-21 实锤：
    story.premise 弹卡裸 JSON）。读现值失败才回落（闸不受影响）。
    """
    from assistant.caps.settings import read_settings_field

    stype = str(args.get("stype") or "")
    field = str(args.get("field") or "")
    value = args.get("value")
    if not stype or not field:
        raise PreviewRejected("没说要写哪个面板的哪个字段，这一步先不写。")
    panel = SETTINGS_PANEL_ZH.get(stype)
    if panel is None:
        raise PreviewRejected(
            f"没有「{stype}」这个设定面板，这一步先不写。设定页只有："
            + "、".join(f"{zh}（{key}）" for key, zh in SETTINGS_PANEL_ZH.items())
            + "。"
        )
    label = SETTINGS_FIELD_WRITE[stype].get(field)
    if label is None:
        raise PreviewRejected(
            f"{panel}面板里没有「{field}」这个字段，这一步先不写。这一页能写的是："
            + "、".join(f"{zh}（{key}）" for key, zh in SETTINGS_FIELD_WRITE[stype].items())
            + "。"
        )
    before = ""
    if project is not None:
        try:
            before = await read_settings_field(project.id, stype, field, "")
        except Exception:  # noqa: BLE001——读不到现值就只给 after（闸不受影响）
            before = ""
    return {
        "tool": "write_settings_field",
        "entity": f"settings:{stype}:{field}",
        "changes": [{"field": field, "label": label, "before": before, "after": value}],
    }


async def _write_chapter_fields(ctx, chapter_ref: str = "", fields: dict | None = None):
    from assistant.caps.chapter import write_chapter_fields_cap

    ref = str(chapter_ref or "").strip()
    if not ref:
        return ToolResult(ok=False, summary="没说要写哪一章——带上章 ref（如 vol-1-ch-3）。")
    if not isinstance(fields, dict) or not fields:
        return ToolResult(ok=False, summary="没有要写的字段。")
    res = await write_chapter_fields_cap(ctx.novel_id, ref, ctx.user_id, fields)
    labels = "、".join(res.get("labels") or [])
    return ToolResult(
        ok=True,
        summary=f"已写入：{labels}（{ref}）。",
        meta={"write_log": {"entity": res["entity"], "changes": res["changes"]}},
    )


async def _write_settings_field(ctx, stype: str = "", field: str = "", value=None):
    from assistant.caps.settings import write_settings_field_cap

    st = str(stype or "").strip()
    fd = str(field or "").strip()
    if not st or not fd:
        return ToolResult(ok=False, summary="没说要写哪个面板的哪个字段。")
    res = await write_settings_field_cap(ctx.novel_id, st, fd, value, ctx.user_id)
    panel = SETTINGS_PANEL_ZH.get(st, st)
    shown = SETTINGS_FIELD_WRITE.get(st, {}).get(fd, fd)
    where = shown if shown == panel else f"{panel} · {shown}"
    return ToolResult(
        ok=True,
        summary=f"已写入：{where}。",
        meta={"write_log": {"entity": res["entity"], "changes": [{"field": fd, "before": res["before"], "after": res["after"]}]}},
    )


PAGE_OPS_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="write_chapter_fields", kind="write", risk_level="high", requires_feature="assistant-execute",
        effect_domain="chapters",
        parameters={
            "type": "object",
            "properties": {
                "chapter_ref": {"type": "string", "description": "章 ref，如 vol-1-ch-3"},
                "fields": {
                    "type": "object",
                    "description": (
                        "要写的章纲字段与值（只写给出的键，其余不动）：summary=概要、"
                        "characters=出场角色(字符串数组)、challenge=碰到的挑战、plot_stage=阶段、"
                        "ladder_exit=章末落点、plot_items=剧情条目(字符串数组)、"
                        "required_changes=必须完成的变化(字符串数组)、prohibitions=禁则(字符串数组)、"
                        "primary_mood=主情绪、word_target=目标字数(数字)。"
                    ),
                },
            },
            "required": ["chapter_ref", "fields"],
        },
        description=(
            "写/改某一章的章纲字段（概要、挑战、落点、主情绪等；逐字段 patch，未提及的不动）。"
            "写操作：确认档先弹授权卡给你过目字段前后，自动档直接落库并带回执。"
            "作家没明确要写就别调。"
        ),
        fn=_write_chapter_fields,
        preview_builder=_preview_write_chapter_fields,
    ),
    Tool(
        name="write_settings_field", kind="write", risk_level="high", requires_feature="assistant-execute",
        effect_domain="settings",
        parameters={
            "type": "object",
            "properties": {
                "stype": {"type": "string", "enum": ["genre", "story", "world"], "description": "面板：genre=题材四格、story=简介、world=世界观条目"},
                "field": {
                    "type": "string",
                    "enum": [
                        k for fields in SETTINGS_FIELD_WRITE.values() for k in fields
                    ],
                    "description": "字段名（必须与 stype 匹配）：genre→core_promise/forbidden_list/cost_ratio/battlefield；story→synopsis；world→no_power/stage/power/cost/history/factions/constraints/extra。没有 premise——简介用 story.synopsis。",
                },
                "value": {"description": "字段新值（文本；genre.cost_ratio 为 1-10 数字）"},
            },
            "required": ["stype", "field", "value"],
        },
        description=(
            "写/改设定面板的某个字段（题材四格、简介、世界观条目；单字段合并写，其余不动）。"
            "写操作：确认档先弹授权卡给你过目字段前后，自动档直接落库并带回执。"
            "作家没明确要写就别调。"
        ),
        fn=_write_settings_field,
        preview_builder=_preview_write_settings_field,
    ),
)
TOOL_REGISTRY: tuple[Tool, ...] = TOOL_REGISTRY + PAGE_OPS_TOOLS


_TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOL_REGISTRY}

# 启动校验（c-writing-agent-tier）：执行类工具必须声明 requires_feature，缺声明 fail loud。
_UNDECLARED_EXECUTE_TOOLS = [
    t.name for t in TOOL_REGISTRY if t.kind == "write" and not t.requires_feature
]
if _UNDECLARED_EXECUTE_TOOLS:  # pragma: no cover - 启动即失败
    raise RuntimeError(
        f"执行类工具缺 requires_feature 声明（应填 assistant-execute）：{_UNDECLARED_EXECUTE_TOOLS}"
    )
# 反向守护：读类/产卡类不得声明执行键（spec：读类 MUST NOT 要求）。
_NON_WRITE_WITH_EXECUTE = [
    t.name for t in TOOL_REGISTRY if t.kind != "write" and t.requires_feature
]
if _NON_WRITE_WITH_EXECUTE:  # pragma: no cover - 启动即失败
    raise RuntimeError(
        f"读类/产卡类工具不应声明 requires_feature：{_NON_WRITE_WITH_EXECUTE}"
    )


def get_tool(name: str) -> Tool | None:
    return _TOOLS_BY_NAME.get(str(name or "").strip())
