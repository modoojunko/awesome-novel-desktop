"""ChapterContext builder — 素材包组装层（ai-prompt-crafting）。

两段式提示词生产的第一段：从 DB 确定性组装素材包。
- ``build_chapter_context``：读全量数据源（设定/章纲全字段含提示词格子/前情）。
- ``ChapterContext.material_markdown()``：结构化素材包（发给大模型润色的原料）。
- ``ChapterContext.build_system_prompt()``：system 恒定层（本书设定，逐章一致）。
- ``ChapterContext.to_user_material()``：章级动态素材（c-write-prompt-layering 拆层，
  原 to_prompt 整包退役——恒定块上收 system 恒定层）。

裁剪预算（awesome-novel 量化口径）：世界观 ≤600 字、活跃伏笔 ≤8 条、角色 ≤5 人；
未填字段跳过，不产生 ``{...}`` 占位符。
"""

import json
import logging
import re

from sqlalchemy import select

from db import async_session
from filesystem.storage import get_storage
from genres.service import build_genre_section, resolve_genre_context
from prompt.context import inject_world_setting
from settings.character_model import (
    WRITE_STATE_KEYS as _WRITE_STATE_KEYS,
)
from settings.character_model import (
    WRITE_STATE_PER_CELL_MAX as _WRITE_STATE_PER_CELL_MAX,
)
from settings.render import (
    quant_section,
    shadow_override_lines,
    style_section,
)
from settings.world_model import render_red_lines

logger = logging.getLogger(__name__)

# 目标字数夹取区间（服务层守卫：越界值按默认处理）
WORD_TARGET_MIN = 500
WORD_TARGET_MAX = 6000
WORD_TARGET_DEFAULT = 2500

# 主线注入预算（storyline-settings-v2 D4）：存储不截断，写章组装是唯一裁剪点
STORY_ARC_INJECT_MAX = 600


def clip_story_arc(text: str, limit: int = STORY_ARC_INJECT_MAX) -> str:
    """主线全文注入裁剪：超预算截断到句读处，避免提示词超载。"""
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    # 截到最后一个句读（句号/问叹号/分号），找不到就从尾部分词处截
    for i in range(len(cut) - 1, max(len(cut) - 80, 0), -1):
        if cut[i] in "。！？；…":
            return cut[: i + 1]
    return cut

# 读者获得类型（micro_payoffs.kind）中文标签单源（c-og-slim-v2）。
# 进提示词一律用中文标签，禁英文枚举键（`clue`/`reveal`…）——中文提示词里夹 slug
# 会让模型把它当英文关键词复读。前端镜像见 chapterForm.ts 的 PAYOFF_KINDS
# （parity 测试逐字对拍，见 tests/test_shared_constants_parity.py）。
MICRO_PAYOFF_LABELS = {
    "clue": "线索",
    "reveal": "真相揭示",
    "twist": "反转",
    "emotion": "情绪共鸣",
    "power": "实力成长",
    "relation": "关系进展",
    "relief": "压力释放",
}

_CH1_PREVIOUS = "无前置章节，开篇直接切入角色当下行动，禁止大段世界观背景介绍。"

# 写作铁律（c-write-prompt-layering）：文本迁入 prompts/write_chapter.prompt 的
# system 恒定层（「## 输出契约」段，含「本章必须完成视为已写情节」仲裁句），
# WRITING_IRON_RULES 常量随之退役——改铁律改模板，不再动代码。

# 收尾重申行（同词不同句，防被当回声）：_stream_chapter 在 user 内容最末字节
# 强制追加，不落库、不进弹窗预览，对存量稿路径与重组路径同样生效。
WRITE_CLOSING_LINE = (
    "输出：仅正文，无标题、无总结、无引导语、无 Markdown；段落之间直接换行，不留空行；"
    "结尾停在素材「章末落点」的画面/瞬间上，落点之后不写一个字。"
)


def normalize_generated_prose(text: str) -> str:
    """AI 生成产物分段归一（c-write-prompt-layering 后续修复）：段间空行收敛为
    单个换行，并去首尾换行。

    背景：prose 契约＝单换行分段，编辑器把每个空行保留为空段落（作者手写稿契约）；
    模型按 LLM 默认习惯发的段间空行会在正文里渲染成成片空段落。生成/续写出口在此
    收敛——只管 AI 产物，不碰作者手写稿（save/save_prose 不归一）。"""
    return re.sub(r"\n{2,}", "\n", text or "").strip("\n")

# 旧版整包行判定标记：粗组存稿行按恒定块标题；润色稿行按 _POLISH_ANCHORS 三锚
# 同现（凡成功落库的润色行必然满足，新 user 层不含「任务指示」「质感」两词）。
_LEGACY_HEADING_MARKERS = (
    "## 角色定位",
    "## 故事背景",
    "## 题材设定",
    "## 文风",
    "## 原则与禁忌",
)


def resolve_persona(style_setting: dict) -> str:
    """身份句单源（c-write-prompt-layering）：手填优先，空串/缺失兜底。

    get(key, default) 对「键存在但值为空串」不生效——历史「你是。」缺陷根因。
    system 恒定层与素材包（【叙事身份】）同源消费，SHALL NOT 出现两个身份表述。
    """
    return str((style_setting or {}).get("role") or "").strip() or "一位小说家"


