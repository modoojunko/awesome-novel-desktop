"""draft_character 两态评估测试（c-writing-agent 访谈→确认→建卡）。

工具侧必需要素口径：identity/relation/function 缺一即追问清单（agent 继续访谈，
不落任何卡）；齐了才出草案确认卡（confirmed=False，作家点确认后前端才调建卡 API）。
"""

import pytest

from assistant.tools import ToolContext
from assistant.tools_settings import DRAFT_CHARACTER_TOOL, _draft_character


def _ctx() -> ToolContext:
    return ToolContext(
        novel_id="n-1",
        root_path="/tmp/n-1",
        user_id="u-1",
        page="workbench",
    )


def _patch_cast(monkeypatch: pytest.MonkeyPatch, names: list[str]) -> None:
    from assistant import tools as tools_mod
    from assistant.tools_settings import ToolResult

    async def _fake_read_settings(ctx, area="cast"):
        summary = "\n".join(f"- {n}（配角）：测试条目" for n in names) or "（名册为空）"
        return ToolResult(ok=True, summary=summary)

    monkeypatch.setattr(tools_mod, "_read_settings", _fake_read_settings)


@pytest.mark.asyncio
async def test_missing_required_returns_intake_not_card(monkeypatch):
    _patch_cast(monkeypatch, ["林野"])
    res = await _draft_character(_ctx(), {"name": "周伯", "gender_age": "男，六十来岁"})
    assert res.ok is True
    assert res.card is None
    intake = res.meta["char_intake"]
    assert intake["missing"] == ["identity", "relation", "function"]
    assert intake["collected"] == {"name": "周伯", "gender_age": "男，六十来岁"}
    assert "逐项问作家" in res.summary


@pytest.mark.asyncio
async def test_partial_fields_collected_kept(monkeypatch):
    _patch_cast(monkeypatch, [])
    res = await _draft_character(_ctx(), {"identity": "账房先生"})
    intake = res.meta["char_intake"]
    assert intake["missing"] == ["relation", "function"]
    assert intake["collected"] == {"identity": "账房先生"}


@pytest.mark.asyncio
async def test_complete_fields_emit_confirm_card(monkeypatch):
    _patch_cast(monkeypatch, ["林野"])
    res = await _draft_character(
        _ctx(),
        {
            "name": "周伯",
            "gender_age": "男，六十来岁",
            "identity": "补给站账房先生",
            "relation": "与林野是旧识",
            "function": "握有撤离名单线索",
            "personality": "谨慎怕事",
        },
    )
    assert res.ok is True
    assert res.card is not None
    payload = res.card["payload"]
    assert payload["confirmed"] is False
    assert payload["collide_check"] == "ok"
    draft = payload["character_draft"]
    assert draft["name"] == "周伯"
    assert draft["identity"] == "补给站账房先生"
    assert draft["function"] == "握有撤离名单线索"
    assert "推确认卡给作家" in res.summary


@pytest.mark.asyncio
async def test_name_collision_rejected(monkeypatch):
    _patch_cast(monkeypatch, ["周伯"])
    res = await _draft_character(
        _ctx(),
        {
            "name": "周伯",
            "identity": "账房",
            "relation": "无",
            "function": "无",
        },
    )
    assert res.ok is False
    assert res.card is None
    assert "撞" in res.summary


@pytest.mark.asyncio
async def test_blank_fields_dropped(monkeypatch):
    _patch_cast(monkeypatch, [])
    res = await _draft_character(
        _ctx(),
        {"name": "  ", "identity": "账房先生", "relation": "", "function": "线索"},
    )
    intake = res.meta["char_intake"]
    # 空白 name/空 relation 都不进 collected；relation 仍算缺
    assert "name" not in intake["collected"]
    assert "relation" in intake["missing"]


def test_tool_registration_low_risk():
    # 只出草案卡不落库 → low（可并行）；建卡执行在作家确认之后
    assert DRAFT_CHARACTER_TOOL.name == "draft_character"
    assert DRAFT_CHARACTER_TOOL.risk_level == "low"
    assert DRAFT_CHARACTER_TOOL.kind == "card"
