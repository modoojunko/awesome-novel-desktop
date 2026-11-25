"""产卡工具摘要渲染（c-card-digest，2026-11-25 boss 拍板）。

病根（真机实锤，2026-11-25 设定·简介页）：
  - 病 A：把整个结果 str(dict) 硬切 300~400 字——简介三条候选只装下「一全文＋二开头」，
    模型对作家说「第二个被截断了」，且不知道一共三条；
  - 病 B：只回一句「已出卡，过目后采纳」——卡里写了什么模型完全不知道，
    作家一追问「两条差在哪」就只能编。

口径：
  - 摘要＝卡内容的人话提炼：候选逐条（标题＋正文）、报告问题逐条（正常只计数）、
    长文给全文；绝不 `str(dict)` 上对话。
  - **单卡 1500 字封顶**；放不下时按整条截并明写「其余 N 条在卡上看」——不许静默截断。
  - 收口句保留「已出卡，作家在卡上过目/采纳」，防模型原地重跑
    （writing-assistant spec：摘要带已交付＋本轮完成语义）。
  - 卡 payload 仍是唯一交付源；本模块只决定模型看到的文本。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

# 单卡摘要上限：三条简介候选（约 900 字）能全文装下；长文卡超出部分明确指回卡面。
CARD_DIGEST_BUDGET = 1500

# 报告类「要处理」的状态词（各核词表不同，统一按非正常态收口）
_PROBLEM_STATUS = frozenset(
    {"warn", "miss", "bad", "weak", "risk", "error", "fail", "failed", "missing", "low"}
)

# 收口句（同一句在多个工具复用；改了要同步 writing-assistant spec 的语义要求）：
# 「还没写进书里」防模型把出卡说成已保存，「不用重跑」防模型原地重起草。
TAIL_ADOPT = "（已出卡，还没写进书里；作家在卡上过目采纳，不用重跑）"
TAIL_REPORT = "（只读体检，没动书里的内容；完整报告在卡上）"


def clip_text(text: str, budget: int) -> str:
    """按预算裁剪，尽量切在句读处（。！？；换行），附省略号。"""
    if budget <= 0:
        return ""
    if len(text) <= budget:
        return text
    if budget == 1:
        return "…"
    window = text[: budget - 1]
    cut = max(window.rfind(ch) for ch in "。！？；\n")
    if cut >= budget // 2:
        window = window[: cut + 1]
    return window.rstrip() + "…"


def one_line(value: Any) -> str:
    """折叠空白成单行（候选正文里的换行不占摘要的行数）。"""
    return " ".join(str(value or "").split())


def _assemble(
    head_line: str,
    lines: list[str],
    tail: str,
    budget: int,
    over_marker: Callable[[int], str],
) -> str:
    """标题行＋逐条行装箱：放不下的整条/半条都明确指向卡面，总额不超预算（收口句除外）。"""
    out = [head_line]
    used = len(head_line) + 1
    reserve = (len(tail) + 1) if tail else 0
    for idx, line in enumerate(lines):
        rest = len(lines) - idx - 1
        extra = (len(over_marker(rest)) + 1) if rest else 0
        room = budget - used - reserve - extra
        if room <= 24:
            out.append(over_marker(len(lines) - idx))
            break
        if len(line) > room:
            marker = "…（本条续在卡上）"
            out.append(line[: max(room - len(marker), 1)].rstrip() + marker)
            if rest:
                out.append(over_marker(rest))
            break
        out.append(line)
        used += len(line) + 1
    if tail:
        out.append(tail)
    return "\n".join(out)


def digest_candidates(
    head: str,
    items: Sequence[Any],
    render: Callable[[Any], str],
    *,
    tail: str = TAIL_ADOPT,
    budget: int = CARD_DIGEST_BUDGET,
) -> str:
    """候选逐条：`head（共 N 条）：` ＋ 1./2./3. 每条一行；超预算按条截并标剩余。"""
    total = len(items)
    lines: list[str] = []
    for idx, item in enumerate(items, start=1):
        body = one_line(render(item))
        lines.append(f"{idx}. {body}" if total > 1 else body)
    return _assemble(
        f"{head}（共 {total} 条）：",
        lines,
        tail,
        budget,
        lambda n: f"（还有 {n} 条在卡上看）",
    )


def digest_report(
    head: str,
    items: Sequence[Any],
    *,
    status_of: Callable[[Any], str],
    render: Callable[[Any], str],
    tail: str = TAIL_REPORT,
    budget: int = CARD_DIGEST_BUDGET,
) -> str:
    """报告：问题条目逐条给（含判据名），正常条目只报计数；超预算标剩余。"""
    problems = [
        it for it in items if str(status_of(it) or "").strip().lower() in _PROBLEM_STATUS
    ]
    ok_count = len(items) - len(problems)
    lines = [f"{idx}. {one_line(render(it))}" for idx, it in enumerate(problems, start=1)]
    if not lines:
        lines = ["没有发现要处理的问题。"]
    return _assemble(
        f"{head}：问题 {len(problems)} 条，正常 {ok_count} 条",
        lines,
        tail,
        budget,
        lambda n: f"（还有 {n} 条问题在卡上看）",
    )


def digest_text(
    head: str,
    text: Any,
    *,
    tail: str = TAIL_ADOPT,
    budget: int = CARD_DIGEST_BUDGET,
) -> str:
    """单篇长文：正文尽量全文，超预算截到句读处并注明（卡上有全文）。"""
    body = str(text or "").strip()
    if not body:
        return f"{head}：没有可看的正文（可重试一次）。"
    marker = "（正文较长，全文在卡上；以下为前半）"
    reserve = (len(tail) + 1) if tail else 0
    room = max(budget - len(head) - 2 - reserve - len(marker) - 1, 40)
    lines = [f"{head}："]
    if len(body) > room:
        body = clip_text(body, room)
        lines.append(marker)
    lines.append(body)
    if tail:
        lines.append(tail)
    return "\n".join(lines)


def flatten_fields(value: Any, labels: dict[str, str] | None = None) -> str:
    """dict → 人话多行（键走中文标签；未知键保留原名）——绝不 str(dict) 上对话。"""
    if not isinstance(value, dict):
        return str(value or "").strip()
    labels = labels or {}
    lines: list[str] = []
    for key, val in value.items():
        if val in (None, "", [], {}):
            continue
        name = labels.get(str(key), str(key))
        if isinstance(val, dict):
            sub = flatten_fields(val, labels)
            if sub:
                lines.append(f"{name}：{sub}")
        elif isinstance(val, list):
            parts = []
            for item in val:
                if isinstance(item, dict):
                    parts.append(" / ".join(str(v) for v in item.values() if str(v or "").strip()))
                else:
                    parts.append(str(item))
            joined = "；".join(part for part in parts if part.strip())
            if joined:
                lines.append(f"{name}：{joined}")
        else:
            text = one_line(val)
            if text:
                lines.append(f"{name}：{text}")
    return "\n".join(lines)
