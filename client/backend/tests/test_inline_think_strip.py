"""c-inline-think-strip — openai 兼容路径内联思考剥离

- MiniMax M2/M3 系把思考以 `<think>…</think>` 内联在 content 交付（官方文档
  明示需手动解析）；交付文本必须零思考段，流式/非流式同构
- 判定从窄：起始判定不变；中段再开完整 `<think>`（M2 交错口径）转思考
  通道（c-thinking-display），非完整标签相似字面仍逐字不动
- 首字守卫口径对齐：内联思考不算首字，思考期守卫持续在计
"""

import asyncio
import types

import pytest

import ai_client as ai_client_module
from ai_client import (
    AIClient,
    AIThinkingTimeoutError,
    _InlineThinkStripper,
    strip_inline_think,
)

FULL = "<think>思考过程可能很长</think>正文开始"


# ── 状态机核心：流式逐 chunk 喂入 ──────────────────────────────────────


def _feed_all(pieces: list[str]) -> str:
    s = _InlineThinkStripper()
    out = "".join(s.feed(p) for p in pieces)
    return out + s.finish()


def test_plain_text_passthrough_verbatim_char_by_char():
    text = "第一段正文，第二句来一点长度。"
    assert _feed_all(list(text)) == text


def test_think_then_prose_char_by_char_zero_leak():
    assert _feed_all(list(FULL)) == "正文开始"


def test_split_matrix_two_chunks_no_leak():
    # 标签在任何位置裂开（覆盖 <think> 与 </think> 全部裂位）都不泄漏
    for i in range(1, len(FULL)):
        assert _feed_all([FULL[:i], FULL[i:]]) == "正文开始", f"split@{i}"


def test_nested_open_tag_inside_think_ignored():
    assert _feed_all(["<think>a<think>b", "</think>", "正文"]) == "正文"


def test_midstream_think_interleave_routed_to_thinking_channel():
    # c-thinking-display 修订（M2 系交错思考官方口径）：闭标签后中段再开
    # `<think>` 转回剥离，思考段走 thinking 列表、不进交付文本
    text = "前文<think>字面</think>尾"
    s = _InlineThinkStripper()
    out = "".join(s.feed(p) for p in [text[:3], text[3:9], text[9:]])
    out += s.finish()
    assert out == "前文尾"
    assert "".join(s.thinking) == "字面"


def test_midstream_near_miss_literal_not_stripped():
    # 判定口径仍从窄：非完整标签的相似字面（如 "<thin"）逐字放行
    text = "前文<thin 字面尾"
    assert _feed_all([text[:3], text[3:9], text[9:]]) == text


def test_short_stream_without_open_tag_delivered_by_finish():
    # 全程攒不满开标签长度：HOLDING 余量由 finish 按正文交付
    assert _feed_all(["ab", "c"]) == "abc"


def test_partial_prefix_then_deviation_flushes_verbatim():
    # "<th" 曾疑似前缀，一旦偏离立即整体放行（普通模型零延迟直通的依据）
    assert _feed_all(["<th", "x普通正文继续"]) == "<thx普通正文继续"
    assert _feed_all(["<", "第一段"]) == "<第一段"


def test_unclosed_think_yields_nothing():
    assert _feed_all(["<think>", "只有思考", "没有正文"]) == ""


def test_stripper_exception_falls_back_to_raw(monkeypatch):
    s = _InlineThinkStripper()
    assert s.feed("<think>思考") == ""  # 已进 STRIPPING
    monkeypatch.setattr(ai_client_module, "_THINK_CLOSE", None)  # find(None) 必炸
    assert s.feed("abc") == "abc"  # 异常兜底：按原始文本交付
    assert s.feed("def") == "def"  # 破损态持续直通
    assert s.finish() == ""


# ── 非流式出口 ─────────────────────────────────────────────────────────


def test_strip_nonstream_prefix_and_verbatim_cases():
    assert strip_inline_think(FULL) == "正文开始"
    assert strip_inline_think("普通正文") == "普通正文"
    assert strip_inline_think("中段<think>字面") == "中段<think>字面"
    assert strip_inline_think("<thin") == "<thin"  # 不完整开标签＝非思考形态
    assert strip_inline_think("<think>只有思考没有正文") == ""
    assert strip_inline_think("") == ""


# ── chat_stream 集成：零泄漏 + 守卫口径 ────────────────────────────────


