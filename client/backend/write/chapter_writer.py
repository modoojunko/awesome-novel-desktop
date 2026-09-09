"""ChapterContext builder — 素材包组装层（ai-prompt-crafting）。

两段式提示词生产的第一段：从 DB 确定性组装素材包。
- ``build_chapter_context``：读全量数据源（设定/章纲全字段含提示词格子/前情）。
- ``ChapterContext.material_markdown()``：结构化素材包（发给大模型润色的原料）。
- ``ChapterContext.to_prompt()``：粗组兜底提示词（未润色/润色失败时直接可用）。

裁剪预算（awesome-novel 量化口径）：世界观 ≤600 字、活跃伏笔 ≤8 条、角色 ≤5 人；
未填字段跳过，不产生 ``{...}`` 占位符。
"""

import re

from filesystem.storage import get_storage
from genres.service import build_genre_section, resolve_genre_context
from prompt.context import filter_active_hooks, inject_world_setting
from settings.render import (
    build_tone_section,
    depiction_techniques_str,
    flatten_principles,
    fmt_mistakes,
)

# 目标字数夹取区间（服务层守卫：越界值按默认处理）
WORD_TARGET_MIN = 500
WORD_TARGET_MAX = 6000
WORD_TARGET_DEFAULT = 2500

_WEIGHT_LABELS = {"high": "高", "mid": "中", "low": "低"}

_CH1_PREVIOUS = "无前置章节，开篇直接切入角色当下行动，禁止大段世界观背景介绍。"

