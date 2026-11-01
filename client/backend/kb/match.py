"""写法块选择器（c-kb-write-block 批A）——章纲信号 → 知识条目确定性挑选。

P0 规则匹配器（不调用模型；确定性＝重试字节一致的前提）。
- 信号抽取住 write/write_block.py（章纲语义归 write 域，kb 不认识章纲表——
  2026-11-02 四角色评审 F8）；本模块收 MatchSignals 做确定性挑选。
- 候选短名单：kb_entry_tags 两段式（concept/genre/scope/slot 维度），≤200 稳定
  排序；SHALL NOT 对 payload_json 全表扫描（§12 铁律）。
- 打分＝匹配度×有用率×新鲜度；有用率读 kb_prefs（账号级，未标记=1.0）；
  新鲜度 30 天半衰。配额：手法 ≤6、场景定性写法 ≤4；粗估超 2K tokens 按分截断。
- 零命中返回 None（调用方整块不拼）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.kb import KbEntry, KbEntryTag, KbPref

# 拆章六档 plot_stage → 章位封闭值（CHAPTER_POS）；空/未知 → ""（不硬猜）
_STAGE_TO_POS = {
    "开局铺垫": "开头",
    "冲突初现": "中段",
    "矛盾升级": "中段",
    "重要转折": "中段",
    "高潮爆发": "中段",
    "卷末收束": "卷末",
}

# 短名单/配额常量
_SHORTLIST_MAX = 200
_TECH_MAX = 6          # 手法条目配额
_SCENE_STYLE_MAX = 4   # 场景定性写法（文风/文笔）配额
_BUDGET_CHARS = 3200   # ≤2K tokens 的中文字符粗估上限

# 文风 slot 白名单：进块的定性槽位（role/pov 书级恒定，走快照不进块）
_STYLE_SLOTS_IN_BLOCK = ("tone", "register", "sample")
# 文笔 slot 全部定性（rule/craft/banned_word/tic）
_CRAFT_SLOTS = ("rule", "craft", "banned_word", "tic")

# 条目字数→token 粗估系数（中文≈1 字 0.6 token，留标签余量取 0.65）
_TOKEN_PER_CHAR = 0.65

# ── 量化维度判据（c-kb-write-block C1）────────────────────────
# 量化条目（句长≤12字 类）SHALL 经章级文风影子渲染，SHALL NOT 进写法块另立数值声明。
import re as _re

_QUANT_VALUE = _re.compile(r"\d+\s*(字|句|段|行|%|％|比)|\d+[:：]\d+")
_QUANT_DIM_RULES: tuple[tuple[str, str], ...] = (
    # (BASELINE_ROWS 键, 词眼)——按命中定影子维度；映射不上→None（不排除，照常进块）
    ("syntax", "句长|句子|段落|分段|每段"),
    ("rhythm", "篇幅|字数|节奏|长短"),
    ("lexicon", "修饰|词频|形容词|比喻密度|成语"),
    ("dialogue_verb", "对话|动词|对白"),
    ("emotion", "情绪|内心|心理描写"),
    ("narrative", "镜头|人称|视角|叙述"),
)


def is_quantitative(entry) -> str | None:
    """量化条目判定：值形态（数字+单位/比例）命中且维度词可映射 → 影子维度键；
    否则 None（定性条目照常进写法块）。"""
    text = entry.instruction or ""
    if not _QUANT_VALUE.search(text):
        return None
    for key, pat in _QUANT_DIM_RULES:
        if _re.search(pat, text):
            return key
    return None


@dataclass
class MatchSignals:
    """一章的选块信号（全部确定性可复算）。"""

    scene: str = ""
    emotion: str = ""
    chapter_pos: str = ""
    characters: list[str] = field(default_factory=list)
    genre: str = ""

    def brief(self) -> dict:
        return {
            "scene": self.scene,
            "emotion": self.emotion,
            "chapter_pos": self.chapter_pos,
            "characters": self.characters,
            "genre": self.genre,
        }


@dataclass
class SelectedItem:
    entry: KbEntry
    score: float
    reason: str
    text_override: str = ""  # run 快照文本（重试字节一致——条目编辑后仍用固化文本）


@dataclass
class Selection:
    """选块结果；run 由调用方（批B 注入器）落库后回填。"""

    signals: MatchSignals
    items: list[SelectedItem]
    run: object | None = None

    @property
    def total_chars(self) -> int:
        return sum(len(i.entry.instruction or "") for i in self.items)


# ── 信号抽取（A1/A2）──────────────────────────────────────────


# ── 候选短名单（A3）──────────────────────────────────────────


async def digest_candidates(
    db: AsyncSession, *, user_id: str, genre: str,
    concepts: tuple[str, ...] = ("手法", "文风", "文笔"),
) -> dict[str, set[str]]:
    """候选短名单（公开：P1 LLM 选择器的候选摘要以本集合为域）。"""
    """kb_entry_tags 两段式：出 (手法 id 集, 场景定性文风/文笔 id 集)。

    不碰 payload_json——条目是否场景条目（scope=scene）与槽位（slot）全是物化维度。
    手法 base＋scene 全进；文风/文笔只取场景条目（基线走快照），且排除
    slot=role/pov（书级恒定槽）。
    """
    rows = (
        await db.execute(
            select(KbEntryTag.entry_id, KbEntryTag.dim, KbEntryTag.value)
            .select_from(KbEntryTag)
            .join(KbEntry, KbEntry.id == KbEntryTag.entry_id)
            .where(
                KbEntryTag.user_id == user_id,
                KbEntryTag.dim.in_(("concept", "scope", "slot")),
                KbEntry.status == "active",
                KbEntry.genre.in_((genre, "")) if genre else True,
            )
        )
    ).all()
    concept: dict[str, str] = {}
    scope: dict[str, str] = {}
    slot: dict[str, str] = {}
    for entry_id, dim, value in rows:
        if dim == "concept":
            if value in concepts:
                concept[entry_id] = value
        elif dim == "scope":
            scope[entry_id] = value
        elif dim == "slot":
            slot[entry_id] = value
    tech: set[str] = set()
    style: set[str] = set()
    for entry_id, cname in concept.items():
        if cname == "手法":
            tech.add(entry_id)
        elif cname in ("文风", "文笔") and scope.get(entry_id) == "scene":
            s = slot.get(entry_id, "")
            if cname == "文笔" or s in _STYLE_SLOTS_IN_BLOCK:
                style.add(entry_id)
    # 稳定排序截断（id 序）——短名单超 200 时保序取前
    return {
        "tech": set(sorted(tech)[:_SHORTLIST_MAX]),
        "style": set(sorted(style)[:_SHORTLIST_MAX]),
    }


# ── 打分与配额（A4）──────────────────────────────────────────


def _when_of(entry: KbEntry) -> dict:
    try:
        w = json.loads(entry.when_json or "{}")
    except ValueError:
        return {}
    return w if isinstance(w, dict) else {}


def _match_score(entry: KbEntry, signals: MatchSignals) -> tuple[float, str]:
    """匹配度∈[0,1]＋命中理由。适用条件＝when_json（payload.scene 是记录字段
    不参与匹配——§7.1「匹配＝when_json∪实体命中」口径）。手法无 when 给基础分。"""
    hits: list[str] = []
    m = 0.0
    w = _when_of(entry)
    if entry.concept == "手法":
        conds = {w["scene"]} if w.get("scene") else set()
        emo_conds = {w["emotion"]} if w.get("emotion") else set()
        pos_conds = {w["chapter_pos"]} if w.get("chapter_pos") else set()
        if not any((conds, emo_conds, pos_conds)):
            m, hits = 0.5, ("全章适用",)
        else:
            per = []
            if signals.scene and signals.scene in conds:
                per.append(f"场面:{signals.scene}")
            if signals.emotion and signals.emotion in emo_conds:
                per.append(f"情绪:{signals.emotion}")
            if signals.chapter_pos and signals.chapter_pos in pos_conds:
                per.append(f"章位:{signals.chapter_pos}")
            if per:
                m = min(1.0, 0.4 + 0.3 * len(per))
                hits = per
            else:
                m = 0.0  # 条件不命中且无实体命中＝不选（命中∪实体并集口径）
    else:
        # 文风/文笔场景条目：scope=scene 已在短名单保证；命中＝when 与信号相交
        per = []
        conds = {w["scene"]} if w.get("scene") else set()
        emo_conds = {w["emotion"]} if w.get("emotion") else set()
        pos_conds = {w["chapter_pos"]} if w.get("chapter_pos") else set()
        if signals.scene and signals.scene in conds:
            per.append(f"场面:{signals.scene}")
        if signals.emotion and signals.emotion in emo_conds:
            per.append(f"情绪:{signals.emotion}")
        if signals.chapter_pos and signals.chapter_pos in pos_conds:
            per.append(f"章位:{signals.chapter_pos}")
        if not per:
            # 信号与条目条件无交集：只在该条目无条件时兜底出（场景条目无条件＝常见场面）
            if not any((conds, emo_conds, pos_conds)):
                m, hits = 0.3, ("通用场景",)
            else:
                m = 0.0
        else:
            m = min(1.0, 0.4 + 0.3 * len(per))
            hits = per
    # 实体命中：条目指令/标题含出场角色名
    for name in signals.characters:
        if not name:
            continue
        hit = (name in (entry.instruction or "")) or bool(entry.title and name in entry.title)
        if hit:
            m = min(1.0, m + 0.2)
            hits.append(f"角色:{name}")
            break
    return (m, "；".join(hits) if hits else "兜底")


def _usefulness(pref: KbPref | None) -> float:
    """有用率＝采纳/(采纳+弃用)；无记录＝1.0；下限 0.2（标记过「没用」不社死）。"""
    if pref is None or (pref.adopt_count + pref.drop_count) == 0:
        return 1.0
    total = pref.adopt_count + pref.drop_count
    return max(0.2, pref.adopt_count / total)


def _freshness(entry: KbEntry, now) -> float:
    if entry.updated_at is None:
        return 1.0
    days = max(0.0, (now - entry.updated_at).total_seconds() / 86400)
    return 0.5 + 0.5 * (0.5 ** (days / 30))


async def select_block(
    db: AsyncSession,
    *,
    user_id: str,
    signals: MatchSignals,
    genre: str,
    concepts: tuple[str, ...] = ("手法", "文风", "文笔"),
    now=None,
) -> Selection | None:
    """选块主入口。零命中返回 None。确定性：同库同权重同章纲 → 同选集同顺序。"""
    import datetime as _dt

    now = now or _dt.datetime.utcnow()
    groups = await digest_candidates(db, user_id=user_id, genre=genre, concepts=concepts)
    if not groups["tech"] and not groups["style"]:
        return None

    wanted = groups["tech"] | groups["style"]
    rows = (
        (
            await db.execute(
                select(KbEntry).where(KbEntry.id.in_(sorted(wanted))).order_by(KbEntry.id)
            )
        )
        .scalars()
        .all()
    )
    # 维度值集合（适用条件）一次性取回，避免逐条查 tags
    prefs = {
        p.entry_id: p
        for p in (
            await db.execute(
                select(KbPref).where(
                    KbPref.user_id == user_id, KbPref.entry_id.in_(sorted(wanted))
                )
            )
        ).scalars()
    }

    scored: list[SelectedItem] = []
    for e in rows:
        m, reason = _match_score(e, signals)
        if m <= 0.0:
            continue
        score = m * _usefulness(prefs.get(e.id)) * _freshness(e, now)
        scored.append(SelectedItem(entry=e, score=round(score, 6), reason=reason))

    # 排序 tiebreaker 用 title（语义稳定）——entry.id 是随进程随机的 uuid，
    # 同分条目跨进程顺序漂移会打破 golden 集与「重试一致」的跨会话口径
    tech = sorted(
        (s for s in scored if s.entry.concept == "手法"),
        key=lambda s: (-s.score, s.entry.title or "", s.entry.id),
    )[:_TECH_MAX]
    style = sorted(
        (s for s in scored if s.entry.concept != "手法"),
        key=lambda s: (-s.score, s.entry.title or "", s.entry.id),
    )[:_SCENE_STYLE_MAX]

    # 预算截断：优先保手法，写法按分补到上限（成本＝条目指令字符数）
    picked: list[SelectedItem] = []
    used = 0
    for s in tech + style:
        cost = len(s.entry.instruction or "")
        if used + cost > _BUDGET_CHARS and picked:
            break
        picked.append(s)
        used += cost
    if not picked:
        return None
    # 保持 tech 优先、写法随后的稳定顺序
    picked_tech = [s for s in picked if s.entry.concept == "手法"]
    picked_style = [s for s in picked if s.entry.concept != "手法"]
    picked_tech.sort(key=lambda s: (-s.score, s.entry.title or "", s.entry.id))
    picked_style.sort(key=lambda s: (-s.score, s.entry.title or "", s.entry.id))
    return Selection(signals=signals, items=picked_tech + picked_style)
