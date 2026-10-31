"""入库闸门——所有来源的知识入库前过同一组闸门。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class GateResult:
    ok: bool
    errors: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    needs_rewrite: bool = False


# ─── 长度闸 ──
_INSTRUCTION_MAX = 240
_EXAMPLE_MAX = 500
_NEGATIVE_MAX = 200
_BANNED_MAX = 50

# ─── 红线闸：强禁令词族（与反AI结构红线冲突的手法写法） ──
_RED_LINE_PATTERNS = [
    re.compile(r"破折号.{0,4}停顿"),
    re.compile(r"[「『][…⋯]{2,}[』」]"),
    re.compile(r"省略号.{0,4}对话"),
    re.compile(r"『[^』]{1,8}』他说"),
    re.compile(r"'[^']{1,8}'他说"),
]


def _check_instruction_length(text: str) -> str | None:
    """硬闸：非空＋≤240 字。"""
    t = text.strip()
    if not t:
        return "指令不能为空"
    if len(t) > 240:
        return "指令超过 240 字"
    return None


def _check_sentence_end(text: str) -> str | None:
    """软闸（warning 不拦截）：指令应句末断；剥掉引号/括号收尾后看末字符。

    判定集只含句末标点——引号、括号先剥，否则 `他说："走。"` 末字符是引号误报。
    """
    t = text.strip()
    if not t:
        return None
    stripped = t.rstrip("」』）\"'\u201d\u2019 ")
    if stripped and stripped[-1] not in "。！？…":
        return "指令未以句末标点收尾，建议补句末断"
    return None


def _check_original_text(sample: str, original_texts: list[str]) -> bool:
    """原文闸：与原文连续 ≥20 字逐字相同返回 True。"""
    s = sample.strip()
    if not s:
        return False
    for orig in original_texts:
        o = orig.strip()
        if not o:
            continue
        # 滑窗比对
        for i in range(len(o) - 19):
            if o[i:i + 20] in s:
                return True
    return False


def _check_red_line(instruction: str) -> str | None:
    """红线闸：指令含与反AI结构红线冲突的写法返回提示。"""
    for pat in _RED_LINE_PATTERNS:
        if pat.search(instruction):
            return "指令与反AI结构红线冲突，请改写（避免破折号停顿/省略号对话等手法）"
    return None


def check_gates(
    *,
    concept: str,
    instruction: str,
    payload: dict,
    example: str = "",
    negative_example: str = "",
    when_json: dict | None = None,
    original_texts: list[str] | None = None,
) -> GateResult:
    """入库闸门。返回 GateResult(ok=是否可入库, errors=逐字段错误, needs_rewrite=是否待改写)。"""
    result = GateResult(ok=True)
    original_texts = original_texts or []
    when = when_json or {}

    # 闸1 概念词表（payload 层强校验已覆盖）

    # 闸2 指令长度（硬）＋句末断（软）
    err = _check_instruction_length(instruction)
    if err:
        result.errors["instruction"] = err
        result.ok = False
    warn = _check_sentence_end(instruction)
    if warn:
        result.warnings.append(warn)

    # 闸3 红线闸
    err = _check_red_line(instruction)
    if err:
        result.warnings.append(err)

    # 闸4 原文闸
    for text_field in (example, payload.get("sample", ""), payload.get("craft", "")):
        if text_field and _check_original_text(text_field, original_texts):
            result.needs_rewrite = True
            result.warnings.append("像原文摘录，改成自己的话")
            break

    # 闸5 when_json 概念白名单
    if when and concept in ("世界设定", "角色设定"):
        result.errors["when_json"] = f"{concept}不支持适用条件"
        result.ok = False

    # 闸6 payload 长度
    if example and len(example) > _EXAMPLE_MAX:
        result.errors["example"] = f"正例超过 {_EXAMPLE_MAX} 字"
        result.ok = False
    if negative_example and len(negative_example) > _NEGATIVE_MAX:
        result.errors["negative_example"] = f"反例超过 {_NEGATIVE_MAX} 字"
        result.ok = False

    return result
