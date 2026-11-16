"""助手人格覆盖测试（boss 拍板 2026-11-15：人格入顶栏控制中心，作家可查看/编辑/恢复默认）。

解析链：用户覆盖 > 提示词包 > 内置兜底；覆盖残缺 SHALL NOT 拒载（记警告回落）；
保存走 validate_identity fail-loud（四字段缺一即 422）。
"""

import pytest
from sqlalchemy import select

from assistant import identity as identity_mod
from db import async_session

PERSONA = {
    "name": "老墨",
    "persona": "毒舌但靠谱的写作搭档",
    "voice_rules": "短句、直接、偶尔损你一句",
    "fence_rules": "只做这本书和知识库内的事，其他明说没能力",
}


@pytest.mark.asyncio
async def test_persona_roundtrip_and_clear():
    async with async_session() as db:
        assert await identity_mod.load_persona(db, "u_persona") is None
        saved = await identity_mod.save_persona(db, "u_persona", PERSONA)
        assert saved == PERSONA
        loaded = await identity_mod.load_persona(db, "u_persona")
        assert loaded == PERSONA
        await identity_mod.clear_persona(db, "u_persona")
        assert await identity_mod.load_persona(db, "u_persona") is None


@pytest.mark.asyncio
async def test_persona_save_missing_fields_fail_loud():
    async with async_session() as db:
        with pytest.raises(RuntimeError):
            await identity_mod.save_persona(db, "u_persona2", {"name": "只有名字"})
        with pytest.raises(TypeError):
            await identity_mod.save_persona(db, "u_persona2", "不是对象")
        assert await identity_mod.load_persona(db, "u_persona2") is None


@pytest.mark.asyncio
async def test_load_identity_for_user_prefers_override(monkeypatch):
    async with async_session() as db:
        await identity_mod.save_persona(db, "u_persona3", PERSONA)
        got = await identity_mod.load_identity_for_user(db, "u_persona3")
        assert got["name"] == "老墨"
        await identity_mod.clear_persona(db, "u_persona3")


@pytest.mark.asyncio
async def test_load_identity_for_user_invalid_override_falls_back(monkeypatch):
    """覆盖残缺不拒载：记警告后回落提示词包/内置（fail-soft 与 spec 拒载口径分工——
    启动校验针对包；用户覆盖是运行期数据，坏了就回落）。"""
    async with async_session() as db:
        await identity_mod.save_persona(db, "u_persona4", PERSONA)
        from models.assistant import AssistantPersona

        row = (
            await db.scalars(
                select(AssistantPersona).where(AssistantPersona.user_id == "u_persona4")
            )
        ).first()
        row.identity_json = '{"name": "缺三字段"}'
        await db.commit()

        async def _fake_load_identity():
            return dict(identity_mod.DEFAULT_IDENTITY)

        monkeypatch.setattr(identity_mod, "load_identity", _fake_load_identity)
        got = await identity_mod.load_identity_for_user(db, "u_persona4")
        assert got == identity_mod.DEFAULT_IDENTITY
        await identity_mod.clear_persona(db, "u_persona4")