def legacy_prompt_kind(text: str) -> str:
    """持久化 write-prompt 行的旧版整包分型（c-write-prompt-layering 分级引导）。

    - "polished"：润色三锚同现（润色产出行，可能含作者手改）→ 只做信息性提示，
      SHALL NOT 引导以未润色重组稿覆盖。先于 raw 判定——润色输入素材含【故事背景】
      【文风】块，产物可能回显「## 故事背景/## 文风」节头，若节头优先会把刚润色的
      行误判成 raw、复活「建议刷新覆盖润色稿」循环（评审 P2）；
    - "raw"：命中恒定块标题且无三锚（旧粗组整包手存稿——旧 to_prompt 不含「任务指示」
      锚，不会被误升为 polished）→ 弹窗建议「刷新提示词」；
    - ""：新分层口径的行或无法判定。
    """
    if all(a in text for a in _POLISH_ANCHORS):
        return "polished"
    if any(m in text for m in _LEGACY_HEADING_MARKERS):
        return "raw"
    return ""


def is_legacy_write_prompt(text: str) -> bool:
    """是否旧版整包行（含恒定设定内容）——legacy_prompt_kind 的布尔便捷面。"""
    return legacy_prompt_kind(text) != ""


def lint_assembled_prompt(
    required_changes: list[str], plot_items: list[str], hooks: list[dict]
) -> list[str]:
    """组装期素材病告警（c-write-prompt-layering）：不阻断生成，显式返回问题清单。

    两件：「本章必须完成」未被剧情条目覆盖（bigram 覆盖代理）、活跃伏笔混入
    已兑现（揭）记录。「爱用词∩世界观词表」无数据源，不在内（见 change Non-Goals）。
    """
    warns: list[str] = []
    if required_changes and not plot_items:
        warns.append(
            f"「本章必须完成」有 {len(required_changes)} 条但剧情条目为空，完成项缺拍点支撑"
        )
    elif required_changes and plot_items:
        plot_text = "\n".join(plot_items)
        for change in required_changes:
            grams = {
                change[i : i + 2] for i in range(len(change) - 1) if len(change) > 1
            }
            if grams and not any(g in plot_text for g in grams):
                warns.append(f"「本章必须完成」未获剧情条目覆盖：{change[:40]}")
    for h in hooks:
        desc = str(h.get("description", ""))
        if desc.startswith(("揭：", "揭:")):
            warns.append(f"活跃伏笔混入已兑现记录：{desc[:40]}")
    return warns


def clamp_word_target(value) -> int:
    """目标字数守卫：空/非法/越界 → 默认 2500；否则夹取 [500, 6000]。"""
    try:
        n = int(value) if value is not None else None
    except (TypeError, ValueError):
        n = None
    if n is None:
        return WORD_TARGET_DEFAULT
    if n < WORD_TARGET_MIN or n > WORD_TARGET_MAX:
        return WORD_TARGET_DEFAULT
    return n


# 润色产物必备锚词（模板「硬性纪律」要求保留；缺失即轻校验不合格）。
# 前情与素材包是否有对应段落强相关（无前情/无剧情条目的章不能要求模型凭空产段），
# 故不进无条件清单，改在 validate 内按素材有无条件校验。
_POLISH_ANCHORS = ("任务指示", "红线", "质感")
_PLACEHOLDER_RE = re.compile(r"\{[^}\n]*\}")

# 剧情条目块（c-plot-split）：块名＋定位句钉死（两路同源 parity 回归校对到字）。
_PLOT_BLOCK_TITLE = "【本章剧情走向（分条）】"
_PLOT_BLOCK_ANCHOR = (
    "定位：首尾以章卡（章末落点/要撞的墙）为锚，中间推进以剧情条目为主干。"
)


def _plot_block(items) -> str:
    """剧情条目块单源渲染：一条一行（单条内换行折叠为空格），空清单回空串。

    material_markdown 与 to_prompt 两路唯一渲染入口（禁再两处手写拼接）；
    空剧情时两路产物逐字不变（golden 回归钉死）。
    """
    rows = [str(it) for it in (items or []) if str(it).strip()]
    if not rows:
        return ""
    lines = [_PLOT_BLOCK_TITLE, _PLOT_BLOCK_ANCHOR]
    lines += ["- " + " ".join(str(it).splitlines()).strip() for it in rows]
    return "\n".join(lines)


# ── 故事状态块（c-chapter-dossier）──────────────────────────────────────────

_STORY_STATE_TITLE = "【故事状态（截至上章）】"
_STORY_STATE_ANCHOR = (
    "定位：以下是截至上一章结束时的既成事实，用于保持连续性，不是本章任务；"
    "与本章剧情安排冲突时以本章为准，需要打破某条状态时必须显式写出转变契机。"
)
_STORY_STATE_RULE = (
    "规则：标「（不知）」的信息，该角色在对话与行动中不得表现出知情，"
    "不得提前摊牌或泄底。"
)
_STORY_STATE_PER_DOMAIN = 6  # 每域条数配额（章近优先＝折叠序取尾）
_STORY_STATE_ITEM_MAX = 40  # 单条渲染截断
_STORY_STATE_BLOCK_MAX = 1500  # 整块硬闸（超限从头丢最旧条并 warning，不静默）


def _clip_item(text: str, n: int = _STORY_STATE_ITEM_MAX) -> str:
    s = " ".join(str(text or "").split())
    return s[:n]


