"""AgentLoop——文本协议动作循环（c-writing-agent 批A 1.5）。

单进程内、request-scoped 的 async 生成器，挂在 SSE generator 里（判例
write/router.py `_stream_chapter` 多阶段编排；多模型调用链判例
story/character_agent.py:261）。不进 job_runner——全局单飞槽会被 8 步循环占死。

每步：模型流式产出（thinking 实时透传、正文增量静默攒全量）→ parse_action →
  final：叙述收口；
  tool：emit step_start→执行→step_end（结果摘要）→观察写回转写；
  degraded：纠错重试一次，仍败则降级纯 chat 收口（degraded 记入结果）。

护栏：回合墙钟（默认 1800s，env 可覆盖）＋作家停止钮——SHALL NOT 设步数/工具次数上限（boss 拍板 2026-11-15，coding agent 口径）；单步 first_content_timeout=90s
（env fail-soft，判例 write/router.py:43-53）。compact：每步前按估算 tokens 判定
（compaction.should_compact），build 失败降级 trim_state，状态经 on_compaction 持久化。
转写即状态：step/tool_result 由调用方逐步落 assistant_messages，崩溃留下完整轨迹。
"""

from __future__ import annotations

import asyncio
import inspect
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ai_client import (
    AIThinkingTimeoutError,
    AITimeoutError,
    api_calls_begin,
    api_calls_drain,
)
from assistant import compact as compact_mod
from assistant.actions import (
    ACT_SENTINEL,
    parse_action,
    protocol_shape_at,
    stream_slice,
)

# 停止/打断的收口话术（openworker 同款语义：已产出保留，随时可以继续）
_CANCEL_NOTICE = "好，先停在这里。已产出的内容都保留着，想继续随时说。"
from assistant.context import build_outbound_window
from assistant.scopes import (
    out_of_scope_guidance,
    tools_for_thread,
)
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


WALL_CLOCK_SECONDS = _env_float("ASSISTANT_TURN_DEADLINE", 1800.0)
STEP_FIRST_CONTENT_TIMEOUT = _env_float("ASSISTANT_STEP_FIRST_CONTENT_TIMEOUT", 90.0)
# 4096：默认开思考后 reasoning 与动作 JSON 共用 max_tokens——2048 可能被思考吃掉
# 导致 JSON 截断（c-agent-thinking-bubbles）。env 仍可收紧。
STEP_MAX_TOKENS = _env_int("ASSISTANT_STEP_MAX_TOKENS", 4096)

_RETRY_NUDGE = (
    "你上一步的输出格式不对。按这个格式重来：先用普通文字说给作家看（可以为空），"
    "然后单独一行输出 ===ACT===，紧跟一个 JSON 对象："
    '{"action": "tool"或"final", "tool": "工具名", "args": {}}。不要输出任何其他东西。'
)

_PROTOCOL_FAIL_REPLY = "（刚才那一步没走通，我先停住。你再说一句，我重来。）"


def _finalize_plan(plan: dict | None, failed: bool) -> dict | None:
    """收口安全网：残留「在做」按收口结果降级，避免计划永远卡在进行中。"""
    if not isinstance(plan, dict):
        return None
    items = [dict(x) for x in (plan.get("items") or []) if isinstance(x, dict)]
    for it in items:
        if it.get("status") == "active":
            it["status"] = "failed" if failed else "pending"
    return {**plan, "items": items}

_UNKNOWN_TOOL_FALLBACK = (
    "（我伸手去拿的工具不在我的工具箱里，这步作废。{reply}）"
)


@dataclass
class LoopConfig:
    wall_clock: float = WALL_CLOCK_SECONDS
    step_timeout: float = STEP_FIRST_CONTENT_TIMEOUT
    step_max_tokens: int = STEP_MAX_TOKENS
    model_alias: str = "haiku"  # resolve() 落到本书绑定模型（业务层不传字面模型名）
    # 思考覆盖（c-agent-thinking-bubbles）：None＝沿用 API 配置；dict＝显式按次
    # {"type": "enabled"} / {"type": "disabled"}（disabled 不搭车；enabled 未带
    # effort 时按模型配置强度补齐，见 c-agent-thinking-effort）
    thinking: dict[str, Any] | None = None
    # DeepSeek 当前日期标记（c-agent-latest-reminder）：非空＝当前外发窗口最后一条
    # user 前插 latest_reminder；不落库不进 compact。空＝不发（其它 vendor）。
    latest_reminder: str = ""


