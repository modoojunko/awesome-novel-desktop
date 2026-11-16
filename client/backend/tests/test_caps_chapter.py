"""章纲域能力核（c-tool-flow 批1）契约测试。

- 工具层不得直调路由 handler——必须经 caps 能力核（端点与工具单源）
- caps 把核的 HTTPException 归一为 CapabilityError（人话消息）
- 业务语义入参直传（抽卡排除名单→CastDrawBody.exclude）
"""

import inspect

import pytest

from assistant.caps import chapter as caps_chapter
from assistant.tools import TOOL_REGISTRY


def test_tools_do_not_call_handlers_directly():
    """能力核层守卫：工具层出现 handler 直调即 fail（改走 caps 能力核）。"""
    handlers = ("plot_simulate", "cast_ai_draw", "cast_ai_review")
    for t in TOOL_REGISTRY:
        if t.fn is None:
            continue
        src = inspect.getsource(t.fn)
        for h in handlers:
            assert h not in src, f"{t.name} 直调了 handler {h}——改走 caps 能力核"


@pytest.mark.asyncio
async def test_draw_passes_exclude_names(monkeypatch):
    """抽卡排除名单直传：exclude_names 进 CastDrawBody.exclude。"""
    captured: dict = {}

    class _Body:
        def __init__(self, **kw):
            captured.update(kw)

    async def fake_draw(project_id, ref, body, user, _a, _b, db):
        return {"cards": [{"name": "新卡"}], "note": ""}

    monkeypatch.setattr("chapters.ai_cast.CastDrawBody", _Body)
    monkeypatch.setattr("chapters.ai_cast.cast_ai_draw", fake_draw)

    await caps_chapter.draw_plot_proposals(
        "n-1", "vol-1-ch-7", "u-1", exclude_names=["旧卡甲", "旧卡乙"], extra="偏悬疑"
    )
    excl = captured.get("exclude") or []
    assert [e.name for e in excl] == ["旧卡甲", "旧卡乙"]
    assert captured.get("extra") == "偏悬疑"


@pytest.mark.asyncio
async def test_review_uses_empty_snapshot_body(monkeypatch):
    """盘点核收空快照 body（面板表单适配私有在核内）。"""
    captured: dict = {}

    class _Body:
        def __init__(self, **kw):
            captured.update(kw)

    async def fake_review(project_id, ref, body, user, _a, _b, db):
        return {"rows": [], "quota": {}, "hints": [], "warnings": []}

    monkeypatch.setattr("chapters.ai_cast.CastReviewBody", _Body)
    monkeypatch.setattr("chapters.ai_cast.cast_ai_review", fake_review)

    await caps_chapter.review_chapter_cast("n-1", "vol-1-ch-7", "u-1")
    assert isinstance(captured.get("_sentinel", None), type(None)) or True
    assert captured == {}  # 空快照＝无字段覆盖


@pytest.mark.asyncio
async def test_http_exception_normalized_to_capability_error(monkeypatch):
    """核的 HTTPException 归一为 CapabilityError（人话消息透传）。"""
    from fastapi import HTTPException

    async def failing_draw(project_id, ref, body, user, _a, _b, db):
        raise HTTPException(502, "AI 这次没出卡，可再试一次")

    monkeypatch.setattr("chapters.ai_cast.CastDrawBody", lambda **kw: type("B", (), {})())
    monkeypatch.setattr("chapters.ai_cast.cast_ai_draw", failing_draw)

    with pytest.raises(caps_chapter.CapabilityError) as ei:
        await caps_chapter.draw_plot_proposals("n-1", "vol-1-ch-7", "u-1")
    assert "没出卡" in ei.value.message
