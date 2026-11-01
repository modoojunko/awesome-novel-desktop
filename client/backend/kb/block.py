"""本章写法块组装器（c-kb-write-block B1＋批F F5/F7）。

- 块首 v2（四角色评审定稿）：三句声明——只约束写法不新增人物事件／红线契约
  （含场景分量与字数）优先／条件标签=本章命中维
- 条件标签**只发本章命中维度**（消除「选择器 OR vs 标签 AND」错位——提示词
  工程师 P0-3）：标签数据＝SelectedItem.reason（选择器已记录的命中清单）；
  手法 payload.scene 仅在等于信号场面时作为展示标签
- 组装守卫：逐条回声闸＋结构消毒（存量脏数据兜底），命中跳过记 reason
- 纯函数：同 Selection → 同字节（重试一致性的组装侧保证）
"""

from __future__ import annotations

import re

from kb.gates import _check_echo, _check_structure
from kb.match import Selection

_BLOCK_HEADER = (
    "【本章写法指引】以下条目只约束写法，不改变剧情，不新增人物、事件或设定；"
    "与反AI结构红线或输出契约（含场景分量与字数要求）冲突时，红线与契约优先；"
    "中括号＝本章已命中的入选条件，以·分隔场面、情绪、章位；"
    "带场面标签的条目只在该类场面执行，其余条目全章适用。"
)

_PAYLOAD_SCENE_RE = re.compile(r'"scene"\s*:\s*"([^"]+)"')


def _when_of(entry) -> dict:
    try:
        w = entry.when_json
        parsed = __import__("json").loads(w or "{}")
    except (ValueError, AttributeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _payload_scene(entry) -> str:
    m = _PAYLOAD_SCENE_RE.search(entry.payload_json or "")
    return m.group(1) if m else ""


def _tag(entry, signals) -> str:
    """条件标签＝**本章命中维度**（signals 非空且等于条目条件/记录值才上标签）。

    空标签＝全章适用（块首语义）。"""
    w = _when_of(entry)
    parts = []
    scene = w.get("scene") or _payload_scene(entry)
    if scene and scene == signals.scene:
        parts.append(scene)
    if w.get("emotion") and w["emotion"] == signals.emotion:
        parts.append(w["emotion"])
    if w.get("chapter_pos") and w["chapter_pos"] == signals.chapter_pos:
        parts.append(w["chapter_pos"])
    label = "·".join(parts)
    return f"[{label}]" if label else ""


def build_block(
    selection: Selection, *, skip_guards: bool = False
) -> tuple[str | None, list[tuple[str, str]]]:
    """Selection → (块文本, 跳过清单[(entry_id, reason)])。零条目返回 (None, …)。

    signals 缺失（旧 run 重建无场景值）→ 标签退化为全空（全章适用语义，安全侧）。"""
    if selection is None or not selection.items:
        return None, []
    signals = selection.signals
    skipped: list[tuple[str, str]] = []
    lines = [_BLOCK_HEADER]
    for item in selection.items:
        text = (item.text_override or (item.entry.instruction or "")).strip()
        if not text:
            skipped.append((item.entry.id, "空指令"))
            continue
        if not skip_guards:
            if _check_echo(text):
                skipped.append((item.entry.id, _check_echo(text)))
                continue
            if _check_structure(text):
                skipped.append((item.entry.id, _check_structure(text)))
                continue
        tag = _tag(item.entry, signals) if signals is not None else ""
        lines.append(f"- {tag}{text}" if tag else f"- {text}")
    if len(lines) == 1:
        return None, skipped
    return "\n".join(lines), skipped
