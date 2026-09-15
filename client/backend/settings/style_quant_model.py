"""style-quant 文档模型（style-settings-v2 tasks 3.1）。

量化层独立 KV（key ``style-quant``，仿 threads 专用键先例——不进 PATH_TO_KEY，
通用 /settings/{type} 端点天然拒绝）。存储形状见 design.md；这里收敛：

- 六行基线（行序固定，渲染/前端共用）：narrative/rhythm/syntax/lexicon/emotion/dialogue_verb
- PUT 仅受理 ``locks``（行级锁定切换）；基线数值服务端只写（前端传值一律忽略）
- ``commit``：draft → 正式区＋history 追加（锁定行如实记录来源）＋draft 清空；幂等
- ``confidence`` 缺失/0 ＝ 未蒸馏；容差分档 ≥70→±10% / ≥50→±20% / 其余→±30%
"""

from __future__ import annotations

QUANT_KEY = "style-quant"

# 六行基线（行序固定；行名 → 人话标签，渲染与前端共用此表）
BASELINE_ROWS: list[tuple[str, str]] = [
    ("narrative", "镜头与人称"),
    ("rhythm", "篇幅配比（五层）"),
    ("syntax", "句子与段落"),
    ("lexicon", "修饰密度"),
    ("emotion", "情绪外化"),
    ("dialogue_verb", "对话与动词质感"),
]
BASELINE_KEYS = [k for k, _ in BASELINE_ROWS]

SAMPLE_MIN = 3000
SAMPLE_MAX = 10000

_EMPTY = {
    "version": 1,
    "confidence": 0,
    "sample_chars": 0,
    "updated_at": "",
    "baseline": {},
    "details": {},
    "portrait": "",
    "history": [],
    "draft": {},
}


def empty_quant() -> dict:
    import copy

    return copy.deepcopy(_EMPTY)


def quant_doc(raw: dict | None) -> dict:
    """读边界：补默认形状（不抛错、缺省安全）。"""
    if not isinstance(raw, dict):
        return empty_quant()
    doc = dict(_EMPTY)
    doc.update({k: v for k, v in raw.items() if k in _EMPTY})
    return doc


def tolerance_for(confidence: int) -> int:
    """容差分档：≥70→±10% / ≥50→±20% / 其余→±30%。"""
    if confidence >= 70:
        return 10
    if confidence >= 50:
        return 20
    return 30


def confidence_for(sample_chars: int, chapter_count: int) -> int:
    """蒸馏置信度（awesome-novel 同式）：样本量 + 章数双因子封顶 100。"""
    return min(100, 20 + min(40, sample_chars // 150) + min(40, chapter_count * 5))


def apply_locks(doc: dict, locks: dict) -> dict:
    """PUT 唯一写路径：行级锁定切换；未知行忽略，其他键一律不动。

    已知行不存在时建空骨架（未蒸馏态也允许预锁；容差按当前 confidence 分档）。
    """
    baseline = doc.get("baseline") or {}
    try:
        conf = int(doc.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0
    for row, flag in (locks or {}).items():
        if row not in BASELINE_KEYS:
            continue
        item = baseline.get(row) if isinstance(baseline.get(row), dict) else {}
        item.setdefault("value", "")
        item.setdefault("tolerance", tolerance_for(conf))
        item["locked"] = bool(flag)
        baseline[row] = item
    doc["baseline"] = baseline
    return doc


def build_baseline(step3: dict) -> dict:
    """step3 出参 → 六行基线（每行 {value, tolerance, locked:false}；锁定不继承 draft）。

    value 统一存字符串（rhythm 五层占比拼成一句），渲染/前端只展示。
    """
    src = step3.get("baseline") if isinstance(step3.get("baseline"), dict) else {}
    out = {}
    for key, _label in BASELINE_ROWS:
        v = src.get(key)
        if key == "rhythm" and isinstance(v, dict):
            v = " ".join(
                f"{k} {v[k]}%" for k in ("dialogue", "action", "narration", "environment", "inner") if k in v
            )
        elif isinstance(v, (dict, list)):
            v = "；".join(str(x) for x in (v if isinstance(v, list) else v.values()))
        out[key] = {"value": str(v or "").strip(), "tolerance": tolerance_for(int(step3.get("confidence") or 0)), "locked": False}
    return out


def commit_draft(doc: dict, *, sample_chars: int, chapter_count: int, at: str) -> dict:
    """draft → 正式区＋history 追加；幂等（draft 空时原样返回）。

    锁定行跳过重蒸馏：保留上一版值，history.mixture 如实记录混合来源。
    """
    draft = doc.get("draft") or {}
    step3 = draft.get("step3")
    if not isinstance(step3, dict) or not step3:
        return doc
    confidence = confidence_for(sample_chars, chapter_count)
    baseline = build_baseline({**step3, "confidence": confidence})
    prev = doc.get("baseline") or {}
    mixture: dict = {}
    for row, item in baseline.items():
        p = prev.get(row)
        if isinstance(p, dict) and p.get("locked"):
            baseline[row] = {**item, "value": str(p.get("value", item["value"]))}
            mixture[row] = "locked(上一版)"
    doc["confidence"] = confidence
    doc["sample_chars"] = sample_chars
    doc["updated_at"] = at
    doc["baseline"] = baseline
    doc["details"] = step3.get("details") or {}
    doc["portrait"] = str(step3.get("portrait") or "")
    doc.setdefault("history", []).append(
        {
            "at": at,
            "sample_chars": sample_chars,
            "confidence": confidence,
            "baseline": baseline,
            "mixture": mixture,
        }
    )
    doc["draft"] = {}
    return doc
