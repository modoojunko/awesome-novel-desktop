"""决策档案钉（c-agent-decision-archive）。

- 档案契约：append-only 全量留痕（永不截断）、坏行容忍、删书级联清文件；
- 分层注入三态：全在预算（无索引无尾注）／部分索引／尾注计数守恒；
- recall_decisions 工具：命中/空档/limit/裁剪；
- 存量迁移：DB 播种 → 对拍 → 幂等。

注入层「半年前的决定」主场景：老决策（日期 2026-05）掉出全文预算后索引仍在，
agent 凭索引调 recall_decisions 拉全文——SHALL NOT 静默丢弃。
"""

import json

import pytest

from assistant import memory as mem
from assistant.tools import ToolContext, run_tool


def _row(text: str, date: str, reason: str = "") -> mem.DecisionRow:
    return mem.DecisionRow(id=f"id-{text[:8]}-{date}", decision=text, reason=reason, created_at=date)


def test_archive_append_and_list_order():
    """追加全量留痕；list 按时间新→旧。"""
    import asyncio

    async def t():
        await mem.add_decision("bookArc", "主角不能飞", "世界观代价体系")
        await mem.add_decision("bookArc", "文风冷硬", "跟作家口味")
        rows = await mem.list_decisions("bookArc")
        assert [r.decision for r in rows] == ["文风冷硬", "主角不能飞"]
        assert rows[0].created_at >= rows[1].created_at

    asyncio.run(t())


def test_archive_tolerates_broken_lines():
    """崩溃残迹容忍：坏行/半行跳过不炸。"""
    path = mem._decisions_path("bookBroken")
    path.parent.mkdir(parents=True, exist_ok=True)
    good = '{"id": "g1", "decision": "有效决定", "reason": "", "created_at": "2026-11-18 10:00:00.0"}'
    path.write_text(good + "\n{broken half lin\n\n", encoding="utf-8")
    rows = mem._read_decisions("bookBroken")
    assert [r.decision for r in rows] == ["有效决定"]


def test_delete_book_memory_removes_archive_file():
    """删书级联：决策档案文件一并移除（零孤儿）。"""
    import asyncio

    async def t():
        await mem.add_decision("bookDead", "注定被删的决定")
        path = mem._decisions_path("bookDead")
        assert path.exists()
        from db import async_session

        async with async_session() as db:
            await mem.delete_book_memory(db, "bookDead")
        assert not path.exists()

    asyncio.run(t())


def _render_decisions(texts_dates: list[tuple[str, str]]) -> str:
    rows = [_row(t, d) for t, d in texts_dates]
    rows.sort(key=lambda r: (r.created_at, r.id), reverse=True)  # 新→旧（list_decisions 同口径）
    return mem.render_memory_section([], rows)


def test_layered_injection_all_within_budget():
    """全在预算：全部全文，无索引无尾注。"""
    pairs = [(f"短决定{i}", f"2026-11-18 10:00:{i:02d}.0") for i in range(5)]
    sec = _render_decisions(pairs)
    assert "索引" not in sec and "另有" not in sec
    assert "主角" not in sec
    assert all(f"短决定{i}" in sec for i in range(5))


def test_layered_injection_old_decision_drops_to_index():
    """半年前场景：老决策掉出全文预算 → 索引行仍在（日期＋一句话）。"""
    # 新决策铺满全文预算（量级从常量自适应推导——行宽调了测试也不脆）
    full_cap = mem.DECISION_CHAR_BUDGET // 16 + 5
    pairs = [(f"新决定{i}——长内容占注入预算", f"2026-11-18 10:00:{i:02d}.0") for i in range(full_cap)]
    pairs.append(("半年前拍板主角不能飞", "2026-05-03 09:00:00.0"))
    sec = _render_decisions(pairs)
    assert "更早的决定（索引）" in sec
    assert "[2026-05-03] 半年前拍板主角不能飞" in sec  # 索引保住老决定


def test_layered_injection_tail_note_counts_rest():
    """索引也装不下 → 尾注计数（守恒：全文＋索引＋尾注 = 总数）。"""
    import re

    total = mem.DECISION_CHAR_BUDGET // 16 + mem.DECISION_INDEX_BUDGET // 20 + 12
    pairs = [(f"决定{i}——长内容占注入预算", f"2026-11-18 10:{i // 60:02d}:{i % 60:02d}.0") for i in range(total)]
    sec = _render_decisions(pairs)
    full = len([l for l in sec.splitlines() if l.startswith("- ") and not l.startswith("- [20")])
    indexed = len([l for l in sec.splitlines() if l.startswith("- [20")])
    m = re.search(r"另有 (\d+) 条更早的决定在档", sec)
    assert m, sec[-400:]
    tail_n = int(m.group(1))
    assert full + indexed + tail_n == total  # 守恒——一条都不丢


def test_layered_injection_memory_section_untouched():
    """写作规矩段（800 字层）零变化：规矩照常全文注入。"""
    from models.assistant import BookAgentMemory

    m = BookAgentMemory(id="mem1", novel_id="n", content="短句口语禁 AI 腔", created_at="2026-11-18 10:00:00")
    sec = mem.render_memory_section([m], [])
    assert "短句口语禁 AI 腔" in sec and "写作规矩" in sec


@pytest.mark.asyncio
async def test_recall_decisions_tool_hit_miss_and_trim():
    ctx = ToolContext(novel_id="n_recall", root_path="/tmp", user_id="u", page="ch:og")
    await mem.add_decision("n_recall", "半年前拍板：血族主角不能飞", "世界观代价体系")
    await mem.add_decision("n_recall", "文风冷硬不圣母", "作家口味")
    r = await run_tool(ctx, "recall_decisions", {"query": "飞"})
    assert r.ok and "血族主角不能飞" in r.summary and "文风冷硬" not in r.summary
    r2 = await run_tool(ctx, "recall_decisions", {})
    assert r2.ok and "共 2 条" in r2.summary
    r_multi = await run_tool(ctx, "recall_decisions", {"query": "血族 飞"})  # 分词 AND：两词都命中
    assert r_multi.ok and "血族主角不能飞" in r_multi.summary
    r_none = await run_tool(ctx, "recall_decisions", {"query": "血族 不存在的词"})
    assert r_none.ok and "没有含" in r_none.summary  # AND 语义：一词不中即不命中
    r3 = await run_tool(ctx, "recall_decisions", {"query": "不存在的词"})
    assert r3.ok and "没有含" in r3.summary


@pytest.mark.asyncio
async def test_db_migration_exports_and_idempotent():
    """迁移钉：DB 播种 → 对拍 → 幂等重跑 → 注入可见。"""
    from pathlib import Path

    from config import DATA_ROOT
    from db import async_session
    from models.assistant import BookDecision

    sid = "mig-dec-0001"
    async with async_session() as db:
        db.add(BookDecision(
            id=sid, novel_id="n_migdec", decision="半年前拍板：主角不能飞",
            reason="代价体系", created_at="2026-05-03 09:00:00.0",
        ))
        await db.commit()

    await mem.migrate_book_decisions()
    path = Path(DATA_ROOT) / "decisions" / "n_migdec.jsonl"
    assert path.exists()
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(l["id"] == sid and l["decision"] == "半年前拍板：主角不能飞" for l in lines)
    # 幂等：重跑不重复
    out2 = await mem.migrate_book_decisions()
    lines2 = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines2) == len(lines)
    assert out2["skipped"] >= 1
    # 注入可见（迁移的老决策以全文或索引出现）
    rows = await mem.list_decisions("n_migdec")
    sec = mem.render_memory_section([], rows)
    assert "主角不能飞" in sec
