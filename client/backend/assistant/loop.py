"""AgentLoop——文本协议动作循环（c-writing-agent 批A 1.5）。

单进程内、request-scoped 的 async 生成器，挂在 SSE generator 里（判例
write/router.py `_stream_chapter` 多阶段编排；多模型调用链判例
story/character_agent.py:261）。不进 job_runner——全局单飞槽会被 8 步循环占死。

每步：模型流式产出（thinking 实时透传、正文增量静默攒全量）→ parse_action →
  final：叙述收口；
  tool：emit step_start→执行→step_end（结果摘要）→观察写回转写；
  degraded：纠错重试一次，仍败则降级纯 chat 收口（degraded 记入结果）。

护栏：MAX_STEPS=8 / MAX_TOOL_CALLS=10 / 回合墙钟 600s / 单步 first_content_timeout=90s
（env fail-soft，判例 write/router.py:43-53）。compact：每步前按估算 tokens 判定
（compaction.should_compact），build 失败降级 trim_state，状态经 on_compaction 持久化。
转写即状态：step/tool_result 由调用方逐步落 assistant_messages，崩溃留下完整轨迹。
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ai_client import AIThinkingTimeoutError, AITimeoutError
from assistant import compact as compact_mod
from assistant.actions import parse_action
from assistant.context import build_outbound_window
from assistant.tools import ToolContext, get_tool, run_tool


# env fail-soft（write/router.py:43-53 同款）
def _env_float(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        return float(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        raw = os.environ.get(name)
        return int(raw) if raw else default
    except (TypeError, ValueError):
        return default


MAX_STEPS = _env_int("ASSISTANT_MAX_STEPS", 8)
MAX_TOOL_CALLS = _env_int("ASSISTANT_MAX_TOOL_CALLS", 10)
WALL_CLOCK_SECONDS = _env_float("ASSISTANT_TURN_DEADLINE", 600.0)
STEP_FIRST_CONTENT_TIMEOUT = _env_float("ASSISTANT_STEP_FIRST_CONTENT_TIMEOUT", 90.0)
STEP_MAX_TOKENS = _env_int("ASSISTANT_STEP_MAX_TOKENS", 2048)

_RETRY_NUDGE = (
    "你上一步的输出不是合法的动作 JSON。只输出一个 JSON 对象，不要输出任何其他文字："
    '{"thought": "…", "action": "tool"或"final", "tool": "工具名", "args": {}, "reply": "给作家的话"}'
)

_UNKNOWN_TOOL_FALLBACK = (
    "（我伸手去拿的工具不在我的工具箱里，这步作废。{reply}）"
)


@dataclass
class LoopConfig:
    max_steps: int = MAX_STEPS
    max_tool_calls: int = MAX_TOOL_CALLS
    wall_clock: float = WALL_CLOCK_SECONDS
    step_timeout: float = STEP_FIRST_CONTENT_TIMEOUT
    step_max_tokens: int = STEP_MAX_TOKENS
    model_alias: str = "haiku"  # resolve() 落到本书绑定模型（业务层不传字面模型名）


@dataclass
class LoopResult:
    final_reply: str = ""
    degraded: bool = False
    steps: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    error: str = ""
    # 工具轨迹（TraceFolded 数据源；只含真实发生的工具步）
    trace: list[dict] = field(default_factory=list)


class AgentLoop:
    """一次执行 = 一次 run() 迭代。事件经 async generator 逐个 yield（SSE 序列化在
    router）；终态（转写/compact/用量）落在实例属性上供调用方取用。"""

    def __init__(
        self,
        *,
        client: Any,
        system: str,
        transcript: list[dict[str, str]],
        tool_ctx: ToolContext,
        compaction_state: Any = None,
        config: LoopConfig | None = None,
        # 批A 传 None；批B 接 write_gate——返回 None=放行；返回事件列表（末项含
        # approved 布尔）＝先逐个下发再按批准与否继续/拒绝
        gate_fn: Callable[[str, dict], Awaitable[list[dict] | None]] | None = None,
        # compact 状态持久化回调（session_store.save_compaction_state 适配）
        on_compaction: Callable[[Any], Awaitable[None]] | None = None,
        # 每步用量回调（router 注入 record_usage 适配，短事务）
        on_usage: Callable[[int, int], Awaitable[None]] | None = None,
        context_window: int | None = None,
    ) -> None:
        self.client = client
        self.system = system
        self.transcript = transcript
        self.tool_ctx = tool_ctx
        self.compaction_state = compaction_state
        self.cfg = config or LoopConfig()
        self.gate_fn = gate_fn
        self.on_compaction = on_compaction
        self.on_usage = on_usage
        self.context_window = context_window
        self.result = LoopResult()

    # -- 对外主入口 ------------------------------------------------------------
    async def run(self, user_input: str) -> AsyncIterator[dict[str, Any]]:
        run_id = uuid.uuid4().hex[:12]
        self.result = LoopResult()
        self.transcript.append({"role": "user", "content": user_input})
        yield {"type": "run_start", "runId": run_id}
        started = time.monotonic()
        error_message = ""

        try:
            for step_no in range(1, self.cfg.max_steps + 1):
                if time.monotonic() - started > self.cfg.wall_clock:
                    yield {
                        "type": "narration",
                        "text": "这一轮跑得太久了，我先停在这里——已经产出的内容都在上面。",
                    }
                    break
                self.result.steps = step_no

                # ── compact 判定（估算 tokens ≥ 触发线才做；build 失败降级 trim）──
                await self._maybe_compact()

                # ── 一步：流式调用（thinking 实时透传；正文增量攒全量）─────────
                action, retry_left, stream_error = None, 1, ""
                full_text = ""
                messages, _ = build_outbound_window(
                    self.transcript, compaction_state=self.compaction_state
                )
                for attempt in range(1 + retry_left):
                    full_text = ""
                    try:
                        async for ev in self.client.chat_stream(
                            model=self.cfg.model_alias,
                            system=self.system,
                            messages=messages,
                            max_tokens=self.cfg.step_max_tokens,
                            operation="assistant_step",
                            first_content_timeout=self.cfg.step_timeout,
                        ):
                            if ev.error:
                                stream_error = ev.error
                                break
                            if ev.thinking:
                                yield {"type": "thinking", "text": ev.thinking}
                            if ev.text:
                                full_text += ev.text
                            if ev.is_done:
                                self.result.tokens_in += ev.tokens_in
                                self.result.tokens_out += ev.tokens
                                if self.on_usage is not None:
                                    await self.on_usage(ev.tokens_in, ev.tokens)
                        if stream_error:
                            break
                    except (AITimeoutError, AIThinkingTimeoutError) as e:
                        stream_error = f"这一步想得太久（{e}）"
                        break

                    action = parse_action(full_text)
                    if action.kind == "degraded" and attempt < retry_left:
                        # 纠错重试一次（协议服从度兜底）
                        messages = messages + [
                            {"role": "assistant", "content": full_text},
                            {"role": "user", "content": _RETRY_NUDGE},
                        ]
                        continue
                    break

                if stream_error:
                    error_message = stream_error
                    yield {"type": "error", "message": stream_error}
                    break
                if action is None:  # 理论不可达（parse 恒返回 Action）
                    break

                self.transcript.append(
                    {"role": "assistant", "content": full_text}
                )

                # ── 分派 ────────────────────────────────────────────────────
                if action.kind == "final":
                    self.result.final_reply = action.reply
                    self.result.degraded = False
                    if action.reply:
                        yield {"type": "narration", "text": action.reply}
                    break

                if action.kind == "degraded":
                    self.result.final_reply = action.reply
                    self.result.degraded = True
                    yield {"type": "narration", "text": action.reply}
                    break

                # tool：未知工具按 final 降级（护栏；不假装调过）
                tool = get_tool(action.tool)
                if tool is None:
                    fallback = _UNKNOWN_TOOL_FALLBACK.format(
                        reply=action.reply or "这件事我手头的工具做不了。"
                    )
                    self.result.final_reply = fallback
                    yield {"type": "narration", "text": fallback}
                    break

                if self.result.tool_calls >= self.cfg.max_tool_calls:
                    yield {
                        "type": "narration",
                        "text": "这轮的工具调用次数到顶了，我先把已有的结果交给你。",
                    }
                    break

                # 授权梯度（write_gate）：gate_fn 返回 None＝放行；返回事件列表＝
                # 先逐个下发（授权卡/升级卡），末项 gate_result.approved 决定是否执行。
                # denied 时只给 agent 非诊断性拒绝语（完整理由仅在授权卡上给作家）。
                if self.gate_fn is not None:
                    gate_events = await self.gate_fn(action.tool, action.args)
                    if gate_events:
                        for ge in gate_events:
                            yield ge
                        last = gate_events[-1]
                        if not last.get("approved", False):
                            refusal = last.get("refusal") or "作家没有授权这个操作，我先不做了。"
                            self.transcript.append(
                                {"role": "user", "content": f"[system] {refusal}"}
                            )
                            yield {"type": "narration", "text": refusal}
                            continue

                self.result.tool_calls += 1
                yield {
                    "type": "step_start",
                    "runId": run_id,
                    "stepId": f"{run_id}-{step_no}",
                    "tool": action.tool,
                    "label": action.thought[:80],
                }
                result = await run_tool(self.tool_ctx, action.tool, action.args)
                note = " ".join(result.summary.split())[:220]
                step_end: dict[str, Any] = {
                    "type": "step_end",
                    "runId": run_id,
                    "stepId": f"{run_id}-{step_no}",
                    "tool": action.tool,
                    "resultNote": note,
                }
                # 写类工具携带写入日志（撤销数据源：entity/fields/previous）
                write_log = result.meta.get("write_log")
                if write_log:
                    step_end["writeLog"] = write_log
                yield step_end
                self.result.trace.append(
                    {"tool": action.tool, "ok": result.ok, "note": note}
                )
                # 观察写回转写：assistant 消息带 _tool 元数据（compact 抽取用），
                # tool 结果作为 user 观察行进窗口（文本协议的 ReAct 惯例）
                self.transcript[-1]["_tool"] = {
                    "name": action.tool,
                    "args": action.args,
                    "result": note,
                }
                self.transcript.append(
                    {"role": "user", "content": f"[tool result] {result.summary}"}
                )
            else:
                # 步数耗尽仍未收口：明确收尾话术，已产出卡保留
                if not self.result.final_reply:
                    tail = "这一轮的步数用完了。已完成的部分都在上面，需要继续可以直接吩咐。"
                    self.result.final_reply = tail
                    yield {"type": "narration", "text": tail}
        finally:
            yield {
                "type": "run_end",
                "runId": run_id,
                "steps": self.result.steps,
                "toolCalls": self.result.tool_calls,
                "degraded": self.result.degraded,
                "error": error_message,
            }

    # -- compact ----------------------------------------------------------------
    async def _maybe_compact(self) -> None:
        messages, tokens_est = build_outbound_window(
            self.transcript, compaction_state=self.compaction_state
        )
        if not compact_mod.should_compact(tokens_est, self.context_window):
            return
        prior = self.compaction_state

        async def _complete(system: str, user_text: str) -> str:
            return await self.client.chat(
                model=self.cfg.model_alias,
                system=system,
                messages=[{"role": "user", "content": user_text}],
                max_tokens=compact_mod.SUMMARY_MAX_TOKENS,
                operation="assistant_compact",
            )

        try:
            state = await compact_mod.build_state(
                messages,
                complete_fn=_complete,
                keep_tokens=compact_mod.trigger_tokens(self.context_window),
                prior=prior,
                model_used=self.cfg.model_alias,
            )
            if state is None:
                return
        except Exception:  # 压缩失败降级裁最旧（含上下文溢出 400；BLE001 豁免）
            state = compact_mod.trim_state(messages, prior=prior)
            if state is None:
                return
        self.compaction_state = state
        if self.on_compaction is not None:
            await self.on_compaction(state)