@dataclass
class LoopResult:
    final_reply: str = ""
    degraded: bool = False
    # 协同取消（c-agent-chat-memory 批8 停止/打断）：作家停止/新消息打断/断连
    # 触发 cancel_event 后，循环在最近检查点收口——已产出保留，收口话术见 _CANCEL_NOTICE
    interrupted: bool = False
    steps: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    error: str = ""
    # 工具轨迹（TraceFolded 数据源；只含真实发生的工具步）
    trace: list[dict] = field(default_factory=list)
    # 任务计划快照（c-agent-action-contract；update_plan 产物，随 run_end 下发）
    plan: dict | None = None


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
        # 批A 传 None；批B 接 write_gate——两种契约（向后兼容）：
        #   1) 协程返回 None=放行；返回事件列表（末项含 approved 布尔）＝先逐个
        #      下发再按批准与否继续/拒绝；
        #   2) 异步生成器逐个 yield 事件——yield 即下发（授权卡必须在停车等待
        #      批复**之前**到达作家眼前，否则默认档每写必确认会空等 300s 超时）。
        gate_fn: (
            Callable[[str, dict], Awaitable[list[dict] | None]]
            | Callable[[str, dict], AsyncIterator[dict[str, Any]]]
            | None
        ) = None,
        # compact 状态持久化回调（session_store.save_compaction_state 适配）
        on_compaction: Callable[[Any], Awaitable[None]] | None = None,
        # 每步用量回调（router 注入 record_usage 适配，短事务）
        on_usage: Callable[[int, int], Awaitable[None]] | None = None,
        # 协同取消（停止/打断/断连）：置位后循环在最近检查点收口（步界＋模型流
        # chunk 级＋gate 停车等待）——不硬杀任务，工具与落库链照常收尾
        cancel_event: asyncio.Event | None = None,
        context_window: int | None = None,
        # c-agent-harness tasks 4.1："" = 自动路由（client.supports_native_tools，
        # env ASSISTANT_HARNESS 可强制）；"native"/"text" 显式钉死。文本协议分支
        # 为降级路径（能力矩阵外供应商），native 为主路径（spike 全过）
        harness: str = "",
    ) -> None:
        self.client = client
        # native 工具历史回传能力（c-agent-native-tool-history）：DeepSeek 带 tools
        # 时历史 reasoning_content 必须完整回传；其它 vendor 不附加未知字段
        _echo = getattr(client, "requires_reasoning_echo", None)
        self._reasoning_echo = bool(_echo()) if callable(_echo) else False
        self.system = system
        self.transcript = transcript
        self.tool_ctx = tool_ctx
        self.compaction_state = compaction_state
        self.cancel_event = cancel_event
        self.cfg = config or LoopConfig()
        self.gate_fn = gate_fn
        self.on_compaction = on_compaction
        self.on_usage = on_usage
        self.context_window = context_window
        # 显式参数 > env 强制 > 能力矩阵自动（env 判定在 loop 层做一份——
        # 假客户端没有 supports_native_tools 也要能被 env 抬进 native 测试）
        env = (os.environ.get("ASSISTANT_HARNESS") or "").strip().lower()
        if harness:
            self.harness = harness
        elif env in ("native", "text"):
            self.harness = env
        else:
            supports = getattr(client, "supports_native_tools", None)
            self.harness = "native" if (supports and supports()) else "text"
        self.result = LoopResult()

    # -- 对外主入口 ------------------------------------------------------------
    def _cancelled(self) -> bool:
        return bool(self.cancel_event is not None and self.cancel_event.is_set())

    def _cancel_notice_event(self) -> dict[str, Any]:
        """停止/打断收口：话术＋标记（已产出保留，镜像/落库照常走完）"""
        self.result.interrupted = True
        return {"type": "narration", "text": _CANCEL_NOTICE}

    async def _interruptible(self, stream: AsyncIterator[Any]) -> AsyncIterator[Any]:
        """模型流的可打断包装：等 chunk 与等取消赛跑（150ms 轮询）——慢 TTFB/长
        思考等待中点停止也即时生效（openworker 停止语义；裸 async-for 会被首
        chunk 前的等待卡死，检查点根本没机会跑——e2e 慢桩实锤）。"""
        get_next = asyncio.ensure_future(stream.__anext__())
        while True:
            if self._cancelled():
                get_next.cancel()
                return
            done, _ = await asyncio.wait({get_next}, timeout=0.15)
            if done:
                try:
                    yield get_next.result()
                except StopAsyncIteration:
                    return
                get_next = asyncio.ensure_future(stream.__anext__())

    async def run(
        self,
        user_input: str,
        prime: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """prime＝chips 结构化触发（c-tool-flow 批2）：{tool, args} 首步确定性
        执行（域校验/授权/去重照走），结果回填后模型接管——作家意图不再依赖
        固定话术被模型猜中。None＝纯 agentic（自由输入）。"""
        run_id = uuid.uuid4().hex[:12]
        self.result = LoopResult()
        self.transcript.append({"role": "user", "content": user_input})
        yield {"type": "run_start", "runId": run_id}
        started = time.monotonic()
        error_message = ""
        # 消费端断开（aclose/GeneratorExit）标记：关闭期间 finally 不得再 yield
        # ——否则 RuntimeError("async generator ignored GeneratorExit")
        closed = False

        prime_tool = str((prime or {}).get("tool") or "").strip()
        prime_args = (prime or {}).get("args") if isinstance((prime or {}).get("args"), dict) else {}
        if prime_tool:
            async for ev in self._prime_step(run_id, started, prime_tool, prime_args or {}):
                yield ev

        inner = self._run_native(run_id, started) if self.harness == "native" else self._run_text(run_id, started)
        try:
            async for ev in inner:
                yield ev
        except (GeneratorExit, asyncio.CancelledError):
            # 消费端关闭/任务取消同口径：关闭态不发 run_end（finally-yield 撞取消
            # 会把生成器挂进「ignored GeneratorExit」险境）；落库由调用方收尾
            closed = True
            raise
        finally:
            # 消费端断开时显式关停内层生成器（其体内无 finally-yield，干净关闭）
            await inner.aclose()
            if not closed:
                final_plan = _finalize_plan(
                    self.result.plan, bool(error_message or self.result.error)
                )
                if final_plan is not None:
                    self.result.plan = final_plan
                incomplete = (
                    sum(
                        1
                        for it in (final_plan or {}).get("items", [])
                        if it.get("status") != "done"
                    )
                    if final_plan
                    else 0
                )
                payload = {
                    "type": "run_end",
                    "runId": run_id,
                    "steps": self.result.steps,
                    "toolCalls": self.result.tool_calls,
                    "degraded": self.result.degraded,
                    "error": error_message,
                    "planIncomplete": incomplete,
                }
                if final_plan is not None:
                    payload["plan"] = final_plan
                yield payload

    # -- 首步结构化触发（c-tool-flow 批2）──────────────────────────────────

    async def _prime_step(
        self, run_id: str, started: float, tool_name: str, args: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """chips tool_hint 首步确定性执行：域校验/授权/去重守卫全程照走；
        结果按 harness 形态回填转写后模型接管（第二步起为普通模型回合）。"""
        if not self._wall_clock_left(started):
            yield self._wall_clock_message()
            return
        self.result.steps = 1

        from assistant.scopes import out_of_scope_guidance

        allowed = self._allowed_tools()
        if allowed is not None and tool_name not in allowed:
            guidance = out_of_scope_guidance(
                tool_name, str(getattr(self.tool_ctx, "thread", "") or "")
            )
            self.transcript.append({"role": "user", "content": f"[system] {guidance}"})
            yield {"type": "narration", "text": guidance}
            return
        if get_tool(tool_name) is None:
            unavailable = f"工具 {tool_name} 不可用。"
            self.transcript.append({"role": "user", "content": f"[system] {unavailable}"})
            yield {"type": "narration", "text": unavailable}
            return

        denied_refusal = None
        step_result = None
        async for kind, payload in self._emit_step(run_id, 1, tool_name, "", args):
            if kind == "event":
                yield payload
            elif kind == "denied":
                denied_refusal = payload
            elif kind == "result":
                step_result = payload

        summary = (step_result.summary if step_result else "") or "（没有产出。）"
        if denied_refusal:
            summary = f"[denied] {denied_refusal}"
        if self.harness == "native":
            self.transcript.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": f"{run_id}-prime",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": "{}"},
                        }
                    ],
                }
            )
            self.transcript.append(
                {"role": "tool", "tool_call_id": f"{run_id}-prime", "content": summary}
            )
        else:
            self.transcript.append(
                {
                    "role": "assistant",
                    "content": "",
                    "_tool": {
                        "name": tool_name,
                        "args": args,
                        "result": " ".join(summary.split())[:220],
                    },
                }
            )
            self.transcript.append({"role": "user", "content": f"[tool result] {summary}"})
        self.transcript.append(
            {
                "role": "user",
                "content": "[system] 首步已按作家的点选执行完成——基于以上结果直接回应作家。",
            }
        )

    # -- 共用小件（两模式同构，tasks 4.3）───────────────────────────────────

    def _duplicate_call(self, tool: str, args: dict) -> bool:
        """连续同工具同参数去重（openworker 重复调用劝退口径）：模型自触发
        的原地重跑（抽卡连抽等）→ 劝退并回喂；作家明示重抽由新一轮承载。"""
        import json as _json

        try:
            key = _json.dumps({"t": tool, "a": args or {}}, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            key = f"{tool}:{sorted(args or {})}"
        dup = key == getattr(self, "_last_call_key", None)
        self._last_call_key = key
        return dup

    def _allowed_tools(self) -> set[str] | None:
        """本线程可声明的工具集；None＝不收窄（thread 空＝旧调用/测试/兜底路径）。

        页签独立流程（c-agent-fleet）：真实请求恒带 thread——按域收窄声明与执行。"""
        ctx = self.tool_ctx
        thread = str(getattr(ctx, "thread", "") or "") if ctx is not None else ""
        if not thread:
            return None
        return tools_for_thread(thread)

    def _wall_clock_left(self, started: float) -> bool:
        return time.monotonic() - started <= self.cfg.wall_clock

    def _wall_clock_message(self) -> dict[str, Any]:
        return {
            "type": "narration",
            "text": "这一轮跑得太久了，我先停在这里——已经产出的内容都在上面。",
        }

    async def _emit_step(
        self,
        run_id: str,
        step_no: int,
        tool_name: str,
        label: str,
        args: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """工具步共用件：授权梯度→step_start→执行→step_end→artifact→轨迹。
        返回 (result, denied_refusal)；denied_refusal 非 None 表示被拒（调用方回喂）。"""
        # 授权梯度（write_gate）：gate_fn 返回 None＝放行；返回事件列表＝先逐个
        # 下发（授权卡/升级卡），末项 gate_result.approved 决定是否执行。denied 时
        # 只给 agent 非诊断性拒绝语（完整理由仅在授权卡上给作家）。
        if self.gate_fn is not None:
            gate = self.gate_fn(tool_name, args)
            last: dict[str, Any] | None = None
            if inspect.isasyncgen(gate):
                # 流式闸（授权卡先到再停车）：生成器 yield 的事件立即下发——
                # 批复端收到卡才有得批；生成器内部停在批复等待上，末项
                # gate_result 定去留（2026-11-21 实锤：旧契约等批复才返回事件，
                # 授权卡永远晚于停车结果，客户端只见「进行中」空等 300s）。
                async for ge in gate:
                    last = ge
                    yield ("event", ge)
            else:
                gate_events = await gate
                if gate_events:
                    for ge in gate_events:
                        yield ("event", ge)
                    last = gate_events[-1]
            if last is not None and not last.get("approved", False):
                yield ("denied", last.get("refusal") or "作家没有授权这个操作，我先不做了。")
                return
        if self._cancelled():
            # 停止/打断在 gate 等待后到达：不执行工具，直接收口（步界检查点接力）
            yield ("denied", "已停止——这一步没有执行。")
            return
        self.result.tool_calls += 1
        from assistant.scopes import domain_of_thread

        # 域标签取当前线程域（check_consistency 等多域归属工具按工具首属域会标错页签）
        domain = domain_of_thread(str(getattr(self.tool_ctx, "thread", "") or ""))
        step_start: dict[str, Any] = {
            "type": "step_start",
            "runId": run_id,
            "stepId": f"{run_id}-{step_no}",
            "tool": tool_name,
            "label": label[:80],
        }
        if domain:
            step_start["domain"] = domain
        yield ("event", step_start)
        # API 调用归集（c-writing-agent 反馈流：本步内工具核心的模型调用全部可见
        # ——coding agent 口径，boss 拍板 2026-11-15）
        api_calls_begin()
        result = await run_tool(self.tool_ctx, tool_name, args)
        api_calls = api_calls_drain()
        note = " ".join(result.summary.split())[:220]
        step_end: dict[str, Any] = {
            "type": "step_end",
            "runId": run_id,
            "stepId": f"{run_id}-{step_no}",
            "tool": tool_name,
            "resultNote": note,
            "ok": result.ok,  # effect 收集口径：只对成功的写步触发前端刷新（router._consume）
            "args": args,  # effect target 来源（c-agent-nav：effect_target_from 指入参键）
        }
        from assistant.scopes import domain_of_thread

        domain = domain_of_thread(str(getattr(self.tool_ctx, "thread", "") or ""))
        if domain:
            step_end["domain"] = domain
        if api_calls:
            step_end["apiCalls"] = api_calls
        write_log = result.meta.get("write_log")
        if write_log:
            step_end["writeLog"] = write_log
        yield ("event", step_end)
        if result.card:
            yield ("event", {
                "type": "artifact",
                "runId": run_id,
                "cardId": f"{run_id}-{step_no}",
                "kind": str(result.card.get("kind", "text")),
                "payload": result.card.get("payload"),
            })
        self.result.trace.append({"tool": tool_name, "ok": result.ok, "note": note})
        yield ("result", result)

    # -- 文本协议分支（tasks 4.4＝原循环原样迁移；解析器＋抢救函数保留）───────

    async def _run_text(self, run_id: str, started: float) -> AsyncIterator[dict[str, Any]]:
        step_no = 0
        while True:
            if not self._wall_clock_left(started):
                yield self._wall_clock_message()
                break
            if self._cancelled():
                yield self._cancel_notice_event()
                break
            step_no += 1
            self.result.steps = step_no

            # ── compact 判定（估算 tokens ≥ 触发线才做；失败重试一次降 trim）──
            notice = await self._maybe_compact()
            if notice:
                yield {"type": "narration", "text": notice}

            # ── 一步：流式调用（thinking 实时透传；正文增量攒全量）─────────
            action, retry_left, stream_error = None, 1, ""
            full_text = ""
            messages, _ = build_outbound_window(
                self.transcript,
                compaction_state=self.compaction_state,
                reminder=self.cfg.latest_reminder,
            )
            cancelled_hit = False
            for attempt in range(1 + retry_left):
                full_text = ""
                streamed_upto, frozen = 0, False
                try:
                    async for ev in self.client.chat_stream(
                        model=self.cfg.model_alias,
                        system=self.system,
                        messages=messages,
                        max_tokens=self.cfg.step_max_tokens,
                        operation="assistant_step",
                        first_content_timeout=self.cfg.step_timeout,
                        **({"thinking": self.cfg.thinking} if self.cfg.thinking else {}),
                    ):
                        if ev.error:
                            stream_error = ev.error
                            break
                        if self._cancelled():
                            # chunk 级取消（逐字流式下停止即时生效——不等整段）
                            cancelled_hit = True
                            break
                        if ev.thinking:
                            yield {"type": "thinking", "text": ev.thinking}
                        if ev.text:
                            full_text += ev.text
                            # 哨兵分节流式（c-agent-chat-memory 批2）：叙述正文字节
                            # 直通 delta；哨兵/JSON 嫌疑处冻结静默攒——裸 JSON 永不
                            # 外漏（deepseek 回归钉）。切分规则收在 stream_slice 纯函数。
                            if not frozen:
                                old_upto = streamed_upto
                                streamed_upto, frozen = stream_slice(
                                    full_text, streamed_upto, frozen
                                )
                                if streamed_upto > old_upto:
                                    yield {
                                        "type": "narration_delta",
                                        "text": full_text[old_upto:streamed_upto],
                                    }
                        if ev.is_done:
                            self.result.tokens_in += ev.tokens_in
                            self.result.tokens_out += ev.tokens
                            if self.on_usage is not None:
                                await self.on_usage(ev.tokens_in, ev.tokens)
                    if cancelled_hit:
                        break
                except (AITimeoutError, AIThinkingTimeoutError) as e:
                    stream_error = f"这一步想得太久（{e}）"
                    break
                except Exception as e:  # noqa: BLE001——模型连接失败等也以 error 事件收尾，
                    # SHALL NOT 静默断流（c-prose-stream-silent-hang 同口径）
                    stream_error = f"模型调用失败：{e}"
                    break

                action = parse_action(
                    full_text, tool_exists=lambda n: get_tool(n) is not None
                )
                if action.kind in ("degraded", "protocol_error") and attempt < retry_left:
                    # 纠错重试一次（协议服从度兜底）：回喂清理后的文本，
                    # SHALL NOT 回声坏片段（2026-11-21 真机：坏片段写回历史后
                    # 模型下一轮开始为自己的坏输出道歉重跑）。
                    clean = (
                        action.reply.strip()
                        if action.kind == "protocol_error"
                        else full_text
                    )
                    messages = messages + [
                        {
                            "role": "assistant",
                            "content": clean or "（上一步只有格式坏掉的片段，没有可读正文）",
                        },
                        {"role": "user", "content": _RETRY_NUDGE},
                    ]
                    continue
                break

            # 停止/打断收口（while 层）：attempt 内 break 跳到这里——已产出保留
            if cancelled_hit:
                self.result.interrupted = True
                yield {"type": "narration", "text": _CANCEL_NOTICE}
                break

            if stream_error:
                yield {"type": "error", "message": stream_error}
                break
            if action is None:  # 理论不可达（parse 恒返回 Action）
                break

            # 坏协议原文不入转写：protocol_error 与无哨兵裸片段都只留清理后的人话
            if action.kind == "protocol_error" or (
                ACT_SENTINEL not in full_text
                and protocol_shape_at(full_text) >= 0
            ):
                stored_text = action.reply.strip()
            else:
                stored_text = full_text
            self.transcript.append(
                {
                    "role": "assistant",
                    "content": stored_text or "（这一步没有产出可读正文。）",
                }
            )

            # ── 分派 ────────────────────────────────────────────────────
            if action.kind == "protocol_error":
                # 协议坏且重试已用尽：只交付清理后的人话；坏片段不上屏、不落历史
                reply = action.reply.strip()
                self.result.final_reply = reply or _PROTOCOL_FAIL_REPLY
                self.result.degraded = True
                if reply:
                    if 0 < streamed_upto < len(reply):
                        yield {
                            "type": "narration_delta",
                            "text": reply[streamed_upto:],
                        }
                    yield {"type": "narration", "text": reply}
                else:
                    yield {"type": "narration", "text": _PROTOCOL_FAIL_REPLY}
                break

            if action.kind == "final":
                self.result.final_reply = action.reply
                # degraded 遥测随动作透传（v2 纯文本兜底＝final 但协议未服从）
                self.result.degraded = bool(action.degraded)
                if action.reply:
                    # 扣尾/冻结窗补发（c-agent-narration-tail-loss）：stream_slice
                    # 的哨兵扣尾窗与 {/``` 冻结区不进 delta，而 dock 对整段
                    # narration 见 seenDelta 一律去重 ⇒ 显示缺尾（实锤：会话存档
                    # 完整、界面缺「你说走哪条，我跟着动。」尾 8 字）。已流过部分
                    # delta 时把未流尾巴补发；零流式的批次交付不动（整段照发，
                    # dock 无 seenDelta 照常追加——旧契约不变）。
                    if 0 < streamed_upto < len(action.reply):
                        yield {
                            "type": "narration_delta",
                            "text": action.reply[streamed_upto:],
                        }
                    yield {"type": "narration", "text": action.reply}
                break

            if action.kind == "degraded":
                self.result.final_reply = action.reply
                self.result.degraded = True
                if action.reply:
                    # 同上：已流过 delta 时补发未流尾巴（degraded 兜底同口径）
                    if 0 < streamed_upto < len(action.reply):
                        yield {
                            "type": "narration_delta",
                            "text": action.reply[streamed_upto:],
                        }
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

            # 工具步叙述入账（c-agent-narration-persist）：正文此前只走
            # narration_delta（流式直出），不补整段 narration——reply_parts 收不到，
            # 整轮收尾/中断定稿时这段文字丢失（2026-11-21 真机实锤：截图有、
            # 会话存档无）。dock 端按前缀对账，不会与已流 delta 翻倍。
            # 只取已流的干净前缀（stream_slice 冻结在哨兵/JSON 嫌疑处）——SHALL NOT
            # 用 action.reply 整段，否则混排输出的裸协议 JSON 会借这条路上屏。
            # 未知工具分支不走此径（上面的 fallback 已含 reply，避免双份）。
            visible = full_text[:streamed_upto].strip()
            if visible:
                yield {"type": "narration", "text": visible}

            # 域外工具＝页签独立流程（c-agent-fleet）：不执行，引导切对应页签
            allowed = self._allowed_tools()
            if allowed is not None and action.tool not in allowed:
                guidance = out_of_scope_guidance(action.tool, str(getattr(self.tool_ctx, "thread", "") or ""))
                self.result.final_reply = guidance
                yield {"type": "narration", "text": guidance}
                break

            # 连续同工具同参数＝模型原地重跑（抽卡连抽类）——劝退回喂不执行
            if self._duplicate_call(action.tool, action.args):
                notice = "这一步和上一步完全相同（同工具同参数），产物已经交付——直接收口，或换一个做法。"
                self.transcript.append({"role": "user", "content": f"[system] {notice}"})
                yield {"type": "narration", "text": notice}
                continue

            # 授权梯度＋执行（_emit_step 共用件）
            denied_refusal = None
            step_result = None
            async for kind, payload in self._emit_step(
                run_id, step_no, action.tool, action.thought, action.args
            ):
                if kind == "event":
                    yield payload
                elif kind == "denied":
                    denied_refusal = payload
                elif kind == "result":
                    step_result = payload
            if denied_refusal:
                self.transcript.append(
                    {"role": "user", "content": f"[system] {denied_refusal}"}
                )
                yield {"type": "narration", "text": denied_refusal}
                continue

            # 计划快照随工具步实时下发（c-agent-action-contract）：只改会话状态
            if step_result is not None and isinstance(step_result.meta, dict):
                plan = step_result.meta.get("plan")
                if isinstance(plan, dict):
                    self.result.plan = plan
                    yield {"type": "plan", "plan": plan, "runId": run_id}

            # 观察写回转写：assistant 消息带 _tool 元数据（compact 抽取用），
            # tool 结果作为 user 观察行进窗口（文本协议的 ReAct 惯例）。
            # apiCalls 只进 step_end 事件（前端轨迹卡）——SHALL NOT 回填模型
            # 历史（openwriter _display 侧车同款：反馈流元数据 agent 不可见）
            note = " ".join((step_result.summary if step_result else "").split())[:220]
            self.transcript[-1]["_tool"] = {
                "name": action.tool,
                "args": action.args,
                "result": note,
            }
            self.transcript.append(
                {"role": "user", "content": f"[tool result] {step_result.summary if step_result else ''}"}
            )

    # -- compact ----------------------------------------------------------------
    async def _maybe_compact(self) -> str:
        """自动压缩（openworker engine._compact_now 同口径）：keep 只留触发线的
        KEEP_RECENT_FRACTION 份；summarizer 失败重试一次再降级裁剪。返回作家可见
        回执（视图没变＝空串，不空发）。native harness 下按原生形态装配（带
        tool_calls/tool 行）——compact 的抽取/渲染本就认识这些形态。"""
        messages, tokens_est = build_outbound_window(
            self.transcript, compaction_state=self.compaction_state,
            native=(self.harness == "native"),
        )
        if not compact_mod.should_compact(tokens_est, self.context_window):
            return ""
        prior = self.compaction_state
        keep = int(
            compact_mod.KEEP_RECENT_FRACTION
            * compact_mod.trigger_tokens(self.context_window)
        )

        async def _complete(system: str, user_text: str) -> str:
            return await self.client.chat(
                model=self.cfg.model_alias,
                system=system,
                messages=[{"role": "user", "content": user_text}],
                max_tokens=compact_mod.SUMMARY_MAX_TOKENS,
                operation="assistant_compact",
            )

        async def _build():
            return await compact_mod.build_state(
                messages,
                complete_fn=_complete,
                keep_tokens=keep,
                prior=prior,
                model_used=self.cfg.model_alias,
            )

        state = None
        failed = False
        for _attempt in range(2):  # 首试＋无条件单次重试（openworker 同款）
            try:
                state = await _build()
                failed = False
                break
            except Exception:  # 含上下文溢出 400；BLE001 豁免
                failed = True
        if state is not None:
            self.compaction_state = state
            if self.on_compaction is not None:
                await self.on_compaction(state)
            return "上下文快满了，我把更早的对话收进了摘要——细节需要时会自动重读。"
        if failed:
            state = compact_mod.trim_state(messages, prior=prior)
            if state is None:
                return ""
            self.compaction_state = state
            if self.on_compaction is not None:
                await self.on_compaction(state)
            return "摘要没压成，我把最旧的轮次裁掉了——需要更早的细节会自动重读。"
        return ""

    # -- native 分支（c-agent-harness tasks 4.2：结构化 tool_calls → 授权 →
    #    执行 → tool 结果回填 → 循环至模型自然收口）──────────────────────────

    async def _run_native(self, run_id: str, started: float) -> AsyncIterator[dict[str, Any]]:
        from assistant.tools import TOOL_REGISTRY

        allowed = self._allowed_tools()
        schemas = [
            t.openai_spec()
            for t in TOOL_REGISTRY
            if allowed is None or t.name in allowed
        ]
        step_no = 0
        while True:
            if not self._wall_clock_left(started):
                yield self._wall_clock_message()
                break
            if self._cancelled():
                yield self._cancel_notice_event()
                break
            step_no += 1
            self.result.steps = step_no

            # compact 判定（native 口径估算：外发窗口带 tool 形态，build_state
            # 的 _render_span/_iter_tool_calls 原生认识 tool_calls/tool 行）
            notice = await self._maybe_compact()
            if notice:
                yield {"type": "narration", "text": notice}

            messages, _ = build_outbound_window(
                self.transcript,
                compaction_state=self.compaction_state,
                native=True,
                reminder=self.cfg.latest_reminder,
            )
            full_text = ""
            step_reasoning = ""
            native_calls: list[dict] = []
            stream_error = ""
            cancelled_hit = False
            try:
                async for ev in self._interruptible(
                    self.client.chat_stream(
                        model=self.cfg.model_alias,
                        system=self.system,
                        messages=messages,
                        max_tokens=self.cfg.step_max_tokens,
                        operation="assistant_step",
                        first_content_timeout=self.cfg.step_timeout,
                        tools=schemas,
                        **({"thinking": self.cfg.thinking} if self.cfg.thinking else {}),
                    )
                ):
                    if ev.error:
                        stream_error = ev.error
                        break
                    if self._cancelled():
                        cancelled_hit = True
                        break
                    if ev.thinking:
                        step_reasoning += ev.thinking
                        yield {"type": "thinking", "text": ev.thinking}
                    if ev.text:
                        full_text += ev.text
                    if ev.tool_calls:
                        native_calls = ev.tool_calls
                    if ev.is_done:
                        self.result.tokens_in += ev.tokens_in
                        self.result.tokens_out += ev.tokens
                        if self.on_usage is not None:
                            await self.on_usage(ev.tokens_in, ev.tokens)
            except (AITimeoutError, AIThinkingTimeoutError) as e:
                stream_error = f"这一步想得太久（{e}）"
            except Exception as e:  # noqa: BLE001——同 text 分支口径
                stream_error = f"模型调用失败：{e}"
            if stream_error:
                yield {"type": "error", "message": stream_error}
                break
            if cancelled_hit:
                yield self._cancel_notice_event()
                break

            if not native_calls:
                # 无工具调用＝模型自然收口（openai 协议 stop 语义）
                final_row: dict[str, Any] = {"role": "assistant", "content": full_text}
                if self._reasoning_echo and step_reasoning:
                    final_row["reasoning_content"] = step_reasoning
                self.transcript.append(final_row)
                self.result.final_reply = full_text
                self.result.degraded = False
                if full_text:
                    yield {"type": "narration", "text": full_text}
                break

            # 有工具调用：先挂 assistant(tool_calls) 行（arguments 原样字符串——
            # openai 校验链要求回喂形态与请求形态一致；坏 JSON 由解析兜底处理）
            call_rows = []
            for idx, tc in enumerate(native_calls):
                call_rows.append(
                    {
                        "id": tc.get("id") or f"{run_id}-tc{idx}",
                        "type": "function",
                        "function": {
                            "name": tc.get("name") or "",
                            "arguments": tc.get("args_raw") or "{}",
                        },
                    }
                )
            self.transcript.append(
                {
                    "role": "assistant",
                    "content": full_text or "",
                    "tool_calls": call_rows,
                    **(
                        {"reasoning_content": step_reasoning}
                        if self._reasoning_echo and step_reasoning
                        else {}
                    ),
                }
            )
            # 随行的正文叙述照常透出（coding agent 口径：边说边做）
            if full_text:
                yield {"type": "narration", "text": full_text}

            for idx, tc in enumerate(native_calls):
                if not self._wall_clock_left(started):
                    # 孤儿 tool_calls 防线：未执行的剩余调用补 tool-error 结果行
                    # （openai 校验链拒孤儿——openworker _interrupted_tool 同款语义）
                    for j in range(idx, len(native_calls)):
                        self.transcript.append(
                            {"role": "tool", "tool_call_id": call_rows[j]["id"],
                             "content": "已停止——这一步没有执行。"}
                        )
                    yield self._wall_clock_message()
                    return
                if self._cancelled():
                    # 停止/打断：剩余调用补 tool-error 结果行，历史不留孤儿
                    self.result.interrupted = True
                    for j in range(idx, len(native_calls)):
                        self.transcript.append(
                            {"role": "tool", "tool_call_id": call_rows[j]["id"],
                             "content": "已停止——这一步没有执行。"}
                        )
                    yield {"type": "narration", "text": _CANCEL_NOTICE}
                    return
                call_id = call_rows[idx]["id"]
                name = tc.get("name") or ""
                args = tc.get("arguments")
                if not isinstance(args, dict):
                    # 坏 JSON 抢救失败按空参执行（宁空勿假——文本协议同口径）
                    args = {}

                if self._duplicate_call(name, args):
                    self.transcript.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": "这一步和上一步完全相同（同工具同参数），产物已经交付——直接收口，或换一个做法。",
                        }
                    )
                    continue

                tool = get_tool(name)
                if tool is None or (allowed is not None and name not in allowed):
                    # native 口径：tool 结果行回喂让模型自纠。未知工具与域外工具
                    # 分话术：域外＝页签独立流程引导（c-agent-fleet）
                    guidance = (
                        out_of_scope_guidance(name, str(getattr(self.tool_ctx, "thread", "") or ""))
                        if tool is not None
                        else (
                            f"工具 {name} 不在工具箱里——从可用工具清单里选一个"
                            "真实存在的再试，或直接回复作家。"
                        )
                    )
                    self.transcript.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": guidance,
                        }
                    )
                    continue

                denied_refusal = None
                step_result = None
                async for kind, payload in self._emit_step(
                    run_id, step_no, name, "", args
                ):
                    if kind == "event":
                        yield payload
                    elif kind == "denied":
                        denied_refusal = payload
                    elif kind == "result":
                        step_result = payload
                if denied_refusal:
                    # 拒绝也按 tool 结果行回喂（协议完整性），叙述照常给作家
                    self.transcript.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": f"[denied] {denied_refusal}",
                        }
                    )
                    yield {"type": "narration", "text": denied_refusal}
                    continue

                # 计划快照随工具步实时下发（与 text 分支同构）
                if step_result is not None and isinstance(step_result.meta, dict):
                    plan = step_result.meta.get("plan")
                    if isinstance(plan, dict):
                        self.result.plan = plan
                        yield {"type": "plan", "plan": plan, "runId": run_id}

                # tool 结果行回填（openai 协议形态；摘要全文进窗口供模型观察——
                # native 转写以 tool_calls/tool 行为元数据，compact 原生认识）
                self.transcript.append(
                    {"role": "tool", "tool_call_id": call_id, "content": step_result.summary if step_result else ""}
                )
                step_no += 1
                self.result.steps = step_no