def _story_state_lines(state: dict) -> dict[str, list[str]]:
    """折叠态四域 → 行字典（每域尾部取 _STORY_STATE_PER_DOMAIN 条，章近优先）。"""

    def _tail(rows):
        return list(rows or [])[-_STORY_STATE_PER_DOMAIN:]

    settings = [
        f"- {_clip_item(s.get('area')) or '设定'}：{_clip_item(s.get('content'))}"
        for s in _tail(state.get("settings"))
    ]
    relations = []
    for r in _tail(state.get("relations")):
        note = f"（{_clip_item(r.get('change_note'))}）" if r.get("change_note") else ""
        relations.append(
            f"- {r.get('owner', '?')}→{r.get('other', '?')}：{_clip_item(r.get('rel_type'))}{note}"
        )
    items = []
    for it in _tail(state.get("items")):
        if it.get("holder"):
            seg = f"- {it.get('name', '?')}：在{_clip_item(it.get('holder'), 20)}手中"
        else:
            seg = f"- {it.get('name', '?')}：{_clip_item(it.get('detail') or it.get('change_type'))}"
        items.append(seg)
    knowledge = []
    for k in _tail(state.get("knowledge")):
        fact = _clip_item(k.get("fact"))
        if k.get("learned"):
            knowledge.append(f"- {k.get('character', '?')}已得知「{fact}」")
        else:
            knowledge.append(f"- {k.get('character', '?')}仍不知道「{fact}」（{k.get('character', '?')}不知）")
    return {"设定": settings, "关系": relations, "物品": items, "角色认知": knowledge}


def _story_state_block(state: dict) -> str:
    """故事状态块单源渲染（c-chapter-dossier D5）：素材包与组装提示词两路唯一入口。

    - 输入＝story_state_upto 折叠态（只含已采纳∧已归档∧非 stale 章）；
    - 四域全空 → 空串（两路产物逐字不变）；stale 章跳过时块头注记；
    - 证据句不进消费段；每域 ≤6 条、单条 ≤40 字、整块 ≤1500 字硬闸。
    """
    groups = _story_state_lines(state or {})
    if not any(groups.values()):
        return ""
    # 整块硬闸：从最长域的头部丢最旧条直到达标（不静默）
    import logging as _logging

    def _total() -> int:
        return sum(len(x) for g in groups.values() for x in g)

    while _total() > _STORY_STATE_BLOCK_MAX:
        longest = max((k for k in groups if groups[k]), key=lambda k: len("".join(groups[k])), default=None)
        if longest is None or len(groups[longest]) <= 1:
            break
        groups[longest].pop(0)
        _logging.getLogger("uvicorn.error").warning(
            "story_state_block 超 %d 字硬闸，已丢弃最旧条目", _STORY_STATE_BLOCK_MAX
        )

    lines = [_STORY_STATE_TITLE, _STORY_STATE_ANCHOR]
    stale_refs = (state or {}).get("skipped_stale_refs") or []
    if stale_refs:
        lines.append(f"注：第 {'、'.join(str(r) for r in stale_refs[:5])} 章的章档基于旧设定，仅供参考。")
    for label, rows in groups.items():
        if rows:
            lines.append(f"◆ {label}：")
            lines.extend(rows)
    lines.append(_STORY_STATE_RULE)
    return "\n".join(lines)


def strip_code_fences(text: str) -> str:
    """剥掉模型偶尔包裹的 ```markdown 围栏（保留内部文本）。"""
    s = str(text).strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def validate_polished_prompt(text: str, ctx: "ChapterContext") -> list[str]:
    """润色产物轻校验：返回缺失的必备锚词清单（空清单 = 合格）。

    爽点锚词仅在确有爽点时要求；剧情走向段仅在 plot_items 非空时要求
    （c-plot-split 条件锚）；场景原材料锚随场景卡退役（c-og-slim-v2）。
    """
    missing = [a for a in _POLISH_ANCHORS if a not in text]
    if (ctx.previous_context or ctx.previous_chapter_recap) and "前情" not in text:
        missing.append("前情")
    if (ctx.chapter_outline or {}).get("summary") and "章纲概要" not in text:
        missing.append("章纲概要")
    if ctx.micro_payoffs and "爽点" not in text:
        missing.append("爽点设计")
    if ctx.plot_items and "剧情走向" not in text:
        missing.append("剧情走向")
    # c-chapter-dossier：有故事状态时润色产物须保留段标题（与「前情」锚同手法）
    if _story_state_block(ctx.story_state) and "故事状态" not in text:
        missing.append("故事状态")
    if _PLACEHOLDER_RE.search(text):
        missing.append("占位符残留")
    return missing


