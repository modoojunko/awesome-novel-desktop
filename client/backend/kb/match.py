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

from kb.concepts import normalize_emotion
from kb.merged import STYLE_SLOTS_IN_BLOCK as _STYLE_SLOTS_IN_BLOCK
from kb.merged import digest_baseline_ids, load_baseline_entries
from models.kb import KbBookEntry, KbBookEntryTag, KbEntryTag, KbKnowledge, KbPref

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
# 单源在 kb/merged.py（基线段短名单共用同一判定，防两侧漂移）
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
    entry: KbKnowledge
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
    book_scope: str | None = None,
) -> dict[str, set[str]]:
    """候选短名单（公开：P1 LLM 选择器的候选摘要以本集合为域）。

    book_scope=书 id：候选走书级副本标签（kb_book_entry_tags 按 novel_id 过滤）——
    书副本已是开书时对 merged 视图的一次性快照，不再叠加实时基线层；
    None：账号级标签域（存量兼容路径）＋基线层（merged，c-kb-baseline）。
    """
    tag_model = KbBookEntryTag if book_scope else KbEntryTag
    if book_scope:
        # 书域：副本已按题材筛过，只按 novel_id 收窄（genre 二次过滤会误杀通用条目）
        stmt = select(tag_model.entry_id, tag_model.dim, tag_model.value).where(
            tag_model.dim.in_(("concept", "scope", "slot")),
            tag_model.novel_id == book_scope,
        )
    else:
        # 账号级存量路径：题材/状态必须在标签查询就收窄——select_block 只补 status，
        # genre 无第二道闸；漏掉会把其他题材条目选进本书（跨题材污染）
        stmt = (
            select(tag_model.entry_id, tag_model.dim, tag_model.value)
            .select_from(tag_model)
            .join(KbKnowledge, KbKnowledge.id == tag_model.entry_id)
            .where(
                tag_model.user_id == user_id,
                tag_model.dim.in_(("concept", "scope", "slot")),
                KbKnowledge.status == "active",
                KbKnowledge.genre.in_((genre, "")) if genre else True,
            )
        )
    rows = (await db.execute(stmt)).all()
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
    if not book_scope:
        # merged 域：用户条目 ∪ 基线层（基线已排 hide、edit 副本在取行时套用）
        base = await digest_baseline_ids(db, user_id=user_id, genre=genre, concepts=concepts)
        tech |= base["tech"]
        style |= base["style"]
    # 稳定排序截断（id 序）——短名单超 200 时保序取前
    return {
        "tech": set(sorted(tech)[:_SHORTLIST_MAX]),
        "style": set(sorted(style)[:_SHORTLIST_MAX]),
    }


# ── 打分与配额（A4）──────────────────────────────────────────


def _when_of(entry: KbKnowledge) -> dict:
    try:
        w = json.loads(entry.when_json or "{}")
    except ValueError:
        return {}
    return w if isinstance(w, dict) else {}


def _emotion_conds(when: dict, signals) -> set[str]:
    """条目是否声明了**可判定**的情绪条件（供「无条件＝全章适用」分支用）。

    emotion 是短自由文本（≤6 字）；只有能归一到情绪族的才算条件——归一不了的写法
    （如「复杂」）不该把条目变成永远 0 分（`select_block` 丢弃 m<=0），按无条件处理。
    """
    raw = str(when.get("emotion") or "")
    return {raw} if normalize_emotion(raw) else set()


def _emotion_hit(when: dict, signals) -> bool:
    """情绪命中：条件与信号**双方都归一**后相等（「压抑—不安」↔「不安」能碰上）。"""
    want = normalize_emotion(str(when.get("emotion") or ""))
    got = normalize_emotion(str(signals.emotion or ""))
    return bool(want and got and want == got)


def _match_score(entry: KbKnowledge, signals: MatchSignals) -> tuple[float, str]:
    """匹配度∈[0,1]＋命中理由。适用条件＝when_json（payload.scene 是记录字段
    不参与匹配——§7.1「匹配＝when_json∪实体命中」口径）。手法无 when 给基础分。"""
    hits: list[str] = []
    m = 0.0
    w = _when_of(entry)
    if entry.concept == "手法":
        conds = {w["scene"]} if w.get("scene") else set()
        emo_conds = _emotion_conds(w, signals)
        pos_conds = {w["chapter_pos"]} if w.get("chapter_pos") else set()
        if not any((conds, emo_conds, pos_conds)):
            m, hits = 0.5, ("全章适用",)
        else:
            per = []
            if signals.scene and signals.scene in conds:
                per.append(f"场面:{signals.scene}")
            if signals.emotion and _emotion_hit(w, signals):
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
        emo_conds = _emotion_conds(w, signals)
        pos_conds = {w["chapter_pos"]} if w.get("chapter_pos") else set()
        if signals.scene and signals.scene in conds:
            per.append(f"场面:{signals.scene}")
        if signals.emotion and _emotion_hit(w, signals):
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


def _freshness(entry: KbKnowledge, now) -> float:
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
    book_scope: str | None = None,
    now=None,
) -> Selection | None:
    """选块主入口。零命中返回 None。确定性：同库同权重同章纲 → 同选集同顺序。"""
    import datetime as _dt

    now = now or _dt.datetime.utcnow()
    groups = await digest_candidates(
        db, user_id=user_id, genre=genre, concepts=concepts, book_scope=book_scope
    )
    if not groups["tech"] and not groups["style"]:
        return None

    wanted = groups["tech"] | groups["style"]
    entry_model = KbBookEntry if book_scope else KbKnowledge
    user_rows = (
        (
            await db.execute(
                select(entry_model)
                .where(entry_model.id.in_(sorted(wanted)), entry_model.status == "active")
                .order_by(entry_model.id)
            )
        )
        .scalars()
        .all()
    )
    # 基线层取行（hide 已排、edit 副本已套＝merged 口径）；书域副本已含快照则不叠加
    base_rows = (
        [] if book_scope
        else await load_baseline_entries(db, user_id=user_id, ids=sorted(wanted))
    )
    rows = list(user_rows) + list(base_rows)
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