# 写作铁律（每次正文生成注入，awesome-novel writer 三工序之二）
WRITING_IRON_RULES = (
    "写作铁律（最高优先执行）：\n"
    "1. 只输出正文本身——不写章节标题、不写解释说明、不写引导语"
    "（如「以下是本章正文」）、不使用任何 Markdown 标记。\n"
    "2. 提示词未写的情节、对话、角色行为不自行添加，不引入提示词未安排的新冲突事件。\n"
    "3. 未命名的次要角色用泛指（「那几个人」「另一个人」），不擅自命名。"
)


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
# 前情/场景原材料与素材包是否有对应段落强相关（无场景卡的章不能要求模型凭空产场景段），
# 故不进无条件清单，改在 validate 内按素材有无条件校验。
_POLISH_ANCHORS = ("任务指示", "红线", "质感")
_PLACEHOLDER_RE = re.compile(r"\{[^}\n]*\}")


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

    场景原材料段仅在素材包确有场景卡时才要求；爽点锚词仅在确有爽点时要求。
    """
    missing = [a for a in _POLISH_ANCHORS if a not in text]
    if (ctx.previous_context or ctx.previous_chapter_recap) and "前情" not in text:
        missing.append("前情")
    if ctx._scene_material_text() and "场景原材料" not in text:
        missing.append("场景原材料")
    if ctx.micro_payoffs and "爽点" not in text:
        missing.append("爽点设计")
    if _PLACEHOLDER_RE.search(text):
        missing.append("占位符残留")
    return missing


class ChapterContext:
    """Holds all context data needed for writing a chapter."""

    def __init__(self):
        self.premise = ""
        self.world_setting = {}
        self.style_setting = {}
        self.anti_ai = {}
        self.hooks = []
        self.volume_summary = ""
        self.chapter_outline = {}
        self.characters = []
        self.previous_chapter_recap = ""
        self.novel_title = ""
        self.genre_section = ""
        # 疲劳词：主源 writing-style.fatigue_words（6.0e 迁移）；旧契约题材行同批合并
        self.style_fatigue_words: list[str] = []
        # ── ai-prompt-crafting 素材扩展 ──────────────────────────────
        self.volume_no: int | None = None
        self.chapter_no: int | None = None
        self.word_target: int = WORD_TARGET_DEFAULT
        # 前情上下文（语义化文本，build 时生成）；空则回退 previous_chapter_recap
        self.previous_context: str = ""
        self.previous_context_semantic: bool = False
        self.scene_cards: list[dict] = []
        self.micro_payoffs: list[dict] = []
        self.ladder_exit: str = ""
        self.required_changes: list[str] = []
        self.payoff_plan: dict = {}
        self.prohibitions: list[str] = []
        self.mood_progression: str = ""
        self.emotional_hook: str = ""
        self.primary_mood: str = ""

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

        role = self.style_setting.get("role", "")
        blocks.append(f"【叙事身份】{role or '一位小说家'}")
        if self.genre_section:
            blocks.append(f"【题材】\n{self.genre_section}")
        tone = build_tone_section(self.style_setting)
        if tone:
            blocks.append(f"【文风基调】\n{tone}")
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

        if self.premise or self.world_setting or self.volume_summary:
            bg = ["故事前提：" + self.premise] if self.premise else []
            world_block = self._world_block()
            if world_block:
                bg.append(world_block)
            if self.volume_summary:
                bg.append(f"本卷概要：{self.volume_summary}")
            blocks.append("【故事背景】\n" + "\n".join(bg))

        scene = self._scene_material_text()
        if scene:
            blocks.append("【场景原材料】\n" + scene)

        if self.characters:
            lines = []
            for ch in self.characters[:5]:
                seg = f"- {ch.get('name', '?')}：{ch.get('state', '')}"
                speech = ch.get("speech", "")
                if speech:
                    seg += f"｜语言特征：{speech}"
                lines.append(seg)
            blocks.append("【角色初始状态】\n" + "\n".join(lines))

        if self.hooks:
            blocks.append(
                "【活跃伏笔】\n"
                + "\n".join(f"- {h.get('description', '?')}" for h in self.hooks[:8])
            )

        red_lines = self._red_lines()
        if red_lines:
            blocks.append(
                "【约束红线（最高优先级，任何压缩不得删改）】\n"
                + "\n".join(f"- {r}" for r in red_lines)
            )
        mistakes = fmt_mistakes(self.style_setting.get("possible_mistakes"))
        if mistakes:
            blocks.append(f"【文风常见错误】{mistakes}")
        techniques = depiction_techniques_str(self.style_setting)
        if techniques:
            blocks.append(f"【描写技法】{techniques}")
        if self.ladder_exit:
            blocks.append(f"【本章章末落点】{self.ladder_exit}")

        return "\n\n".join(blocks)

    def _few_shot_examples(self) -> list[str]:
        raw = self.style_setting.get("few_shot_examples")
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        return [str(s).strip() for s in raw if str(s).strip()][:3]

    def _world_block(self) -> str:
        block = inject_world_setting(self.world_setting)
        # 世界观裁剪预算 ≤600 字（含标签），超宽截断
        if len(block) > 600:
            block = block[:600] + "…"
        return block

    def _narrative_goals_lines(self) -> list[str]:
        goals = []
        if self.emotional_hook:
            goals.append(f"核心悬念：{self.emotional_hook}（本章解决/加深/转移）")
        if self.primary_mood:
            goals.append(f"读者情绪（离场感受）：{self.primary_mood}")
        if self.micro_payoffs:
            payoff = "；".join(
                f"{m.get('kind', '')}·{m.get('description', '')}"
                f"（{m.get('location', '')}）".strip("（）")
                for m in self.micro_payoffs
                if str(m.get("description", "")).strip()
            )
            if payoff:
                goals.append(f"爽点设计（读者获得）：{payoff}")
        return goals

    def _scene_material_text(self) -> str:
        lines = []
        for i, sc in enumerate(self.scene_cards, 1):
            parts = [f"场景{i}｜{sc.get('scene_name', '')}".rstrip("｜")]
            weight = _WEIGHT_LABELS.get(sc.get("weight", ""))
            if weight:
                parts.append(f"权重：{weight}")
            if sc.get("focus"):
                parts.append(f"焦点：{sc['focus']}")
            lines.append("｜".join(parts))
            chain = " → ".join(
                str(sc.get(k, "")).strip()
                for k in ("goal", "obstacle", "hook")
                if str(sc.get(k, "")).strip()
            )
            if chain:
                lines.append(f"  核心事件链（外部动作，非内心）：{chain}")
        if self.mood_progression:
            lines.append(f"情绪弧线：{self.mood_progression}")
        return "\n".join(lines)

    def _red_lines(self) -> list[str]:
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
        return reds

    # ── 粗组兜底提示词 ─────────────────────────────────────────────

    def to_prompt(self) -> str:
        """Assemble full writing prompt from all context data."""
        lines = []

        # Role
        role = self.style_setting.get("role", "一位小说家")
        principles = flatten_principles(self.style_setting.get("core_principles"))
        lines.append("## 角色定位")
        lines.append(f"你是{role}。{' '.join(principles)}")
        lines.append("")

        # Genre section (题材定义注入，紧跟角色定位，先于正文指引生效)
        if self.genre_section:
            lines.append(self.genre_section)
            lines.append("")

        # Tone section (ADR-007：文风基调归文风表单，题材库不再注入)
        tone_section = build_tone_section(self.style_setting)
        if tone_section:
            lines.append(tone_section)
            lines.append("")

        # Rules
        mistakes = fmt_mistakes(self.style_setting.get("possible_mistakes"))
        fatigue = self._flatten_fatigue_words(self.anti_ai.get("fatigue_words_zh", {}))
        fatigue = list(dict.fromkeys(fatigue + self.style_fatigue_words))
        tic_patterns = [
            r.get("pattern", "")
            for r in self.anti_ai.get("structural_tic_patterns", [])
        ]
        lines.append("## 原则与禁忌")
        if mistakes:
            lines.append(f"注意避免：{mistakes}")
        if fatigue:
            lines.append(f"禁止使用以下词汇：{', '.join(fatigue)}")
        if tic_patterns:
            lines.append(f"禁止以下句式：{', '.join(tic_patterns[:5])}")
        lines.append("")

        # Background
        lines.append("## 故事背景")
        lines.append(f"本段是《{self.novel_title}》的一章。")
        if self.premise:
            lines.append(f"故事前提：{self.premise}")
        world_block = self._world_block()
        if world_block:
            lines.append(world_block)
        if self.volume_summary:
            lines.append(f"本卷概要：{self.volume_summary}")
        lines.append("")

        # Chapter outline + 场景原材料
        outline = self.chapter_outline
        lines.append("## 当前章节")
        lines.append(f"章纲：{outline.get('summary', '')}")
        key_points = outline.get("key_points", [])
        if key_points:
            lines.append(f"关键情节点：{'、'.join(key_points[:5])}")
        scene = self._scene_material_text()
        if scene:
            lines.append("")
            lines.append(scene)
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

        # Character snapshots
        if self.characters:
            lines.append("## 角色状态")
            for ch in self.characters[:5]:
                seg = f"- {ch.get('name', '?')}：{ch.get('state', '')}"
                speech = ch.get("speech", "")
                if speech:
                    seg += f"（语言特征：{speech}）"
                lines.append(seg)
            lines.append("")

        # Active hooks
        if self.hooks:
            lines.append("## 活跃伏笔")
            for h in self.hooks[:8]:
                lines.append(f"- {h.get('description', '?')}")
            lines.append("")

        # 不可违反规则（红线 > 字数 > 疲劳词句式 > 文风规范）
        red_lines = self._red_lines()
        lines.append("## 不可违反规则（优先级降序）")
        if red_lines:
            lines.append("1. 约束红线（任何压缩不得删改）：")
            lines.extend(f"   - {r}" for r in red_lines)
        lines.append(f"2. 字数：约 {self.word_target} 字（±10%），超限先压缩低权重场景。")
        lines.append("3. 疲劳词与句式：见上方「原则与禁忌」。")
        lines.append("4. 文风规范：原则与描写要求为最低层，与上层冲突时让步。")
        if self.ladder_exit:
            lines.append(f"章末落点：{self.ladder_exit}")
        lines.append("")

        # Writing requirements
        techniques_str = depiction_techniques_str(self.style_setting)
        lines.append("## 写作要求")
        if techniques_str:
            lines.append(techniques_str)
        few_shot = self._few_shot_examples()
        if few_shot:
            lines.append("文风例句（参考语感）：")
            lines.extend(f"- {s}" for s in few_shot)
        lines.append("质感要求：留 1-2 个不服务主线的细碎生活细节；对话允许半截话、语气词、停顿；按场景权重分配笔墨（高权重细化、低权重简笔转场）。")
        lines.append(f"输出长度：约 {self.word_target} 字（±10% 可接受，叙事完整性优先）。")
        lines.append("语言：中文。")
        lines.append("写正文，不写章节标题，不写总结，不使用 Markdown 标记，不输出引导语。")

        return "\n".join(lines)

    def _flatten_fatigue_words(self, fatigue_dict: dict) -> list[str]:
        words = []
        for category in fatigue_dict.values():
            if isinstance(category, list):
                words.extend(category)
        return words


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
    """上章章纲情绪设计 → 语义前情文本；章纲关键字段全空 → ("", False) 由调用方回退。"""
    emotional = prev_chapter.get("emotional_design") or {}
    memo = prev_chapter.get("memo") or {}

    mood_tail = str(emotional.get("mood_progression", "")).strip()
    if mood_tail:
        # 取末段（"平静→不安→紧张" 取最后一节）
        mood_tail = mood_tail.split("->")[-1].split("→")[-1].strip()
    hook = str(emotional.get("emotional_hook", "")).strip()
    changes = [
        str(c).strip()
        for c in (memo.get("required_changes") or [])
        if str(c).strip()
    ]
    ladder_exit = str(prev_chapter.get("ladder_exit", "")).strip()
    expectation = (memo.get("reader_expectation") or {}).get("detail", "")
    expectation = str(expectation).strip()

    if not any((mood_tail, hook, changes, ladder_exit)):
        return "", False

    parts = []
    if mood_tail:
        parts.append(f"上章结尾情绪：{mood_tail}")
    if hook:
        parts.append(f"上章章末情绪钩子：{hook}")
    if changes:
        parts.append("上章必须完成的改变：" + "；".join(changes))
    if ladder_exit:
        parts.append(f"上章章末落点（本章的更高起点）：{ladder_exit}")
    if expectation:
        parts.append(f"读者期待缺口：{expectation}")
    return "\n".join(parts), True


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

    # Settings
    ctx.style_setting = (
        await get_storage().read_yaml(root_path, "settings/writing-style.yaml") or {}
    )
    ctx.world_setting = (
        await get_storage().read_yaml(root_path, "settings/world-setting.yaml") or {}
    )
    ctx.anti_ai = (
        await get_storage().read_yaml(root_path, "settings/anti-ai.yaml") or {}
    )

    # Hooks（共享过滤口径：排除本章引入 + pending/mentioned + ≤8）
    hooks_data = await get_storage().read_yaml(root_path, "settings/hooks.yaml") or {}
    ctx.hooks = filter_active_hooks(hooks_data, chapter_ref)

    # Genre（题材定义注入，定义缺失时优雅降级为空）
    # novel_id 有值时读 novel_genre 关系表（D19 新契约）；无值时回退旧 KV genre_id。
    gctx = await resolve_genre_context(root_path, novel_id)
    if gctx:
        ctx.genre_section = build_genre_section(gctx)
    # 疲劳词主源已迁 writing-style.yaml（6.0e）；旧契约题材行的疲劳词过渡期合并去重。
    ctx.style_fatigue_words = list(
        dict.fromkeys(
            [
                *(ctx.style_setting.get("fatigue_words") or []),
                *((gctx or {}).get("fatigue_words") or []),
            ]
        )
    )

    # Chapter
    from workflow.engine import load_chapter

    chapter = await load_chapter(root_path, chapter_ref) or {}
    ctx.chapter_outline = chapter.get("outline", {})
    if not isinstance(ctx.chapter_outline, dict):
        ctx.chapter_outline = {}

    # 提示词格子素材
    ctx.scene_cards = [sc for sc in chapter.get("scene_cards") or [] if isinstance(sc, dict)]
    ctx.micro_payoffs = [
        mp for mp in chapter.get("micro_payoffs") or [] if isinstance(mp, dict)
    ]
    ctx.ladder_exit = str(chapter.get("ladder_exit", "") or "").strip()
    memo = chapter.get("memo") or {}
    ctx.required_changes = [
        str(c) for c in (memo.get("required_changes") or []) if str(c).strip()
    ]
    ctx.payoff_plan = memo.get("payoff_plan") or {}
    ctx.prohibitions = [
        str(p) for p in (memo.get("prohibitions") or []) if str(p).strip()
    ]
    emotional = chapter.get("emotional_design") or {}
    ctx.mood_progression = str(emotional.get("mood_progression", "") or "").strip()
    ctx.emotional_hook = str(emotional.get("emotional_hook", "") or "").strip()
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
            ctx.volume_summary = await volume_repo.get_summary_by_root(
                session, root_path, vol_no
            )

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

    # Characters in this chapter（补语言特征 speech）
    char_names = ctx.chapter_outline.get("characters", [])
    if isinstance(char_names, list):
        for name in char_names[:5]:
            if isinstance(name, str):
                ch_data = (
                    await get_storage().read_yaml(
                        root_path, f"settings/character-setting/{name}.yaml"
                    )
                    or {}
                )
                state = ""
                state_history = ch_data.get("state_history", [])
                if isinstance(state_history, list) and state_history:
                    last = state_history[-1]
                    if isinstance(last, dict):
                        state = last.get("state", "")
                ctx.characters.append(
                    {"name": name, "state": state, "speech": ch_data.get("speech", "")}
                )

    return ctx
