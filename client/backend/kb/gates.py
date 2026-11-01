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

# ─── 回声闸（c-kb-write-block）：条目指令与生成链固定文案撞句判据式拒收 ──
# 基线副本（真源在 write/chapter_writer.py 的 WRITE_CLOSING_LINE / 场景分量定性行 /
# refill_instruction 骨架；kb SHALL NOT import write，此处字面副本由 parity 钉
# tests/test_kb_gates_parity.py 守一致——真源改动时本表同步）。
_ECHO_BASELINES = (
    (
        "输出：仅正文，无标题、无总结、无引导语、无 Markdown；段落之间直接换行，不留空行；"
        "每个场景都写足——这一场戏从起手写到见分晓，一个动作要激起一个反应，"
        "这条没到分量不换下一场；不足目标字数就回到当前场景继续展开，"
        "落点是收笔的位置，不是提前收卷的理由；"
        "结尾收在「章末落点」那一瞬，末句停在动作、台词或声响；"
        "落点是局面陈述或未给动向时以一句未展开的新动向（已登场势力的新压力）硬切，"
        "收束章停在落点本身；落点之后不写一个字。"
    ),
    "动作有回应、局面有推进，这场没写完不进下一场，不得一场两三句带过。",
    (
        "不重述、不改写已写内容，同一时空同场景顺下去，一场接一场继续，"
        "补够下限或写到素材「章末落点」，先到者收笔；只发新写的正文。"
    ),
)
_ECHO_MIN = 8  # 最长公共子串 ≥8 字判撞句


def _lcs_len(a: str, b: str) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for ca in a:
        cur = [0] * (len(b) + 1)
        for j, cb in enumerate(b, 1):
            if ca == cb:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def _check_echo(instruction: str) -> str | None:
    """回声闸：与固定文案最长公共子串 ≥8 字返回可读错误（判据式拒收）。"""
    t = instruction.strip()
    if not t:
        return None
    for base in _ECHO_BASELINES:
        if _lcs_len(t, base) >= _ECHO_MIN:
            return "与系统固定文案撞句，请改写成自己的话"
    return None


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

    # 闸2b 回声闸（c-kb-write-block）：与生成链固定文案撞句硬拒
    echo = _check_echo(instruction)
    if echo:
        result.errors["instruction"] = echo
        result.ok = False

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
