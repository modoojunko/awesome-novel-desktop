"""draft_arc 入参分层测试（c-agent-action-contract）。

素材与写法约束在工具层分开传、在能力核前拼成分隔块；卡面回显写法约束。
"""

import pytest

from assistant.tools import ToolContext
from assistant.tools_cards import _draft_arc


@pytest.mark.asyncio
async def test_draft_arc_passes_material_and_constraints(monkeypatch):
    seen: dict = {}

    async def fake_arc(novel_id, action, user_id, input_text="", constraints=""):
        seen.update(
            novel_id=novel_id, action=action, user_id=user_id,
            input_text=input_text, constraints=constraints,
        )
        return {"value": {"fullstory": "主线草稿"}}

    monkeypatch.setattr("assistant.caps.settings.arc_ai_action", fake_arc)
    ctx = ToolContext(novel_id="n1", root_path="", user_id="u1")
    res = await _draft_arc(
        ctx,
        action="draft",
        material="穿越+魔兽术士，主角陆沉",
        constraints="真谛前期不点\n冷硬短句",
    )
    assert res.ok is True
    assert seen["input_text"] == "穿越+魔兽术士，主角陆沉"
    assert seen["constraints"] == "真谛前期不点\n冷硬短句"
    value = res.card["payload"]["value"]
    assert value["constraints_used"] == ["真谛前期不点", "冷硬短句"]
    assert "还没写进书里" in res.summary


@pytest.mark.asyncio
async def test_draft_arc_input_alias_still_works(monkeypatch):
    seen: dict = {}

    async def fake_arc(novel_id, action, user_id, input_text="", constraints=""):
        seen.update(input_text=input_text, constraints=constraints)
        return {"value": {"fullstory": "旧调用"}}

    monkeypatch.setattr("assistant.caps.settings.arc_ai_action", fake_arc)
    ctx = ToolContext(novel_id="n1", root_path="", user_id="u1")
    res = await _draft_arc(ctx, action="draft", input="旧素材")
    assert res.ok is True
    assert seen["input_text"] == "旧素材"
    assert seen["constraints"] == ""
    assert "constraints_used" not in res.card["payload"]["value"]


@pytest.mark.asyncio
async def test_draft_arc_check_does_not_echo_constraints(monkeypatch):
    async def fake_arc(novel_id, action, user_id, input_text="", constraints=""):
        return {"value": {"checks": []}}

    monkeypatch.setattr("assistant.caps.settings.arc_ai_action", fake_arc)
    ctx = ToolContext(novel_id="n1", root_path="", user_id="u1")
    res = await _draft_arc(ctx, action="check", constraints="只看冲突")
    assert res.ok is True
    assert "constraints_used" not in res.card["payload"]["value"]
    assert res.card["kind"] == "report"


def test_compose_arc_input_keeps_material_and_constraints_separate():
    from settings.ai_router import _compose_arc_input

    out = _compose_arc_input("故事素材", "不圣母\n算得清账")
    assert out.startswith("故事素材")
    assert "【写法约束（只影响怎么写，不是故事内容）】" in out
    assert "不圣母" in out
    # 只有约束、没有素材时仍给出占位素材段——约束不被当成素材
    only_constraints = _compose_arc_input("", "冷硬短句")
    assert only_constraints.startswith("（无——按已填内容处理）")
    assert "冷硬短句" in only_constraints
    # 无约束时保持旧口径
    assert _compose_arc_input("素材", "") == "素材"
