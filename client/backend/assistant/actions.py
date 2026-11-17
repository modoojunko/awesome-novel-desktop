"""动作协议解析（c-writing-agent 批A 1.4；c-agent-chat-memory 升哨兵分节协议 v2）。

文本协议 v2（全模型逐字流式）：叙述正文先行（逐字流式直出）＋哨兵行收尾＋动作 JSON——
  （叙述正文……）
  ===ACT===
  {"action": "tool"|"final", "tool": str, "args": {}}

哨兵前正文＝给作家看的话（reply 字段退役）；哨兵后 JSON＝动作声明。
兼容链（parse_action 顺序）：v2 哨兵分节 → 旧版单 JSON（{"thought"...,"reply"}，
旧提示词包未升级时模型仍走旧格式）→ 纯文本兜底（无哨兵非 JSON＝模型直接回答，
整段按 final 交付，degraded 标记供遥测）。

三级修复（design §循环）：严格 json → 修复（复用 story/character_agent.py `_repair_json`
手法：中文标点/尾逗号/单引号/字面量）→ 重试一次（由调用方做）。另含 openworker 抢救
语义（providers/openai_provider.py:389-536）：模型把动作当正文输出时的「从文本中抢救
JSON」——代码围栏提取＋首尾括号截取。
未知工具名由调用方按 final 处理（本模块只认语法，不认工具存在性）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# 合法动作动词（协议封闭集）
ACTION_VERBS = ("tool", "final")

# v2 哨兵行（叙述与动作 JSON 的物理分界；流式切分与解析共用同一常量）
ACT_SENTINEL = "===ACT==="

_REPLY_FALLBACK = "（我这一步没想明白，先直接回答：\n{snippet}）"

# 混排输出（人话夹协议 JSON）里的 reply 字段抽取——降级时优先给作家看内容，
# 而不是把协议原文糊到对话框（boss 红线 2026-11-16：截图实锤协议 JSON 上屏）
_REPLY_IN_TEXT = __import__("re").compile(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _human_reply_from_raw(raw: str) -> str | None:
    """从混排文本里抽协议 JSON 的 reply 字段人话；没有则 None。"""
    m = _REPLY_IN_TEXT.search(raw or "")
    if not m:
        return None
    import json as _json

    try:
        v = _json.loads(f'"{m.group(1)}"')
        out = str(v).strip()
        return out or None
    except Exception:  # noqa: BLE001——转义失败按没有处理
        return None


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


def _action_from_parsed(parsed: dict, reply: str, raw: str) -> Action:
    """从解析出的 JSON（v2 尾部或旧版整段）＋已知 reply 组装 Action。

    语义判定与旧版一致：action=tool 需带工具名；final 收口；非法/缺字段
    按「有 reply 自愿收口，否则降级」处理。
    """
    action = str(parsed.get("action", "")).strip().lower()
    thought = str(parsed.get("thought", ""))
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


def stream_slice(buf: str, emitted: int, frozen: bool) -> tuple[int, bool]:
    """哨兵分节流式的纯函数视图：给定当前累计文本，返回 (新的已发位置, 是否冻结)。

    规则（裸 JSON 永不外漏——deepseek 回归钉）：
    - 首字符是 ``{`` 或 `` ` ``（旧版纯 JSON/代码围栏嫌疑）→ 冻结＝整段静默
      攒（批次交付，同旧口径；此时 emitted 必为 0）
    - 未流式区出现哨兵 → 哨兵前全部直通，之后冻结
    - 未流式区出现 ``{`` 或 `` ``` `` → 从该处冻结（叙述后混入 JSON/围栏＝
      旧版抢救形态，其后静默攒）
    - 无任何危险信号 → 发到 len-扣尾（哨兵可能跨 chunk，扣 len(SENTINEL)-1）
    冻结后调用方不再调用；返回位置只前进不回退。
    """
    if frozen:
        return emitted, True
    if (buf or "").lstrip()[:1] in ("{", "`"):
        return 0, True
    candidates = [
        i
        for i in (
            buf.find(ACT_SENTINEL, emitted),
            buf.find("{", emitted),
            buf.find("```", emitted),
        )
        if i >= 0
    ]
    if candidates:
        freeze = min(candidates)
        return freeze, True
    safe = max(emitted, len(buf) - (len(ACT_SENTINEL) - 1))
    return safe, False


def parse_action(text: str) -> Action:
    """把一步模型输出解析为 Action（v2 哨兵分节优先，旧版单 JSON 兼容）。

    - v2：哨兵行分节——哨兵前＝叙述正文（reply），哨兵后＝动作 JSON；
      尾部 JSON 解析不出且有正文 → 按自愿收口 final（正文已完整，动作缺省
      不拦作家内容）；尾部解析不出且无正文 → degraded。
    - 旧版：整段单 JSON（{"thought"...,"reply"}）——提示词包未升级时的兼容路径。
    - 无哨兵且非 JSON：模型直接回答了 → 整段按 final 交付（协议没服从但内容
      完整，degraded 供遥测；不再包「没想明白」外壳——那是把好回答当故障）。
    """
    raw = text or ""

    # ── v2：哨兵分节 ────────────────────────────────────────────────
    if ACT_SENTINEL in raw:
        narration, _, tail = raw.partition(ACT_SENTINEL)
        reply = narration.strip()
        parsed = _extract_json(tail)
        if parsed is not None:
            act = _action_from_parsed(parsed, reply, raw)
            # 降级组装（action 字段烂了）但有正文 → 正文已完整，按收口交付
            if act.kind == "degraded" and reply:
                return Action(kind="final", reply=reply, raw=raw, degraded=True)
            return act
        if reply:
            # 尾部不是 JSON（哨兵误触发或格式烂）：哨兵后有散文则并入回答不丢内容
            stray = tail.strip()
            return Action(
                kind="final",
                reply=f"{reply}\n{stray}" if stray else reply,
                raw=raw,
                degraded=True,
            )
        return Action(
            kind="degraded",
            reply=_REPLY_FALLBACK.format(snippet="（空输出）"),
            raw=raw,
            degraded=True,
        )

    # ── 旧版兼容：整段单 JSON ────────────────────────────────────────
    parsed = _extract_json(raw)
    if parsed is not None:
        act = _action_from_parsed(parsed, str(parsed.get("reply", "")), raw)
        return act

    # ── 纯文本兜底：整段视为 final 回答 ─────────────────────────────
    human = _human_reply_from_raw(raw)
    if human:
        return Action(kind="final", reply=human, raw=raw, degraded=True)
    plain = raw.strip()
    if plain:
        return Action(kind="final", reply=plain, raw=raw, degraded=True)
    return Action(
        kind="degraded",
        reply=_REPLY_FALLBACK.format(snippet="（空输出）"),
        raw=raw,
        degraded=True,
    )