class ChapterContext:
    """Holds all context data needed for writing a chapter."""

    def __init__(self):
        self.premise = ""
        # 主线（story_arc.fullstory＝从头到尾的全景，legacy premise 在归一里升位）：整本书
        # 怎么走的唯一归属；注入前经 clip_story_arc 裁剪（≤600 字）。
        # 2026-09-10 起题材面板不再有「剧情轨道」（与主线重复），注入改由这里承接。
        self.story_arc = ""
        self.world_setting = {}
        self.style_setting = {}
        self.style_quant = {}
        # 本章文风影子（chapter-style-shadow）：命中行覆盖基线渲染；直建 ctx 默认空
        self.style_shadow: dict = {}
        self.hooks = []
        # 全书角色静态档案锚（c-write-prompt-layering）：system 恒定层用，
        # 不按单章出场名单过滤——出场与否由 user 层角色状态行表达
        self.cast_items: list[dict] = []
        # 组装期素材病告警（lint_assembled_prompt）：显式透出，不阻断
        self.lint_warnings: list[str] = []
        self.volume_outline = ""
        self.chapter_outline = {}
        self.characters = []
        self.previous_chapter_recap = ""
        self.novel_title = ""
        self.genre_section = ""
        # ── ai-prompt-crafting 素材扩展 ──────────────────────────────
        self.volume_no: int | None = None
        self.chapter_no: int | None = None
        self.word_target: int = WORD_TARGET_DEFAULT
        # 前情上下文（语义化文本，build 时生成）；空则回退 previous_chapter_recap
        self.previous_context: str = ""
        self.previous_context_semantic: bool = False
        self.micro_payoffs: list[dict] = []
        self.ladder_exit: str = ""
        # c-chapter-plan-ai：拆章两格（挑战/阶段）——写正文素材消费
        # （c-og-slim-v2：「本章行动」退役）
        self.challenge: str = ""
        self.plot_stage: str = ""
        # c-plot-split：本章剧情条目（场景描述清单，非正文）——素材包【本章剧情走向（分条）】原料
        self.plot_items: list[str] = []
        # 开篇期位置标注（首章/开篇期，其余空）——与剧情抽卡【本章位置】同词同单源，
        # 驱动 system 恒定层「## 开篇期节奏」的分档
        self.chapter_position: str = ""
        self.required_changes: list[str] = []
        self.payoff_plan: dict = {}
        self.prohibitions: list[str] = []
        # c-og-slim-v2：mood_progression / emotional_hook 退役（页面无控件、语义并入
        # 主情绪与章末落点）——不再取数、不再注入。
        self.primary_mood: str = ""
        # c-chapter-dossier：故事状态（截至上章）——章档已采纳行的折叠态
        # （story_state_upto 产出）；空 dict 时素材包/提示词两路均不出块。
        self.story_state: dict = {}

    # ── 素材包（润色原料）───────────────────────────────────────────

    def material_markdown(self) -> str:
        """结构化素材包：全部数据源按标签罗列，供大模型润色成成品提示词。"""
        blocks: list[str] = []
        title = f"《{self.novel_title}》素材包" if self.novel_title else "小说素材包"
        vol_ch = "、".join(
            f"{label} {no}"
            for label, no in (("卷", self.volume_no), ("章", self.chapter_no))
            if no is not None
        )
        blocks.append(f"# {title}" + (f"（{vol_ch}）" if vol_ch else ""))

        role = resolve_persona(self.style_setting)
        blocks.append(f"【叙事身份】{role}")
        if self.genre_section:
            blocks.append(f"【题材】\n{self.genre_section}")
        style_sec = style_section(self.style_setting)
        if style_sec:
            blocks.append(f"【文风】\n{style_sec}")
        quant = quant_section(self.style_quant, self.style_shadow)
        if quant:
            blocks.append(quant)
        few_shot = self._few_shot_examples()
        if few_shot:
            blocks.append("【文风例句（案例段原料）】\n" + "\n".join(f"- {s}" for s in few_shot))

        task_lines = [
            f"目标字数：约 {self.word_target} 字（±10% 可接受，叙事完整性优先）",
            "压缩策略：超字数时优先压缩低权重场景（≤100 字转场），不得删改红线内容",
        ]
        goals = self._narrative_goals_lines()
        if goals:
            task_lines.append("叙事目标：\n" + "\n".join(f"- {g}" for g in goals))
        blocks.append("【任务指示】\n" + "\n".join(task_lines))

        prev = self.previous_context or self.previous_chapter_recap
        if prev:
            blocks.append(f"【前情上下文】\n{prev}")

        if self.premise or self.world_setting or self.volume_outline:
            bg = ["故事前提：" + self.premise] if self.premise else []
            if self.story_arc:
                bg.append("全书主线：" + self.story_arc)
            world_block = self._world_block()
            if world_block:
                bg.append(world_block)
            if self.volume_outline:
                bg.append("本卷卷纲：\n" + self.volume_outline)
            blocks.append("【故事背景】\n" + "\n".join(bg))

        # 章纲概要块（c-og-slim-v2）：删格批次之前此处缺失，润色产物（直接用于生成正文）
        # 因此丢掉章纲主干。挑战/阶段两块在下方既有（非空时才出），此处只补概要。
        if self.chapter_outline.get("summary"):
            blocks.append(f"【章纲概要】{self.chapter_outline['summary']}")

        # c-plot-split：剧情条目块（单源渲染）
        plot = _plot_block(self.plot_items)
        if plot:
            blocks.append(plot)

        # c-chapter-dossier：故事状态块（单源渲染；剧情块后、角色块前）
        story = _story_state_block(self.story_state)
        if story:
            blocks.append(story)

        if self.characters:
            lines = []
            for ch in self.characters:
                seg = f"- {ch.get('name', '?')}：{ch.get('state', '')}"
                speech = ch.get("speech", "")
                if speech:
                    seg += f"｜语言特征：{speech}"
                lines.append(seg)
            blocks.append("【角色初始状态】\n" + "\n".join(lines))

        if self.hooks:
            # 展示编号 + 优先级（高/中/低）随注入（foreshadow-settings-v2）；
            # 无编号的 dict 桩（测试/旧形）降级为纯描述行
            lines = []
            for h in self.hooks[:8]:
                desc = h.get("description", "?")
                code = h.get("code") or ""
                prefix = f"[{code}] " if code else ""
                label = h.get("priority_label") or ""
                lines.append(
                    f"- {prefix}{desc}" + (f"（优先级：{label}）" if label else "")
                )
            blocks.append("【活跃伏笔】\n" + "\n".join(lines))

        red_lines = self._red_lines()
        if red_lines:
            blocks.append(
                "【约束红线（最高优先级，任何压缩不得删改）】\n"
                + "\n".join(f"- {r}" for r in red_lines)
            )
        if self.ladder_exit:
            blocks.append(f"【本章章末落点】{self.ladder_exit}")
        # c-chapter-plan-ai：拆章五段另三块进素材（填了就要被读到，否则拆章白拆）
        if self.challenge:
            blocks.append(f"【本章要撞的墙】{self.challenge}")
        if self.plot_stage:
            blocks.append(f"【本章在卷剧情里的位置】{self.plot_stage}")

        return "\n\n".join(blocks)

    def _few_shot_examples(self) -> list[str]:
        raw = self.style_setting.get("few_shot_examples")
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        return [str(s).strip() for s in raw if str(s).strip()][:3]

    def _world_block(self) -> str:
        # 预算由领域渲染器内部按「整条为单元 + 显式从略」控制（world-setting-v2 D5），
        # 不再从中间硬切——被切半截的红线比没有更糟；铁律走 _red_lines 红线区。
        return inject_world_setting(self.world_setting)

    def _narrative_goals_lines(self) -> list[str]:
        goals = []
        if self.primary_mood:
            goals.append(f"读者情绪（离场感受）：{self.primary_mood}")
        if self.micro_payoffs:
            parts = []
            for m in self.micro_payoffs:
                desc = str(m.get("description", "")).strip()
                if not desc:
                    continue
                label = MICRO_PAYOFF_LABELS.get(str(m.get("kind", "")).strip(), "")
                parts.append(f"{label}·{desc}" if label else desc)
            if parts:
                goals.append("爽点设计（读者获得）：" + "；".join(parts))
        return goals

    def _red_lines(self, include_world: bool = True) -> list[str]:
        """章级红线＋（可选）世界铁律。c-write-prompt-layering：世界铁律上收
        system 恒定层后，to_user_material 传 include_world=False 只取章级；
        material_markdown（润色素材包）维持原全量口径不变。"""
        reds: list[str] = []
        if self.required_changes:
            reds.extend(f"本章必须完成：{c}" for c in self.required_changes)
        for kind, label in (
            ("must_resolve", "本章必须兑现"),
            ("must_hold", "本章必须维持（不揭底）"),
        ):
            items = self.payoff_plan.get(kind) or []
            reds.extend(f"{label}：{h}" for h in items)
        reds.extend(f"禁止：{p}" for p in self.prohibitions)
        if include_world:
            # 世界铁律（world-setting-v2）：逐条完整进红线区，任何压缩不得删改
            reds.extend(render_red_lines(self.world_setting))
        return reds

    # ── 分层组装（c-write-prompt-layering）────────────────────────

    def build_system_prompt(self) -> str:
        """写正文 system 恒定层：由本书设定组装，逐章字节一致（缓存生命线）。

        恒定承诺的失效源只有设定变更/换卷/新增角色；章级差异（出场状态、文风影子、
        前情）一律经 to_user_material 传递。空段整节跳过——恒定层不出空节；
        世界观走全量通道（势力/历史/细节不裁剪、无「另有 N 条从略」）；
        文风影子 SHALL NOT 进本层（user 层覆盖块承接）。
        """
        from prompt.context import cast_profile_block, render_template
        from prompts import load_layers
        from settings.world_model import render_world_block

        system_tpl, _ = load_layers("write_chapter")

        style_rows: list[str] = []
        style_sec = style_section(self.style_setting)
        if style_sec:
            style_rows.append(style_sec)
        # 量化基线不带影子（影子命中行走 user 层覆盖块，见 to_user_material）
        quant = quant_section(self.style_quant)
        if quant:
            style_rows.append(quant)
        few_shot = self._few_shot_examples()
        if few_shot:
            style_rows.append(
                "文风例句（参考语感）：\n" + "\n".join(f"- {s}" for s in few_shot)
            )
        banned = [str(w) for w in (self.style_setting.get("banned_words") or [])]
        tic_patterns = [
            r.get("pattern", "")
            for r in (self.style_setting.get("tic_patterns") or [])
            if isinstance(r, dict)
        ]
        if banned:
            style_rows.append(f"禁止使用以下词汇：{', '.join(banned)}")
        if tic_patterns:
            style_rows.append(f"禁止以下句式：{', '.join(tic_patterns[:5])}")

        premise_rows = [f"本段是《{self.novel_title}》的一章。"]
        if self.premise:
            premise_rows.append(f"故事前提：{self.premise}")
        if self.story_arc:
            premise_rows.append(f"全书主线：{self.story_arc}")

        iron_rules = "\n".join(f"- {r}" for r in render_red_lines(self.world_setting))

        values = {
            "persona": resolve_persona(self.style_setting),
            "craft_rules": (
                "质感要求：留 1-2 个不服务主线的细碎生活细节；对话允许半截话、"
                "语气词、停顿；按场景权重分配笔墨（高权重细化、低权重简笔转场）。"
            ),
            "premise_story": "\n".join(premise_rows),
            "genre_section": self.genre_section,
            "style_block": "\n".join(style_rows),
            "world_block": render_world_block(self.world_setting, None),
            "iron_rules": iron_rules,
            "volume_outline": self.volume_outline,
            "cast_anchors": (
                cast_profile_block(self.cast_items) if self.cast_items else ""
            ),
        }

        # 逐节渲染：节体为空 → 连节头整节跳过（恒定层不出空节）；
        # 占位符填充用顺序 replace（render_template），SHALL NOT str.format——
        # 素材/设定文本含 `{}` 时 format 会崩。
        # 首块无 ## 节头（身份句先行——load_layers 会把开头连续 ## 行当注释剥掉），
        # 整块渲染保留。
        out: list[str] = []
        for chunk in re.split(r"(?m)^(?=## )", system_tpl):
            if not chunk.strip():
                continue
            if not chunk.startswith("## "):
                rendered = render_template(chunk, **values).strip("\n")
                if rendered.strip():
                    out.append(rendered.rstrip())
                continue
            header, _, body = chunk.partition("\n")
            body = render_template(body, **values).strip("\n")
            if body.strip():
                out.append(f"{header}\n{body}".rstrip())
        return "\n\n".join(out)

    def to_user_material(self) -> str:
        """章级动态素材（c-write-prompt-layering）：恒定内容已上 system 恒定层，
        这里只组装随章变化的部分。节标题维持 ## 风格（润色锚词与 legacy 判定
        吃文本形状）。顺序按「稳定在前、易变在后」。"""
        lines: list[str] = []

        outline = self.chapter_outline
        lines.append("## 当前章节")
        lines.append(f"章纲：{outline.get('summary', '')}")
        # 拆章两格（c-og-slim-v2 补齐）：此前只有素材包含这两块，未润色直写会丢拆章成果
        if self.challenge:
            lines.append(f"本章要撞的墙：{self.challenge}")
        if self.plot_stage:
            lines.append(f"本章在卷剧情里的位置：{self.plot_stage}")
        # 开篇期位置标注（首章/开篇期）：驱动 system「## 开篇期节奏」的分档
        if self.chapter_position:
            lines.append(f"本章位置：{self.chapter_position}")
        # c-plot-split：剧情条目块（与 material_markdown 同源同字）
        plot = _plot_block(self.plot_items)
        if plot:
            lines.append("")
            lines.append(plot)
        if self.ladder_exit:
            lines.append(f"章末落点：{self.ladder_exit}")
        goals = self._narrative_goals_lines()
        if goals:
            lines.append("")
            lines.append("叙事目标：")
            lines.extend(f"- {g}" for g in goals)
        lines.append("")

        # Previous chapter recap / 语义前情
        prev = self.previous_context or self.previous_chapter_recap
        if prev:
            lines.append("## 前文回顾")
            lines.append(prev)
            lines.append("")

        # c-chapter-dossier：故事状态块（与素材包同源同字；角色状态前）
        story = _story_state_block(self.story_state)
        if story:
            lines.append(story)
            lines.append("")

        # Character snapshots
        if self.characters:
            lines.append("## 角色状态")
            for ch in self.characters:
                seg = f"- {ch.get('name', '?')}：{ch.get('state', '')}"
                speech = ch.get("speech", "")
                if speech:
                    seg += f"（语言特征：{speech}）"
                lines.append(seg)
            lines.append("")

        # 章级文风影子覆盖块（chapter-style-shadow）：基线恒定层不动，命中行在此
        # 覆盖并声明优先级；无影子章整块缺省，system 逐章一致不受影响。
        shadow_hits = shadow_override_lines(self.style_quant, self.style_shadow)
        if shadow_hits:
            lines.append("## 本章文风覆盖")
            lines.append("以下维度以本章值为准，覆盖指令恒定层中的文风基线：")
            lines.extend(shadow_hits)
            lines.append("")

        # Active hooks（[编号]＋优先级前缀，与素材包渲染器同口径）
        if self.hooks:
            lines.append("## 活跃伏笔")
            for h in self.hooks[:8]:
                code = h.get("code") or ""
                prefix = f"[{code}] " if code else ""
                label = h.get("priority_label") or ""
                lines.append(
                    f"- {prefix}{h.get('description', '?')}"
                    + (f"（优先级：{label}）" if label else "")
                )
            lines.append("")

        # 章级红线（世界铁律已上收 system 恒定层；本段只留随章变化的承诺）
        lines.append("## 章级红线（优先于字数与写法；世界铁律见指令恒定层）")
        red_lines = self._red_lines(include_world=False)
        if red_lines:
            lines.extend(f"- {r}" for r in red_lines)
        lines.append(f"字数：约 {self.word_target} 字（±10%），超限先压缩低权重场景。")

        return "\n".join(lines)


