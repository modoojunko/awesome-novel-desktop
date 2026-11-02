"""智能拆书选章器（c-deconstruct-knowledge 批A）——纯代码零模型。

选章规则（boss 锁定 2026-11-01）：
- 第 1-3 章固定入选（开篇手法样本：钩子/登场/设定铺陈）
- 第 4 章起逐章打标：七类场面关键词命中（词族复用 kb/concepts——deconstruct→kb
  方向合法，与写法块选择器同词表单源）＋对话密度＋短句率＋情绪词密度
  → 类型标签＋每千字信号强度（除以章长防长章刷分）
- 每类型取强度 Top 3-4，约束同卷 ≤2 章；章长 <800 或 >P95 跳过
- 「未分类」章不硬猜，仅作字数居中兜底补足（固定步长，零随机）
- 封顶 31 章（3＋7类×4）；单遍 O(总字数)，千万字亚秒级

打标准确率由校准工具把关（python -m deconstruct.calibrate，开发期一次性，
大模型独立读选中章判类对表——命中率 <70% 调词族阈值再测）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kb.concepts import _EMOTION_ALIASES, EMOTIONS, SCENES

# 打标信号常量（调优改这里，校准工具验证效果）
DIALOGUE_RATIO_BONUS = 3.0     # 对话密度加成（对峙/文戏）
SHORT_RATE_BONUS = 2.0         # 短句率加成（打斗）
EXCLAIM_BONUS = 2.0            # 惊叹密度加成（打斗）
DIALOGUE_RATIO_LINE = 0.4      # 对话密度阈值
SHORT_RATE_LINE = 0.5          # 短句率阈值
EXCLAIM_PER_K = 5.0            # 每千字惊叹阈值
TITLE_WEIGHT = 3               # 章标题命中权重（标题是网文最强分类信号）
MIN_LEN = 800                  # 过短章跳过
CAP = 31                       # 采样集硬上限（3＋7类×4）
FLOOR = 12                     # 兜底补足下限
SAME_VOLUME_MAX = 2            # 同卷上限
PER_TYPE = 4                   # 每类型代表章数

_SENT_SPLIT = re.compile(r"[。！？…]")
_DIALOGUE_LINE = re.compile(r'^\s*[「『“"]')


@dataclass
class ChapterInput:
    """切分产物的一章（纯数据——采样器不碰 ORM，可单测）。"""

    ref: str
    vol_no: int
    chapter_no: int
    title: str = ""
    text: str = ""

    @property
    def char_len(self) -> int:
        return len(self.text)


@dataclass
class ChapterTag:
    label: str      # 七类场面之一；""＝未分类（不硬猜）
    strength: float  # 每千字信号强度
    signals: dict = field(default_factory=dict)


def tag_chapter(text: str, *, title: str = "", char_len: int | None = None) -> ChapterTag:
    """单章打标：类型标签＋每千字信号强度。全类零分 → 未分类。"""
    char_len = char_len if char_len is not None else len(text)
    if char_len <= 0:
        return ChapterTag(label="", strength=0.0)

    from kb.concepts import _SCENE_ALIASES

    title_and_body = f"{title}\n{text}"  # 标题命中按 TITLE_WEIGHT 加权
    score: dict[str, float] = {}
    for scene in SCENES:
        hit = sum(title_and_body.count(a) * (TITLE_WEIGHT if a in title else 1)
                  for a in _SCENE_ALIASES[scene])
        score[scene] = float(hit)

    # 对话密度：以引号开头的行占比
    lines = [ln for ln in text.split("\n") if ln.strip()]
    dialogue_lines = sum(1 for ln in lines if _DIALOGUE_LINE.match(ln))
    dialogue_ratio = dialogue_lines / max(len(lines), 1)

    # 短句率
    sentences = [s for s in _SENT_SPLIT.split(text) if s.strip()]
    short_rate = (sum(1 for s in sentences if len(s.strip()) <= 12) / max(len(sentences), 1))

    # 惊叹密度（每千字）
    exclaim_density = (text.count("！") + text.count("？")) / char_len * 1000

    # 零命中早退：词表全没命中＝无场面信号——加成项只调制有关键词命中的类，
    # 不能凭对话/短句统计凭空造标签（「排队半天」≠打斗）
    if all(v <= 0 for v in score.values()):
        return ChapterTag(label="", strength=0.0, signals={
            "dialogue_ratio": round(dialogue_ratio, 3),
            "short_rate": round(short_rate, 3),
            "exclaim_density": round(exclaim_density, 2),
        })

    if dialogue_ratio > DIALOGUE_RATIO_LINE:
        score["对峙"] += DIALOGUE_RATIO_BONUS
        score["文戏"] += DIALOGUE_RATIO_BONUS
    if short_rate > SHORT_RATE_LINE:
        score["打斗"] += SHORT_RATE_BONUS
    if exclaim_density > EXCLAIM_PER_K:
        score["打斗"] += EXCLAIM_BONUS

    label = max(score, key=lambda k: score[k])
    if score[label] <= 0:
        return ChapterTag(label="", strength=0.0, signals={
            "dialogue_ratio": round(dialogue_ratio, 3),
            "short_rate": round(short_rate, 3),
            "exclaim_density": round(exclaim_density, 2),
        })
    strength = score[label] / (char_len / 1000 + 1)
    return ChapterTag(label=label, strength=round(strength, 4), signals={
        "dialogue_ratio": round(dialogue_ratio, 3),
        "short_rate": round(short_rate, 3),
        "exclaim_density": round(exclaim_density, 2),
    })


def tag_emotions(text: str) -> dict[str, int]:
    """情绪词命中曲线的一章采样点（节奏统计器爽点间隔的输入）。"""
    return {e: sum(text.count(a) for a in _EMOTION_ALIASES[e]) for e in EMOTIONS}


@dataclass
class SmartSelection:
    """选章结果：固定开篇＋类型代表＋兜底，附每章标签（节奏统计复用）。"""

    selected_refs: list[str]
    fixed_refs: list[str]
    tags: dict[str, ChapterTag]       # ref → 打标（含未入选章——节奏统计要用全书曲线）
    skipped: dict[str, str]           # ref → 跳过原因（过长/过短）


def select_chapters(
    chapters: list[ChapterInput],
    *,
    opening_count: int = 3,
    per_type: int = PER_TYPE,
    same_volume_max: int = SAME_VOLUME_MAX,
    min_len: int = MIN_LEN,
    cap: int = CAP,
    floor: int = FLOOR,
) -> SmartSelection:
    """选章主入口。确定性：同输入同输出（兜底用固定步长，零随机）。"""
    ordered = sorted(chapters, key=lambda c: c.chapter_no)
    tags = {c.ref: tag_chapter(c.text, title=c.title, char_len=c.char_len) for c in ordered}
    lengths = sorted(c.char_len for c in ordered)
    median = lengths[len(lengths) // 2] if lengths else 0
    long_cap = max(min_len * 6, median * 4)  # P95 会被超长章自己顶掉——中位×4 硬帽

    fixed = [c.ref for c in ordered[:opening_count]]
    fixed_set = set(fixed)

    skipped: dict[str, str] = {}
    candidates = []
    for c in ordered[opening_count:]:
        if c.char_len < min_len:
            skipped[c.ref] = f"过短（{c.char_len}字）"
            continue
        if long_cap and c.char_len > long_cap:
            skipped[c.ref] = f"超长（{c.char_len}字）"
            continue
        candidates.append(c)

    # 每类型取强度 Top（贪心＋同卷约束），跨类型互斥（一章只归一个类型——打标已是单标签）
    by_type: dict[str, list[tuple[float, ChapterInput]]] = {}
    for c in candidates:
        t = tags[c.ref]
        by_type.setdefault(t.label, []).append((t.strength, c))
    picked: list[ChapterInput] = []
    vol_count: dict[int, int] = {}
    for scene in SCENES:  # SCENES 序＝确定性遍历序
        taken_vol: dict[int, int] = dict(vol_count)
        for strength, c in sorted(by_type.get(scene, []), key=lambda x: (-x[0], x[1].chapter_no)):
            if len([p for p in picked if tags[p.ref].label == scene]) >= per_type:
                break
            if taken_vol.get(c.vol_no, 0) >= same_volume_max:
                continue
            if c.ref in fixed_set or any(p.ref == c.ref for p in picked):
                continue
            picked.append(c)
            taken_vol[c.vol_no] = taken_vol.get(c.vol_no, 0) + 1
        vol_count.update({k: v for k, v in taken_vol.items()})

    selected = [c for c in ordered if c.ref in fixed_set] + picked
    # 兜底：总量不足下限时按「字数居中序」固定步长补未入选章（零随机）。
    # 已跳过章（过短/超长）不进兜底池——质量过滤不得被兜底绕过。
    if len(selected) < floor:
        chosen = {c.ref for c in selected} | set(skipped)
        pool = sorted(
            (c for c in ordered if c.ref not in chosen),
            key=lambda c: abs(c.char_len - (lengths[len(lengths) // 2] if lengths else 0)),
        )
        step = max(1, len(pool) // max(floor - len(selected), 1))
        for c in pool[::step]:
            if len(selected) >= floor:
                break
            if c.ref not in {x.ref for x in selected}:
                selected.append(c)
    selected = selected[:cap]
    sel_refs = [c.ref for c in selected]
    return SmartSelection(
        selected_refs=sel_refs,
        fixed_refs=fixed,
        tags=tags,
        skipped=skipped,
    )
