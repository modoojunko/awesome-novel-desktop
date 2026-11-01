"""本章写法块组装器（c-kb-write-block B1）。

- 块首三句声明（拍板口径：不改剧情／红线契约优先／条件标签语义）
- 条件标签＝when_json 适用条件（scene/emotion/chapter_pos），手法另以 payload.scene
  作展示标签（记录字段，不参与匹配——match.py 同口径）
- 组装守卫：逐条再跑回声闸（存量脏数据兜底），命中跳过记 reason
- 纯函数：同 Selection → 同字节（重试一致性的组装侧保证）
"""

from __future__ import annotations

import json

from kb.gates import _check_echo
from kb.match import Selection


def _when_of(entry) -> dict:
    try:
        w = json.loads(entry.when_json or "{}")
    except ValueError:
        return {}
    return w if isinstance(w, dict) else {}


def _payload_scene(entry) -> str:
    try:
        p = json.loads(entry.payload_json or "{}")
    except ValueError:
        return ""
    v = p.get("scene") if isinstance(p, dict) else None
    return str(v or "")


def _tag(entry) -> str:
    w = _when_of(entry)
    parts = [w.get("scene") or _payload_scene(entry) or "", w.get("emotion") or "", w.get("chapter_pos") or ""]
    label = "·".join(p for p in parts if p)
    return f"[{label}]" if label else ""


def build_block(selection: Selection, *, skip_echo_guard: bool = False) -> tuple[str | None, list[tuple[str, str]]]:
    """Selection → (块文本, 跳过清单[(entry_id, reason)])。零条目返回 (None, …)。

    确定性：遍历顺序＝selection.items 顺序（选择器已稳定排序）。
    """
    if selection is None or not selection.items:
        return None, []
    skipped: list[tuple[str, str]] = []
    lines = [
        (
            "【本章写法指引】以下只约束写法，不改变剧情；"
            "与反AI结构红线或输出契约冲突时，红线与契约优先；"
            "中括号标明适用场面，只在该类场面生效；未标条目全章适用。"
        )
    ]
    for item in selection.items:
        text = (item.entry.instruction or "").strip()
        if not text:
            skipped.append((item.entry.id, "空指令"))
            continue
        if not skip_echo_guard:
            echo = _check_echo(text)
            if echo:
                skipped.append((item.entry.id, echo))
                continue
        tag = _tag(item.entry)
        lines.append(f"- {tag}{text}" if tag else f"- {text}")
    if len(lines) == 1:
        return None, skipped
    return "\n".join(lines), skipped