# ── 前情上下文（语义化）──────────────────────────────────────────────


async def _prev_chapter_ref(root_path: str, vol_no: int, ch_no: int) -> str | None:
    """按 (卷号, 章号) 找上一章：本卷更小章号，否则上一卷末章。"""
    from sqlalchemy import or_, select

    from db import async_session
    from models.chapter import Chapter
    from models.project import Novel
    from models.volume import Volume

    cond = or_(
        Volume.volume_no < vol_no,
        (Volume.volume_no == vol_no) & (Chapter.chapter_no < ch_no),
    )
    stmt = (
        select(Chapter.ref)
        .join(Volume, Volume.id == Chapter.volume_id)
        .join(Novel, Novel.id == Chapter.project_id)
        .where(Novel.root_path == root_path, cond)
        .order_by(Volume.volume_no.desc(), Chapter.chapter_no.desc())
        .limit(1)
    )
    async with async_session() as session:
        return await session.scalar(stmt)


def build_previous_context(prev_chapter: dict) -> tuple[str, bool]:
    """上章章纲留存字段 → 语义前情文本；全空 → ("", False) 由调用方回退。

    c-og-slim-v2 换源：原来源「情绪设计（mood_progression 末段 / emotional_hook）＋
    读者期待缺口」随字段退役，改为**上章概要 ＋ required_changes ＋ ladder_exit**——
    这三项是作者可编辑、且拆章会写入的字段；被删的两项在页面上本就没有控件。
    """
    outline = prev_chapter.get("outline") or {}
    memo = prev_chapter.get("memo") or {}

    summary = str(outline.get("summary", "")).strip()
    changes = [
        str(c).strip()
        for c in (memo.get("required_changes") or [])
        if str(c).strip()
    ]
    ladder_exit = str(prev_chapter.get("ladder_exit", "")).strip()

    if not any((summary, changes, ladder_exit)):
        return "", False

    parts = []
    if summary:
        parts.append(f"上章写的是：{summary}")
    if changes:
        parts.append("上章必须完成的改变：" + "；".join(changes))
    if ladder_exit:
        parts.append(f"上章章末落点（本章的更高起点）：{ladder_exit}")
    return "\n".join(parts), True