def _openai_client(chunks) -> AIClient:
    client = AIClient(api_key="sk-test", api_format="openai",
                      base_url="https://example.com/v1")

    async def create(**kwargs):
        async def _gen():
            for c in chunks:
                yield c
        return _gen()

    client._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    return client


def _delta_chunk(text):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content=text))]
    )


def _run(client, **kw):
    async def _go():
        out, err = [], None
        try:
            async for ev in client.chat_stream(
                model="m", system="",
                messages=[{"role": "user", "content": "hi"}], **kw
            ):
                out.append(ev)
        except AIThinkingTimeoutError as e:
            err = e
        return out, err

    return asyncio.new_event_loop().run_until_complete(_go())


def test_stream_think_suppressed_prose_intact():
    client = _openai_client([_delta_chunk(p) for p in
                             ["<thi", "nk>想", "一想</t", "hink>", "第一段"]])
    out, err = _run(client)
    assert err is None
    assert "".join(e.text for e in out if e.text) == "第一段"
    assert any(e.is_done for e in out)


def _stream_trickle_client(chunks, gap):
    client = AIClient(api_key="sk-test", api_format="openai",
                      base_url="https://example.com/v1")

    async def create(**kwargs):
        async def _gen():
            for c in chunks:
                await asyncio.sleep(gap)
                yield c
        return _gen()

    client._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    return client


def test_guard_not_disarmed_by_inline_think():
    # 回归钉（旧口径「首个 delta.content 即撤守卫」被 `<th` 缴械，永不判死）：
    # 内联思考涓流超限必须判死，且判死前零正文事件产出
    chunks = [_delta_chunk(p) for p in
              ("<think>思考一", "思考二", "思考三", "思考四", "思考五")]
    client = _stream_trickle_client(chunks, gap=0.03)
    out, err = _run(client, first_content_timeout=0.05)
    assert err is not None and err.seconds >= 0.05
    assert not any(e.text for e in out)
    assert not any(e.is_done for e in out)


def test_guard_disarmed_by_first_prose_after_think():
    # 思考快、正文在时限内到达即撤守卫：此后正文间隙再长不误杀
    client = AIClient(api_key="sk-test", api_format="openai",
                      base_url="https://example.com/v1")

    async def create(**kwargs):
        async def _gen():
            yield _delta_chunk("<think>快想完")
            yield _delta_chunk("</think>")
            await asyncio.sleep(0.02)  # 时限 0.05 内
            yield _delta_chunk("首字")
            for _ in range(3):
                await asyncio.sleep(0.12)  # 合计远超时限
                yield _delta_chunk(None)
            yield _delta_chunk("尾")

        return _gen()

    client._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    out, err = _run(client, first_content_timeout=0.05)
    assert err is None
    assert "".join(e.text for e in out if e.text) == "首字尾"
    assert any(e.is_done for e in out)


def test_stream_think_spanning_guard_window_then_prose():
    # 思考在时限内收束、正文持续：整链零泄漏（thinking 阶段事件零产出）
    client = _stream_trickle_client(
        [_delta_chunk(p) for p in ["<think>想", "</think>", "正文一", "正文二"]],
        gap=0.0,
    )
    out, err = _run(client, first_content_timeout=5.0)
    assert err is None
    assert "".join(e.text for e in out if e.text) == "正文一正文二"


# ── chat() 非流式集成 ──────────────────────────────────────────────────


def _chat_client(content: str) -> AIClient:
    client = AIClient(api_key="sk-test", api_format="openai",
                      base_url="https://example.com/v1")

    async def create(**kwargs):
        choice = types.SimpleNamespace(message=types.SimpleNamespace(content=content))
        return types.SimpleNamespace(choices=[choice], usage=None)

    client._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    return client


def test_chat_strips_inline_think_prefix():
    async def _go():
        return await _chat_client(FULL).chat(
            model="m", system="", messages=[{"role": "user", "content": "hi"}]
        )

    assert asyncio.new_event_loop().run_until_complete(_go()) == "正文开始"


def test_chat_plain_content_verbatim():
    async def _go():
        return await _chat_client("普通判定结果").chat(
            model="m", system="", messages=[{"role": "user", "content": "hi"}]
        )

    assert asyncio.new_event_loop().run_until_complete(_go()) == "普通判定结果"


@pytest.mark.parametrize("pieces,expected", [
    (["<think>", "想", "</think>", "正文"], "正文"),
    ([FULL], "正文开始"),
    (["普通"], "普通"),
])
def test_feed_all_parametrized(pieces, expected):
    assert _feed_all(pieces) == expected
