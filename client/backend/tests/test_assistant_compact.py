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


# -- 跨轮重映射（review 判例 2026-11-14）---------------------------------------
# boundary_index 是「轮内转写」的裸索引；下一轮转写由 assistant_messages 重建
# （原始动作 JSON 与 [tool result] 行不落库），构成不同——必须重映射，否则
# apply_to_outbound 切在任意语义点或越界静默失效。


def test_remap_boundary_lands_after_anchor_reply():
    # 轮内转写：动作 JSON 行 + 观察行（不落库的形态）
    in_run = [
        _msg("user", "帮我铺这一卷"),
        _msg("assistant", '{"thought": "干", "action": "tool", "tool": "read_outline"}'),
        _msg("user", "[tool result] 第1卷…"),
        _msg("assistant", '{"action": "final", "reply": "铺好了。"}'),
        _msg("user", "再铺一版"),
        _msg("assistant", "第二版铺好了。"),
    ]
    state = c.CompactionState(
        boundary_index=4,
        summary_text="作家要铺卷纲。",
        working_state="",
        user_messages=["帮我铺这一卷"],
    )
    # 下一轮重建转写：只有 user + 最终叙述行（落库投影）
    rebuilt = [
        _msg("user", "帮我铺这一卷"),
        _msg("assistant", "铺好了。"),
        _msg("user", "再铺一版"),
    ]
    remapped = c.remap_boundary(state, rebuilt)
    assert remapped is not None
    # 锚 user（「帮我铺这一卷」）在 0 → 边界挪到其后回复之后＝2
    assert remapped.boundary_index == 2
    outbound = c.apply_to_outbound(rebuilt, remapped)
    assert "compacted-history" in outbound[0]["content"]
    assert outbound[-1] == rebuilt[-1]


def test_remap_boundary_current_turn_user_anchor():
    # 锚＝当前轮的用户消息（compaction 发生在轮内，user 已进 span）：
    # 边界挪到其回复之后，本轮叙述保守保留在 verbatim 尾
    rebuilt = [_msg("user", "帮我铺这一卷"), _msg("assistant", "铺好了。")]
    state = c.CompactionState(
        boundary_index=9,
        summary_text="摘要",
        working_state="",
        user_messages=["帮我铺这一卷"],
    )
    remapped = c.remap_boundary(state, rebuilt)
    assert remapped is not None
    assert remapped.boundary_index == len(rebuilt)


def test_remap_boundary_unmatchable_state_discarded():
    rebuilt = [_msg("user", "新会话的问题"), _msg("assistant", "答")]
    state = c.CompactionState(
        boundary_index=5,
        summary_text="摘要",
        working_state="",
        user_messages=["已被重置清掉的旧消息"],
    )
    assert c.remap_boundary(state, rebuilt) is None


def test_remap_boundary_none_passthrough():
    assert c.remap_boundary(None, [_msg("user", "q")]) is None
    state = c.CompactionState(boundary_index=1, summary_text="", working_state="", user_messages=[])
    assert c.remap_boundary(state, [_msg("user", "q")]) is None
