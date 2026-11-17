"""书级记忆与项目决策测试（c-agent-chat-memory 批3/批4）。

CRUD（增改删/空内容拒绝/跨书隔离）、render_memory_section 容量护栏
（空书空段/决策倒序超限截断/理由拼接）、删书级联零孤儿。
"""

import pytest

from assistant import memory as memory_mod
from db import async_session


@pytest.mark.asyncio
async def test_memory_upsert_update_delete_cycle():
    async with async_session() as db:
        row = await memory_mod.upsert_memory(db, "n_mem", "本书全程第一人称")
        assert row.content == "本书全程第一人称"
        # 改（带 id）
        row2 = await memory_mod.upsert_memory(db, "n_mem", "改：第一人称＋章末钩子", memory_id=row.id)
        assert row2.id == row.id
        assert "章末钩子" in row2.content
        # 删
        assert await memory_mod.delete_memory(db, "n_mem", row.id) is True
        assert await memory_mod.delete_memory(db, "n_mem", row.id) is False


@pytest.mark.asyncio
async def test_memory_empty_content_rejected():
    async with async_session() as db:
        with pytest.raises(ValueError):
            await memory_mod.upsert_memory(db, "n_mem", "   ")


@pytest.mark.asyncio
async def test_memory_scoped_by_novel():
    async with async_session() as db:
        await memory_mod.upsert_memory(db, "n_a", "A 书避免血腥")
        rows_b = await memory_mod.list_memories(db, "n_b")
        assert rows_b == []
        rows_a = await memory_mod.list_memories(db, "n_a")
        assert len(rows_a) == 1 and "血腥" in rows_a[0].content


@pytest.mark.asyncio
async def test_decision_append_and_recency_order():
    async with async_session() as db:
        d1 = await memory_mod.add_decision(db, "n_dec", "否决主角黑化", reason="调子不符")
        d2 = await memory_mod.add_decision(db, "n_dec", "定了海边收尾")
        assert d1.reason == "调子不符" and d2.decision == "定了海边收尾"
        rows = await memory_mod.list_decisions(db, "n_dec")
        # 倒序：最近在前
        assert rows[0].decision == "定了海边收尾" and rows[-1].decision == "否决主角黑化"


@pytest.mark.asyncio
async def test_decision_empty_rejected():
    async with async_session() as db:
        with pytest.raises(ValueError):
            await memory_mod.add_decision(db, "n_dec", "")


def test_render_section_empty_returns_empty_string():
    assert memory_mod.render_memory_section([], []) == ""


def test_render_section_capacity_keeps_recent_decisions():
    from models.assistant import BookAgentMemory, BookDecision

    memories = [
        BookAgentMemory(id=f"m{i}", novel_id="n", content="规矩" + "长" * 30, updated_at="")
        for i in range(40)
    ]
    decisions = [
        BookDecision(id=f"d{i}", novel_id="n", decision=f"决定{i}" + "述" * 30, created_at=f"t{i}")
        for i in range(39, -1, -1)  # 新→旧（list_decisions 同序约定）
    ]
    text = memory_mod.render_memory_section(memories, decisions)
    assert text.startswith("── 这本书我们定下的规矩与决定 ──")
    # 预算护栏：记忆段不超预算太多（逐条保留）；决策只留最近若干条
    assert "决定0" not in text  # 最旧的被截断
    assert "决定39" in text  # 最新的保留


def test_render_section_decision_reason_appended():
    from models.assistant import BookDecision

    d = BookDecision(id="d1", novel_id="n", decision="否决黑化", reason="调子不符", created_at="")
    text = memory_mod.render_memory_section([], [d])
    assert "否决黑化" in text and "调子不符" in text


@pytest.mark.asyncio
async def test_load_section_roundtrip():
    async with async_session() as db:
        await memory_mod.upsert_memory(db, "n_load", "结尾留钩子")
        out = await memory_mod.load_book_memory_section(db, "n_load")
        assert "结尾留钩子" in out
        # 空书空段（前缀缓存友好）
        assert await memory_mod.load_book_memory_section(db, "n_none") == ""


@pytest.mark.asyncio
async def test_delete_book_memory_cascades_zero_orphans():
    async with async_session() as db:
        for i in range(3):
            await memory_mod.upsert_memory(db, "n_del", f"规矩{i}")
        await memory_mod.add_decision(db, "n_del", "决定A")
        await memory_mod.add_decision(db, "n_del", "决定B")
        await memory_mod.delete_book_memory(db, "n_del")
        assert await memory_mod.list_memories(db, "n_del") == []
        assert await memory_mod.list_decisions(db, "n_del") == []


# ── 记忆工具（批4.5：run_tool 全链＋免授权结构＋透明话术） ──────────────


def _ctx():
    from assistant.tools import ToolContext

    return ToolContext(novel_id="n_tools", root_path="", user_id="u1", thread="ch:og")


@pytest.mark.asyncio
async def test_memory_tools_cycle_via_run_tool():
    from assistant.tools import run_tool

    ctx = _ctx()
    r1 = await run_tool(ctx, "remember_book_memory", {"content": "本书避免血腥描写"})
    assert r1.ok and "记下了" in r1.summary
    r2 = await run_tool(ctx, "recall_book_memory", {})
    assert r2.ok and "避免血腥" in r2.summary
    # 拿 id → 改 → 删
    from db import async_session

    async with async_session() as db:
        rows = await memory_mod.list_memories(db, "n_tools")
    mid = rows[0].id
    r3 = await run_tool(ctx, "remember_book_memory", {"content": "改口径：不写实施暴力", "memory_id": mid})
    assert r3.ok and "更新了" in r3.summary
    r4 = await run_tool(ctx, "forget_book_memory", {"memory_id": mid})
    assert r4.ok and "不再记着" in r4.summary
    r5 = await run_tool(ctx, "forget_book_memory", {"memory_id": "nonexistent"})
    assert not r5.ok


@pytest.mark.asyncio
async def test_decision_tool_appends_and_reports():
    from assistant.tools import run_tool

    ctx = _ctx()
    r = await run_tool(ctx, "remember_decision", {"decision": "否决主角黑化路线", "reason": "与全书调子冲突"})
    assert r.ok and "记下了" in r.summary and "调子冲突" in r.summary
    r2 = await run_tool(ctx, "recall_book_memory", {})
    assert "否决主角黑化路线" in r2.summary


@pytest.mark.asyncio
async def test_memory_tools_are_gate_free_by_kind():
    """免授权＝结构性（kind=read 不进 gate；write_gate 三档不涉记忆工具）。"""
    from assistant.tools import get_tool

    for name in (
        "recall_book_memory",
        "remember_book_memory",
        "forget_book_memory",
        "remember_decision",
    ):
        t = get_tool(name)
        assert t is not None and t.kind == "read"


@pytest.mark.asyncio
async def test_memory_tools_in_all_domains():
    from assistant.scopes import tools_for_thread

    names = {
        "recall_book_memory",
        "remember_book_memory",
        "forget_book_memory",
        "remember_decision",
    }
    for thread in ("ch:og", "ch:prose", "set:chars", "vol", "preview"):
        assert names <= tools_for_thread(thread), thread
