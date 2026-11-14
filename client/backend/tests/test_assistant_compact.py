"""compact 移植测试（c-writing-agent 批A 1.7）。

口径：触发阈值 = min(0.8×窗口, cap)；build_state 用注入的 complete_fn；
失败降级 trim_state；外发视图替换头部、不动持久化转写。
"""

import pytest

from assistant import compact as c


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def test_should_compact_threshold():
    # 128k 窗口 × 0.8 = 102400；cap 250k 不生效
    assert c.trigger_tokens(128_000) == 102_400
    # 1M 窗口被 cap 压到 250k（百万上下文模型提前压缩）
    assert c.trigger_tokens(1_000_000) == 250_000
    assert c.should_compact(102_400, 128_000) is True
    assert c.should_compact(102_399, 128_000) is False


def test_pick_boundary_prefers_user_turns():
    messages = [_msg("user", "开头问题")]
    for i in range(30):
        messages += [_msg("assistant", "回答" + str(i) * 200), _msg("user", "追问" + str(i) * 200)]
    boundary = c.pick_boundary(messages, keep_tokens=400)
    assert boundary is not None
    assert messages[boundary]["role"] == "user"


def test_trim_state_advances_boundary():
    messages = [_msg("user", "q0")]
    for i in range(10):
        messages += [_msg("assistant", "a" * 100), _msg("user", "u" * 100)]
    state = c.trim_state(messages)
    assert state is not None
    assert state.trimmed is True
    assert state.boundary_index > 1
    assert state.user_messages  # 用户消息机械保留


@pytest.mark.asyncio
async def test_build_state_with_fake_summarizer():
    messages = [_msg("user", "第一问：这本书的主线是什么？")]
    for i in range(20):
        messages += [
            _msg("assistant", f"第{i}轮工具步：读了第{i}章"),
            _msg("user", f"第{i}轮追问，关于第{i}章"),
        ]

    async def fake_complete(system: str, user_text: str) -> str:
        return "## Primary request and intent\n作家在追问各章内容。\n## All user messages\n- 第一问\n- 后续追问"

    state = await c.build_state(
        messages, complete_fn=fake_complete, keep_tokens=300
    )
    assert state is not None
    assert state.summary_text.startswith("## Primary request and intent")
    assert state.working_state == ""  # 无工具记录
    assert any("第一问" in u for u in state.user_messages)
    block = c.compacted_block(state)
    assert "<compacted-history>" in block
    # 外发视图：压缩块顶到无 system 头时的 outbound[0]，尾部原样
    outbound = c.apply_to_outbound(messages, state)
    assert outbound[0]["role"] == "user"
    assert "compacted-history" in outbound[0]["content"]
    assert outbound[-1] == messages[-1]


@pytest.mark.asyncio
async def test_build_state_nothing_to_compact():
    messages = [_msg("user", "唯一一问"), _msg("assistant", "唯一一答")]
    calls = 0

    async def fake_complete(system: str, user_text: str) -> str:
        nonlocal calls
        calls += 1
        return "摘要"

    state = await c.build_state(messages, complete_fn=fake_complete, keep_tokens=4000)
    assert state is None
    assert calls == 0


def test_context_overflow_detection():
    assert c.is_context_overflow(RuntimeError("This model's maximum context length is 8192 tokens"))
    assert c.is_context_overflow(RuntimeError("prompt is too long: 300000 tokens > 200000"))
    assert not c.is_context_overflow(RuntimeError("connection reset"))
