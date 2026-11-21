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
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# 合法动作动词（协议封闭集）
ACTION_VERBS = ("tool", "final")

# v2 哨兵行（叙述与动作 JSON 的物理分界；流式切分与解析共用同一常量）
ACT_SENTINEL = "===ACT==="

# 无哨兵裸片段形态（2026-11-21 真机实录：模型漏了哨兵，只吐
# `"action": "draft_arc", "tool": "", "args": {}}`）。协议键出现在叙述任意
# 位置都视为协议形状起点——宁可晚点显示，不可把协议原文当正文上屏。
_PROTOCOL_KEY_RE = re.compile(r'"(?:action|tool|args)"\s*:')

_REPLY_FALLBACK = "（我这一步没想明白，先直接回答：\n{snippet}）"

# 混排输出（人话夹协议 JSON）里的 reply 字段抽取——降级时优先给作家看内容，
# 而不是把协议原文糊到对话框（boss 红线 2026-11-16：截图实锤协议 JSON 上屏）
_REPLY_IN_TEXT = re.compile(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"')


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

    kind: str  # "tool" | "final" | "degraded" | "protocol_error"
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


def protocol_shape_at(text: str, start: int = 0) -> int:
    """协议形状片段起点（无哨兵裸动作声明）；-1＝没有。"""
    m = _PROTOCOL_KEY_RE.search(text or "", max(0, start))
    return m.start() if m else -1


def _parse_protocol_fragment(text: str) -> dict | None:
    """抢救无哨兵裸片段：补前花括号／去尾部多余花括号后再走通用提取。

    真机形态 `"action": "draft_arc", "tool": "", "args": {}}` 原样不是 JSON；
    补一个 `{` 即成合法对象。绝不抛。
    """
    frag = (text or "").strip()
    if not frag:
        return None
    bases = [frag] if frag.startswith("{") else ["{" + frag, frag]
    for base in bases:
        trimmed = base.rstrip()
        for cut in range(3):
            cand = trimmed[: len(trimmed) - cut] if cut else trimmed
            if not cand.endswith("}"):
                cand += "}"
            parsed = _extract_json(cand)
            if parsed is not None:
                return parsed
    return None


def _action_from_parsed(
    parsed: dict,
    reply: str,
    raw: str,
    tool_exists: Callable[[str], bool] | None = None,
    protocol_shaped: bool = False,
) -> Action:
    """从解析出的 JSON（v2 尾部或旧版整段）＋已知 reply 组装 Action。

    语义判定：action=tool 需带工具名；final 收口；action 槽误填已注册工具名
    时确定性修复为工具调用；其余非法动作在协议形状路径下判 protocol_error
    （由循环重试），旧版单 JSON 兼容路径保持「有 reply 自愿收口」。
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
    # action 槽误填工具名（真机：{"action":"draft_arc","args":{...}}）——
    # 确定性修复为该工具调用，不再静默收口。
    if action and tool_exists is not None and tool_exists(action):
        args = parsed.get("args")
        if not isinstance(args, dict):
            args = {}
        return Action(
            kind="tool",
            thought=thought,
            tool=action,
            args=args,
            reply=reply,
            raw=raw,
        )
    if protocol_shaped:
        # 协议形状路径（哨兵/裸片段）里的非法动作＝协议错误：交循环重试，
        # 不把「一句承诺」当 final 交付。
        return Action(kind="protocol_error", thought=thought, reply=reply, raw=raw)
    # 旧版单 JSON：action 字段非法／缺失——有 reply 当 final（模型自愿收口），否则降级
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
    - 未流式区出现协议键裸片段（`"action"`／`"tool"`／`"args"`）→ 从该处冻结
      （2026-11-21 真机：模型漏哨兵直吐键值对，不能逐字流给作家）
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
            protocol_shape_at(buf, emitted),
        )
        if i >= 0
    ]
    if candidates:
        freeze = min(candidates)
        return freeze, True
    safe = max(emitted, len(buf) - (len(ACT_SENTINEL) - 1))
    return safe, False


def parse_action(
    text: str, tool_exists: Callable[[str], bool] | None = None
) -> Action:
    """把一步模型输出解析为 Action（v2 哨兵分节优先，旧版单 JSON 兼容）。

    - v2：哨兵行分节——哨兵前＝叙述正文（reply），哨兵后＝动作 JSON；
      尾部 JSON 解析不出且无协议形状 → 按自愿收口 final（正文已完整，动作
      缺省不拦作家内容）；尾部是协议形状但解析不出 → protocol_error。
    - 无哨兵但出现协议键裸片段：切「叙述前缀＋片段」抢救；解析成功走动作
      （含 action 槽误填工具名的修复），失败或无叙述 → protocol_error。
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
            act = _action_from_parsed(
                parsed, reply, raw, tool_exists, protocol_shaped=True
            )
            # 降级组装（action 字段烂了）但有正文 → 正文已完整，按收口交付
            if act.kind == "degraded" and reply:
                return Action(kind="final", reply=reply, raw=raw, degraded=True)
            return act
        stray = tail.strip()
        if protocol_shape_at(stray) >= 0:
            frag = _parse_protocol_fragment(stray)
            if frag is not None:
                act = _action_from_parsed(
                    frag, reply, raw, tool_exists, protocol_shaped=True
                )
                if act.kind != "protocol_error":
                    return act
            return Action(kind="protocol_error", reply=reply, raw=raw)
        if reply:
            # 尾部不是 JSON（哨兵误触发或格式烂）：哨兵后有散文则并入回答不丢内容
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

    # ── 旧版兼容：整段单 JSON（先于形状检测——完整对象不该被切成裸片段）──
    parsed = _extract_json(raw)
    if parsed is not None:
        # 叙述＋JSON 混排：JSON 前的人话要交付，不能只回 reply 字段
        json_start = raw.find("{")
        prefix = raw[:json_start].strip() if json_start > 0 else ""
        prefix = re.sub(r"```[A-Za-z0-9_-]*\s*$", "", prefix).strip()
        act = _action_from_parsed(
            parsed, str(parsed.get("reply", "")) or prefix, raw, tool_exists
        )
        return act

    # ── 无哨兵但出现协议键裸片段（真机 2026-11-21）──────────────────
    shape = protocol_shape_at(raw)
    if shape >= 0:
        head = raw[:shape].rstrip()
        if head.endswith("{"):
            # 键前面是对象开括号——括号归片段，别留在叙述里
            shape = len(head) - 1
        prefix = re.sub(r"```[A-Za-z0-9_-]*\s*$", "", raw[:shape].strip()).strip()
        frag = _parse_protocol_fragment(raw[shape:])
        if frag is not None:
            act = _action_from_parsed(
                frag,
                prefix or str(frag.get("reply", "")),
                raw,
                tool_exists,
                protocol_shaped=True,
            )
            if act.kind != "protocol_error":
                return act
        return Action(kind="protocol_error", reply=prefix, raw=raw)

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
