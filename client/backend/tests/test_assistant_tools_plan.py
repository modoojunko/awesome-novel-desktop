"""update_plan 工具单元测试（c-agent-action-contract）。"""

import pytest

from assistant.tools import ToolContext
from assistant.tools_plan import _update_plan


def _ctx(plan: dict | None = None) -> ToolContext:
    return ToolContext(
        novel_id="n1", root_path="", user_id="u1",
        scratch={"plan": plan} if plan else {},
    )


@pytest.mark.asyncio
async def test_create_plan_and_update_status():
    ctx = _ctx()
    res = await _update_plan(
        ctx,
        items=[{"title": "主线前提"}, {"title": "主角陆沉"}],
        note="两件",
    )
    assert res.ok is True
    plan = res.meta["plan"]
    assert len(plan["items"]) == 2
    assert [i["status"] for i in plan["items"]] == ["pending", "pending"]
    assert plan["note"] == "两件"

    res2 = await _update_plan(
        ctx, items=[{"id": "主线前提", "title": "主线前提", "status": "done"}]
    )
    plan2 = res2.meta["plan"]
    assert plan2["id"] == plan["id"]
    assert plan2["items"][0]["status"] == "done"
    assert plan2["items"][1]["status"] == "pending"


@pytest.mark.asyncio
async def test_merge_without_status_keeps_existing_status():
    """省略 status 的重命名/补充不得把已做完打回还没动。"""
    ctx = _ctx()
    await _update_plan(ctx, items=[{"title": "主线前提", "status": "done"}])
    res = await _update_plan(
        ctx, items=[{"id": "主线前提", "title": "主线前提（陆沉）"}]
    )
    item = res.meta["plan"]["items"][0]
    assert item["title"] == "主线前提（陆沉）"
    assert item["status"] == "done"


@pytest.mark.asyncio
async def test_replace_starts_new_plan():
    ctx = _ctx()
    first = (await _update_plan(ctx, items=[{"title": "旧事"}])).meta["plan"]
    second = (
        await _update_plan(ctx, items=[{"title": "新事"}], mode="replace")
    ).meta["plan"]
    assert second["id"] != first["id"]
    assert [i["title"] for i in second["items"]] == ["新事"]


@pytest.mark.asyncio
async def test_unknown_status_degrades_to_pending():
    ctx = _ctx()
    res = await _update_plan(ctx, items=[{"title": "主线前提", "status": "running"}])
    assert res.meta["plan"]["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_empty_items_is_error():
    res = await _update_plan(_ctx(), items=[])
    assert res.ok is False
    assert "至少要有一件事" in res.summary


@pytest.mark.asyncio
async def test_merge_without_id_matches_by_title():
    """模型省略 id 时按标题合并，不得把同一条拆成两行。"""
    ctx = _ctx()
    await _update_plan(ctx, items=[{"id": "a", "title": "主线前提", "status": "done"}])
    res = await _update_plan(ctx, items=[{"title": "主线前提", "status": "active"}])
    items = res.meta["plan"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == "a"
    assert items[0]["status"] == "active"
