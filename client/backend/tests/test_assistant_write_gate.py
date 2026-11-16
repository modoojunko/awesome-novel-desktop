"""write_gate 授权梯度测试（c-writing-agent 批B 2.5）。

口径：三档（confirm_each 默认逐次确认 / allow_book 本书放行 / allow_all 全放）；
硬地板清单任何档位必弹卡且 human_only；未知档位回落默认；停车场 register/
wait/resolve/超时/重复 resolve 语义。
"""

import asyncio

import pytest

from assistant.write_gate import (
    HARD_FLOOR_TOOLS,
    PARKING,
    TIER_ALLOW_ALL,
    TIER_ALLOW_BOOK,
    TIER_CONFIRM_EACH,
    GateDecision,
    evaluate,
)


def test_default_tier_needs_user():
    d = evaluate("write_volume_fields", {"ref": "vol-1", "fields": {"summary": "x"}}, tier=TIER_CONFIRM_EACH)
    assert d.allowed is False
    assert d.needs_user is True
    assert d.human_only is False
    assert d.preview["tool"] == "write_volume_fields"
    assert d.preview["args"]["ref"] == "vol-1"


def test_allow_book_auto_allows():
    d = evaluate("write_volume_fields", {"ref": "vol-1", "fields": {"summary": "x"}}, tier=TIER_ALLOW_BOOK)
    assert d.allowed is True
    assert d.needs_user is False


def test_allow_all_auto_allows():
    d = evaluate("write_volume_fields", {"ref": "vol-1"}, tier=TIER_ALLOW_ALL)
    assert d.allowed is True


def test_unknown_tier_falls_back_to_confirm_each():
    d = evaluate("write_volume_fields", {"ref": "vol-1"}, tier="yolo_mode")
    assert d.needs_user is True


def test_hard_floor_always_asks_regardless_of_tier():
    for tool in HARD_FLOOR_TOOLS:
        for tier in (TIER_CONFIRM_EACH, TIER_ALLOW_BOOK, TIER_ALLOW_ALL):
            d = evaluate(tool, {}, tier=tier)
            assert d.needs_user is True, (tool, tier)
            assert d.human_only is True
            assert d.allowed is False


def test_set_permission_tier_is_hard_floor():
    # 「agent 不能给自己授权」：改档位永远弹卡（且结构性不在工具注册表）
    d = evaluate("set_permission_tier", {"tier": "allow_all"}, tier=TIER_ALLOW_ALL)
    assert d.human_only is True


def test_preview_carries_tool_and_args():
    args = {"ref": "vol-2", "fields": {"ending": "海边的告别"}}
    d = evaluate("write_volume_fields", args, tier=TIER_CONFIRM_EACH)
    assert d.preview == {"tool": "write_volume_fields", "args": args}


@pytest.mark.asyncio
async def test_parking_wait_resolved_approved():
    gate_id = PARKING.register()
    async def _approve_later():
        await asyncio.sleep(0.01)
        assert PARKING.resolve(gate_id, "approved") is True

    import asyncio as _a
    task = _a.create_task(_approve_later())
    decision = await PARKING.wait(gate_id, timeout=1.0)
    await task
    assert decision == "approved"
    PARKING.discard(gate_id)


@pytest.mark.asyncio
async def test_parking_resolve_denied():
    gate_id = PARKING.register()

    async def _deny_later():
        await asyncio.sleep(0.01)
        PARKING.resolve(gate_id, "denied")

    import asyncio as _a
    task = _a.create_task(_deny_later())
    decision = await PARKING.wait(gate_id, timeout=1.0)
    await task
    assert decision == "denied"
    PARKING.discard(gate_id)


@pytest.mark.asyncio
async def test_parking_timeout_denies():
    gate_id = PARKING.register()
    decision = await PARKING.wait(gate_id, timeout=0.01)
    assert decision == "denied"
    PARKING.discard(gate_id)


@pytest.mark.asyncio
async def test_parking_unknown_id_denies_and_double_resolve_rejected():
    assert await PARKING.wait("nonexistent", timeout=0.01) == "denied"
    gate_id = PARKING.register()
    assert PARKING.resolve(gate_id, "approved") is True
    # 已决不可改口（先答者赢，openwriter inbox 口径）
    assert PARKING.resolve(gate_id, "denied") is False
    PARKING.discard(gate_id)


def test_gate_decision_defaults():
    d = GateDecision()
    assert d.allowed is False and d.needs_user is False and d.human_only is False
