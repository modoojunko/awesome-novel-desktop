"""动作协议解析（c-writing-agent 批A 1.4）。

文本协议（一期，全模型兼容）：每步模型产一个 JSON——
  {"thought": str, "action": "tool"|"final", "tool": str, "args": {}, "reply": str}

三级兜底（design §循环）：严格 json → 修复（复用 story/character_agent.py `_repair_json`
手法：中文标点/尾逗号/单引号/字面量）→ 重试一次（由调用方做）→ 降级为纯 chat 回答
（degraded=true）。另含 openworker 抢救语义（providers/openai_provider.py:389-536）：
模型把动作当正文输出时的「从文本中抢救 JSON」——代码围栏提取＋首尾括号截取。
未知工具名由调用方按 final 处理（本模块只认语法，不认工具存在性）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# 合法动作动词（协议封闭集）
ACTION_VERBS = ("tool", "final")

_REPLY_FALLBACK = "（我这一步没想明白，先直接回答：\n{snippet}）"


@dataclass
class Action:
    """一步动作的解析结果。degraded=True 表示协议没服从、走了降级路径。"""

    kind: str  # "tool" | "final" | "degraded"
    thought: str = ""
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    reply: str = ""
    raw: str = ""
    degraded: bool = False


def _repair_json(text: str) -> str | None:
    """修复常见毛病：中文标点、单引号、Python/JS 字面量、尾逗号。

    手法在 story/character_agent.py `_repair_json` 基础上升级：单引号键值与
    True/False/None 字面量交给 `ast.literal_eval`（Python 原生解析，覆盖正则
    lookbehind 漏掉的 `'args': {'area': 'cast'}` 冒号后取值形态）。
    """
    result = text.strip()

    # Chinese punctuation → English
    result = result.replace("：", ":").replace("，", ",")
    result = result.replace("（", "(").replace("）", ")")

    # 1) 原样直读
    try:
        json.loads(result)
        return result
    except json.JSONDecodeError:
        pass

    # 2) Python 字面量（单引号/True/False/None）→ 合法 JSON
    try:
        import ast

        literal = ast.literal_eval(result)
        return json.dumps(literal, ensure_ascii=False)
    except (ValueError, SyntaxError, TypeError, MemoryError):
        pass

    # 3) Single-quoted keys/values → double-quoted（字面量路径漏网的残段）
    result = re.sub(r"(?<=[{,:\s])'([^']+?)'(?=\s*[:,\]}])", r'"\1"', result)

    # Trailing commas before ] or }
    result = re.sub(r",\s*([}\]])", r"\1", result)

    # Python/JS → JSON literals
    result = result.replace("None", "null").replace("undefined", "null")
    result = result.replace("True", "true").replace("False", "false")

    try:
        json.loads(result)
        return result
    except json.JSONDecodeError:
        return None


def _extract_json(text: str) -> dict | None:
    """从模型文本提取 JSON 对象：直接解析→修复→代码围栏→首尾花括号截取。绝不抛。"""
    cleaned = text.strip()

    # 1. Direct parse (try raw, then repaired)
    for src in [cleaned, _repair_json(cleaned)]:
        if not src:
            continue
        try:
            parsed = json.loads(src)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 2. Markdown code fence (```json ... ```)
    if "```" in cleaned:
        for part in cleaned.split("```"):
            part = part.strip()
            if not part:
                continue
            if part.startswith("json"):
                part = part[4:].strip()
            for src in [part, _repair_json(part)]:
                if not src:
                    continue
                try:
                    parsed = json.loads(src)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass

    # 3. First { ... } block（抢救：动作被正文包裹时截取）
    start = cleaned.find("{")
    if start >= 0:
        end = cleaned.rfind("}")
        if end > start:
            candidate = cleaned[start : end + 1]
            for src in [candidate, _repair_json(candidate)]:
                if not src:
                    continue
                try:
                    parsed = json.loads(src)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
    return None


def parse_action(text: str) -> Action:
    """把一步模型输出解析为 Action。

    - 严格/修复/抢救任一命中且语义合法 → tool/final；
    - `action` 字段非法或缺失 → 有 reply 则按 final（模型自愿收口），否则 degraded；
    - 完全解析不出 → degraded，reply 取文本前段当回答（降级纯 chat）。
    """
    raw = text or ""
    parsed = _extract_json(raw)

    if parsed is None:
        snippet = " ".join(raw.split())[:220]
        return Action(
            kind="degraded",
            reply=_REPLY_FALLBACK.format(snippet=snippet or "（空输出）"),
            raw=raw,
            degraded=True,
        )

    action = str(parsed.get("action", "")).strip().lower()
    thought = str(parsed.get("thought", ""))
    reply = str(parsed.get("reply", ""))
    tool = str(parsed.get("tool", "")).strip()

    if action == "tool" and tool:
        args = parsed.get("args")
        return Action(
            kind="tool",
            thought=thought,
            tool=tool,
            args=args if isinstance(args, dict) else {},
            reply=reply,
            raw=raw,
        )
    if action == "final":
        return Action(kind="final", thought=thought, reply=reply, raw=raw)
    if action == "tool" and not tool:
        # 声称调工具但没给工具名——有 reply 则当收口，否则降级
        if reply:
            return Action(kind="final", thought=thought, reply=reply, raw=raw)
        return Action(
            kind="degraded",
            thought=thought,
            reply=_REPLY_FALLBACK.format(snippet=" ".join(raw.split())[:220]),
            raw=raw,
            degraded=True,
        )
    # action 字段非法：有 reply 当 final（模型自愿收口），否则降级
    if reply:
        return Action(kind="final", thought=thought, reply=reply, raw=raw)
    return Action(
        kind="degraded",
        reply=_REPLY_FALLBACK.format(snippet=" ".join(raw.split())[:220] or "（空输出）"),
        raw=raw,
        degraded=True,
    )