async def _novel_id_by_root(root_path: str) -> str | None:
    from models.project import Novel

    async with async_session() as session:
        row = (
            await session.scalars(
                select(Novel).where(Novel.root_path == root_path)
            )
        ).first()
        return row.id if row else None


async def _resolve_character_row(session, novel_id: str, name: str):
    from models.character import Character

    cards = (
        await session.scalars(
            select(Character).where(Character.novel_id == novel_id)
        )
    ).all()
    for c in cards:
        if c.name == name:
            return c
    for c in cards:
        try:
            if name in json.loads(c.aliases or "[]"):
                return c
        except (TypeError, ValueError):
            continue
    return None


async def build_chapter_context(
    root_path: str,
    chapter_ref: str,
    novel_title: str = "",
    novel_id: str | None = None,
) -> ChapterContext:
    """Read all data sources and build a ChapterContext."""
    ctx = ChapterContext()
    ctx.novel_title = novel_title

    # Premise
    story = await get_storage().read_yaml(root_path, "story.yaml") or {}
    ctx.premise = story.get("synopsis", "")
    arc = story.get("story_arc") if isinstance(story.get("story_arc"), dict) else {}
    # storyline-settings-v2：fullstory 全景（legacy premise 归一），组装层唯一裁剪点
    from novels.router import _arc_normalize

    ctx.story_arc = clip_story_arc(_arc_normalize(arc)["fullstory"])

    # Settings（banned-words-into-style：统一迁移感知读路径，禁用词/句式随 style_setting 单源）
    from settings.style_model import read_style_migrated

    ctx.style_setting = await read_style_migrated(root_path)
    from filesystem.paths import STYLE_QUANT_PATH

    ctx.style_quant = await get_storage().read_yaml(root_path, STYLE_QUANT_PATH) or {}
    ctx.world_setting = (
        await get_storage().read_yaml(root_path, "settings/world-setting.yaml") or {}
    )

    # Hooks（真表 novel_hooks：status==active + 本章引入按章 id 排除 + ≤8）
    from prompt.context import active_hooks_for_chapter

    ctx.hooks = await active_hooks_for_chapter(root_path, chapter_ref, novel_id)

    # Genre（题材定义注入，定义缺失时优雅降级为空）
    # novel_id 有值时读 novel_genre 关系表（D19 新契约）；无值时回退旧 KV genre_id。
    gctx = await resolve_genre_context(root_path, novel_id)
    if gctx:
        ctx.genre_section = build_genre_section(gctx)

    # Chapter
    from workflow.engine import load_chapter

    chapter = await load_chapter(root_path, chapter_ref) or {}
    # 本章文风影子（chapter-style-shadow）：章 YAML 的 style_shadow（回退/支线同款直出）
    ctx.style_shadow = chapter.get("style_shadow") or {}
    if not isinstance(ctx.style_shadow, dict):
        ctx.style_shadow = {}
    ctx.chapter_outline = chapter.get("outline", {})
    if not isinstance(ctx.chapter_outline, dict):
        ctx.chapter_outline = {}

    # 提示词格子素材
    ctx.micro_payoffs = [
        mp for mp in chapter.get("micro_payoffs") or [] if isinstance(mp, dict)
    ]
    ctx.ladder_exit = str(chapter.get("ladder_exit", "") or "").strip()
    ctx.challenge = str(chapter.get("challenge", "") or "").strip()
    ctx.plot_stage = str(chapter.get("plot_stage", "") or "").strip()
    # c-plot-split：剧情条目（assemble_chapter 恒带键；空/损坏按 [] 不阻塞）
    ctx.plot_items = [
        str(x) for x in (chapter.get("plot_items") or []) if str(x).strip()
    ]
    memo = chapter.get("memo") or {}
    ctx.required_changes = [
        str(c) for c in (memo.get("required_changes") or []) if str(c).strip()
    ]
    ctx.payoff_plan = memo.get("payoff_plan") or {}
    ctx.prohibitions = [
        str(p) for p in (memo.get("prohibitions") or []) if str(p).strip()
    ]
    emotional = chapter.get("emotional_design") or {}
    ctx.primary_mood = str(emotional.get("primary_mood", "") or "").strip()

    # 字数目标（夹取守卫；章纲未填走默认）
    ctx.word_target = clamp_word_target(chapter.get("word_target"))

    vol_match = re.match(r"vol-(\d+)", chapter_ref)
    ch_num = chapter.get("chapter", 0)
    ctx.chapter_no = ch_num if isinstance(ch_num, int) else None

    if vol_match:
        from db import async_session
        from repositories import volume_repo

        vol_no = int(vol_match.group(1))
        ctx.volume_no = vol_no
        async with async_session() as session:
            ctx.volume_outline = await volume_repo.get_outline_by_root(
                session, root_path, vol_no
            )
            # 开篇期位置标注：与剧情抽卡同一单源（chapter_position_tags），
            # 拿不到 project（novel_id 空）降级为无标注
            if novel_id and isinstance(ch_num, int) and ch_num >= 1:
                from chapters.ai_plan import global_chapter_position, position_label

                global_ch, tags = await global_chapter_position(
                    session, novel_id, vol_no, ch_num
                )
                ctx.chapter_position = position_label(global_ch, tags)

        # 前情上下文升级：上章章纲情绪设计优先，无章纲回退上章正文末段
        prev_ref = await _prev_chapter_ref(
            root_path, vol_no, ch_num if isinstance(ch_num, int) else 1
        )
        if prev_ref:
            prev = await load_chapter(root_path, prev_ref) or {}
            semantic_text, is_semantic = build_previous_context(prev)
            if is_semantic:
                ctx.previous_context = semantic_text
                ctx.previous_context_semantic = True
            else:
                prev_prose = prev.get("prose", "")
                if prev_prose:
                    ctx.previous_chapter_recap = prev_prose[-500:]
        else:
            # 无上一章（开篇）：固定句，禁大段背景介绍
            ctx.previous_context = _CH1_PREVIOUS
            ctx.previous_context_semantic = True

    # Characters in this chapter（character-settings-v2：按 id 读真表；
    # 状态 = 认知层主格摘要 + 语言特征——旧 state_history 链路已随台账移除退役）
    if not novel_id:
        novel_id = await _novel_id_by_root(root_path)

    # 故事状态（c-chapter-dossier）：截至本章（不含）的章档已采纳折叠态——
    # 只取 主线∧archived∧非 stale 章；四域全空时 ctx.story_state 留空不出块。
    try:
        from write.story_state import story_state_upto

        ctx.story_state = await story_state_upto(novel_id, chapter_ref, exclusive=True)
    except Exception as e:  # noqa: BLE001 — 状态块缺席不阻塞写章主流程
        logger.warning("story_state_upto failed: novel=%s ref=%s err=%s", novel_id, chapter_ref, e)
        ctx.story_state = {}

    char_names = ctx.chapter_outline.get("characters", [])
    if isinstance(char_names, list) and char_names:
        async with async_session() as session:
            for name in char_names:
                if not isinstance(name, str):
                    continue
                ch_row = await _resolve_character_row(session, novel_id, name)
                if ch_row is None:
                    # 显式告警：不注入空条目（旧行为渲染 "- 名字："），不静默跳过
                    ctx.characters.append(
                        {"name": name, "state": "", "speech": "", "missing": True}
                    )
                    logger.warning(
                        "chapter character not found: novel=%s name=%s", novel_id, name
                    )
                    continue
                cog = json.loads(ch_row.cog or "{}")
                dossier = json.loads(ch_row.dossier or "{}")
                # c-ai-material-audit：逐格 40 字封顶（旧实现整串切 120——首格写长一点
                # 就把后五层整段挤掉，人物行为/决策层直接消失）
                parts = [
                    str(cog.get(k, "") or "").strip()[:_WRITE_STATE_PER_CELL_MAX]
                    for k in _WRITE_STATE_KEYS
                ]
                parts = [p for p in parts if p]
                state = "；".join(parts) if parts else ""
                ctx.characters.append(
                    {
                        "name": ch_row.name or name,
                        "state": state,
                        "speech": dossier.get("speech", ""),
                        "missing": False,
                    }
                )

    # 全书角色静态档案锚（c-write-prompt-layering）：system 恒定层用，全书角色集，
    # 不按本章出场名单过滤——第 2 章新增角色只让 system 变化一次，此后恒定。
    if novel_id:
        try:
            from settings.character_service import list_characters

            async with async_session() as session:
                roster = await list_characters(session, novel_id)
            items = list(roster.get("items", []))
            items.sort(key=lambda it: 0 if it.get("role") == "主角" else 1)
            ctx.cast_items = items
        except Exception:  # noqa: BLE001 — 档案锚缺取不阻塞正文组装
            logger.warning(
                "cast anchor fetch failed: novel=%s", novel_id, exc_info=True
            )
            ctx.cast_items = []

    # 组装期素材病告警（c-write-prompt-layering）：显式透出不阻断
    ctx.lint_warnings = lint_assembled_prompt(
        ctx.required_changes, ctx.plot_items, ctx.hooks
    )
    for warn in ctx.lint_warnings:
        logger.warning("assembled prompt lint: %s", warn)

    return ctx
