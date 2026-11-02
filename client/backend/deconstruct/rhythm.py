"""节奏统计器（c-deconstruct-knowledge 批A A3）——纯代码零模型，全书口径。

四指标（打标数据上直接算，选章器打标扫的是全书——节奏档反而是全书口径，
比模型提炼维度的采样口径更准；报告页分开标注）：
- 章字数分布：均值/中位/最短/最长
- 每章场景数估计：叙述↔对话转换次数（场面切换常伴随语态转换）
- 爽点间隔：情绪信号峰间的章距（峰＝局部极大且超均值＋标准差）
- 卷章数配比：每卷章数分布
"""

from __future__ import annotations

import itertools
import statistics

from deconstruct.sampler import ChapterInput, tag_emotions


def _scene_switches(text: str) -> int:
    """叙述↔对话转换次数（场面切换的廉价估计）。"""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    switches = 0
    prev_dialogue = None
    for ln in lines:
        is_dialogue = ln.startswith(("「", "『", "“", '"'))
        if prev_dialogue is not None and is_dialogue != prev_dialogue:
            switches += 1
        prev_dialogue = is_dialogue
    return switches


def _peak_intervals(series: list[int]) -> list[int]:
    """情绪峰间章距：局部极大（≥邻章且超均值＋标准差）之间的章数序列。"""
    if len(series) < 3:
        return []
    mean = statistics.mean(series)
    try:
        std = statistics.pstdev(series)
    except statistics.StatisticsError:
        std = 0
    threshold = mean + std
    peaks = [i for i, v in enumerate(series)
             if v > threshold and 0 < i < len(series) - 1
             and v >= series[i - 1] and v >= series[i + 1]]
    return [b - a for a, b in itertools.pairwise(peaks)] if len(peaks) >= 2 else []


def compute_rhythm(chapters: list[ChapterInput]) -> dict:
    """四指标节奏档。输入＝全书章列表（打标数据零模型全量可得）。"""
    if not chapters:
        return {}
    ordered = sorted(chapters, key=lambda c: c.chapter_no)
    lens = [c.char_len for c in ordered]

    scenes_per_chapter = [
        max(1, round(_scene_switches(c.text) / 2) + 1) for c in ordered
    ]

    emotion_curve = [
        sum(tag_emotions(c.text).values()) for c in ordered
    ]
    intervals = _peak_intervals(emotion_curve)

    vol_counts: dict[int, int] = {}
    for c in ordered:
        vol_counts[c.vol_no] = vol_counts.get(c.vol_no, 0) + 1

    return {
        "chapter_len": {
            "mean": round(statistics.mean(lens)),
            "median": round(statistics.median(lens)),
            "min": min(lens),
            "max": max(lens),
        },
        "scenes_per_chapter": {
            "mean": round(statistics.mean(scenes_per_chapter), 1),
            "median": round(statistics.median(scenes_per_chapter), 1),
        },
        "climax_interval": {
            "mean_chapters": round(statistics.mean(intervals), 1) if intervals else None,
            "peaks": len(intervals) + 1 if intervals else 0,
        },
        "volume_chapters": {
            str(vol): n for vol, n in sorted(vol_counts.items())
        },
        "note": "全书打标口径（代码统计，零模型）",
    }
