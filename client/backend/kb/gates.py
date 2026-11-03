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


_STRUCTURE_LINE = __import__("re").compile(r"^(#{1,6}\s|---|\-\s|【)")


def _check_structure(instruction: str) -> str | None:
    """结构消毒闸（批F F5；design §7.1 补丁5 兑现）：条目指令是单行短句——
    含换行或行首结构标记会被当成提示词结构（伪节标题/伪块首注入面）。"""
    t = instruction.strip()
    if not t:
        return None
    if "\n" in t:
        return "指令需单行短句——含换行会被当成提示词结构，请改成单行或拆成多条"
    if _STRUCTURE_LINE.match(t):
        return "指令不能以 #、-、【 等结构标记开头——会被当成提示词结构"
    if "【本章写法指引】" in t:
        return "与写法块块首声明撞句，请改成自己的话"
    return None


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

    # 闸2b 回声闸＋结构消毒（c-kb-write-block）：撞句/伪结构硬拒
    echo = _check_echo(instruction)
    if echo:
        result.errors["instruction"] = echo
        result.ok = False
    structure = _check_structure(instruction)
    if structure:
        result.errors["instruction"] = structure
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


# ─── 基线包单条硬闸（c-kb-baseline C1）────────────────────────────
# 内容仓 tools/validate.py 与 C 端同步器共用同一判据集（fixture 双端 parity：
# tests/fixtures/kb_baseline_gate_cases.json）。返回 None＝合格，否则返回
# 稳定错误码（前端/CI 只按码展示，不解析文案）。
_SRC_KEY_RE = re.compile(r"^baseline:[^:\s]+:[^:\s]+$")
_BASELINE_CONCEPTS = ("手法", "文风", "文笔")
_WHEN_KEYS = ("scene", "emotion", "chapter_pos")


def check_baseline_entry(e: object) -> str | None:
    """基线包条目闸（同步端逐条复验＋内容仓 validate 同集单源）。

    规则顺序固定（parity 依赖首个违规码）：
    src_key → concept → genre → title → instruction → payload → when。

    向前兼容（c-kb-forward-compat）：本判据即「本端看得懂什么」的边界——
    返回非 None 的条目由同步器**整条跳过**（其余照收），不构成整包拒收；
    未知顶层字段不设判据（包级扩展字段老客户端忽略即可）。
    """
    from kb.concepts import CHAPTER_POS, EMOTIONS, SCENES, THEMES

    if not isinstance(e, dict):
        return "entry_not_object"
    key = e.get("src_key")
    if not isinstance(key, str) or not _SRC_KEY_RE.match(key) or len(key) > 120:
        return "src_key_invalid"
    concept = e.get("concept")
    if concept not in _BASELINE_CONCEPTS:
        return "concept_invalid"
    genre = e.get("genre")
    if not isinstance(genre, str) or (genre and genre not in THEMES):
        return "genre_invalid"
    title = e.get("title")
    if not isinstance(title, str) or len(title) > 40:
        return "title_invalid"

    ins = e.get("instruction")
    if not isinstance(ins, str):
        return "instruction_invalid"
    text = ins.strip()
    if not (6 <= len(text) <= _INSTRUCTION_MAX):
        return "instruction_length"
    structure = _check_structure(text)
    if structure:
        return "instruction_structure"
    if _check_echo(text):
        return "instruction_echo"

    payload = e.get("payload")
    if not isinstance(payload, dict):
        return "payload_invalid"
    if concept == "手法" and not str(payload.get("instruction") or "").strip():
        return "payload_slot_missing"
    if concept in ("文风", "文笔") and not str(payload.get("slot") or "").strip():
        return "payload_slot_missing"

    when = e.get("when")
    if when is None:
        return None
    if not isinstance(when, dict) or len(when) > 3:
        return "when_invalid"
    allowed = {"scene": set(SCENES), "emotion": set(EMOTIONS), "chapter_pos": set(CHAPTER_POS)}
    for k, v in when.items():
        if k not in _WHEN_KEYS:
            return "when_invalid"
        if not isinstance(v, str) or v not in allowed[k]:
            return "when_invalid"
    return None
