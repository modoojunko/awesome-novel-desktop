"""身份定义与作家画像测试（c-writing-agent 批C）。

identity：必需字段缺失 fail loud（spec §身份定义缺失拒载）；包缺失回落内置兜底稿。
profile：分区合并（dict 深合并/list 追加去重）、敏感先问提示、暂停开关停更、
定期总结（阈值触发/失败静默/已总结事件打标）。
"""

import json

import pytest

from assistant import identity as identity_mod
from assistant import profile as profile_mod
from db import async_session

# ── identity ─────────────────────────────────────────────────────────────────


def test_identity_validate_missing_fields_fail_loud():
    with pytest.raises(RuntimeError):
        identity_mod.validate_identity({"name": "写作助手", "persona": "…"})
    with pytest.raises(TypeError):
        identity_mod.validate_identity("不是对象")


def test_identity_validate_full_passes():
    raw = {
        "name": "写作助手",
        "persona": "搭档",
        "voice_rules": "短句",
        "fence_rules": "只做书内",
    }
    out = identity_mod.validate_identity(raw)
    assert out == raw


def test_builtin_identity_has_all_fields():
    out = identity_mod.validate_identity(dict(identity_mod.DEFAULT_IDENTITY))
    assert "没能力做" in out["fence_rules"]  # 能力围栏是身份的一部分（拍板④）


def test_identity_system_section_stable_order():
    ident = identity_mod.validate_identity(dict(identity_mod.DEFAULT_IDENTITY))
    text = identity_mod.identity_system_section(ident)
    assert text.index("你是「写作助手」") < text.index("说话规矩") < text.index("能力与纪律边界")


# ── profile ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_sections_merges_and_lists_dedupe():
    async with async_session() as db:
        r1 = await profile_mod.update_sections(
            db, user_id="u_prof", updates={"pet_peeves": ["圣母心主角"]}, novel_id="n1"
        )
        assert r1["ok"] is True
        r2 = await profile_mod.update_sections(
            db, user_id="u_prof", updates={"pet_peeves": ["圣母心主角", "拖更"]}, novel_id="n1"
        )
        assert r2["ok"] is True
        sections = await profile_mod.load_sections(db, "u_prof")
        # 追加去重：两条、不重复
        assert sections["pet_peeves"] == ["圣母心主角", "拖更"]


@pytest.mark.asyncio
async def test_sensitive_update_carries_ask_hint():
    async with async_session() as db:
        r = await profile_mod.update_sections(
            db, user_id="u_sens", updates={"income": "稿费五位数"}, novel_id="n1"
        )
        assert r["sensitive"] is True
        assert "确认" in r["notice"]


@pytest.mark.asyncio
async def test_pause_stops_summarize():
    async with async_session() as db:
        await profile_mod.set_paused(db, "u_pause", paused=True)
        calls = 0

        async def fake_complete(system, user_text):
            nonlocal calls
            calls += 1
            return "{}"

        result = await profile_mod.maybe_summarize(
            db, user_id="u_pause", novel_id="n1", complete_fn=fake_complete
        )
        assert result == {"skipped": "paused"}
        assert calls == 0
        await profile_mod.set_paused(db, "u_pause", paused=False)


@pytest.mark.asyncio
async def test_summarize_below_threshold_skips():
    async with async_session() as db:
        result = await profile_mod.maybe_summarize(
            db, user_id="u_below", novel_id="n1", complete_fn=None
        )
        assert result["skipped"] == "below_threshold"


@pytest.mark.asyncio
async def test_summarize_merges_and_marks_events():
    uid = "u_summary"
    async with async_session() as db:
        for i in range(profile_mod.SUMMARY_EVERY_EVENTS):
            await profile_mod.record_event(
                db, user_id=uid, novel_id="n1", kind="adopted",
                payload={"tool": "draft_character", "idx": i},
            )

    async def fake_complete(system, user_text):
        # 摘要器收到行为记录
        assert "adopted" in user_text
        return json.dumps({"freeform": "作家常采纳角色草案，偏好反派视角。"})

    result = await profile_mod.maybe_summarize(
        db, user_id=uid, novel_id="n1", complete_fn=fake_complete
    )
    assert result["ok"] is True
    sections = await profile_mod.load_sections(db, uid)
    assert "反派视角" in sections.get("freeform", "")
    # 总结事件已入账；再次跑→below_threshold（无未总结事件）
    result2 = await profile_mod.maybe_summarize(
        db, user_id=uid, novel_id="n1", complete_fn=fake_complete
    )
    assert result2["skipped"] == "below_threshold"


@pytest.mark.asyncio
async def test_summarize_failure_silent():
    async with async_session() as db:
        uid = "u_fail"
        for i in range(profile_mod.SUMMARY_EVERY_EVENTS):
            await profile_mod.record_event(
                db, user_id=uid, novel_id="n1", kind="adopted", payload={"idx": i}
            )

    async def bad_complete(system, user_text):
        raise RuntimeError("模型超时")

    result = await profile_mod.maybe_summarize(
        db, user_id=uid, novel_id="n1", complete_fn=bad_complete
    )
    assert "error" in result  # 静默降级，不冒泡
