"""会话存储测试（c-writing-agent 批A 1.1）。

口径：每书一会话（UNIQUE user_id+novel_id）；seq 单调递增；悬挂 streaming 行
加载自愈为 error（崩前内容保留）；unsafe session id 拒绝；reset 清消息与 compact。
"""

import pytest

from assistant import session_store as ss
from db import async_session


def test_safe_session_id():
    assert ss.is_safe_session_id("a3f9c2e1" + "0" * 20)
    assert not ss.is_safe_session_id("../../evil")
    assert not ss.is_safe_session_id("a/b")
    assert not ss.is_safe_session_id("")
    assert not ss.is_safe_session_id("x" * 200)


@pytest.mark.asyncio
async def test_get_or_create_session_unique_per_book():
    async with async_session() as db:
        s1 = await ss.get_or_create_session(db, user_id="u1", novel_id="n1")
        s1_again = await ss.get_or_create_session(db, user_id="u1", novel_id="n1")
        s2 = await ss.get_or_create_session(db, user_id="u1", novel_id="n2")
        assert s1.id == s1_again.id
        assert s2.id != s1.id


@pytest.mark.asyncio
async def test_append_message_seq_monotonic_and_heal():
    async with async_session() as db:
        session = await ss.get_or_create_session(db, user_id="u_seq", novel_id="n_seq")
        m1 = await ss.append_message(
            db, session.id, novel_id="n_seq", role="user", content="第一问", page="volume"
        )
        pending = await ss.append_message(
            db, session.id, novel_id="n_seq", role="assistant", content="写到一半",
            page="volume", status="streaming",
        )
        m3 = await ss.append_message(
            db, session.id, novel_id="n_seq", role="user", content="第二问"
        )
        assert m3.seq == pending.seq + 1
        assert pending.seq == m1.seq + 1

        rows = await ss.load_messages(db, session.id)
        # 悬挂 streaming 自愈为 error，崩前内容保留
        healed = next(r for r in rows if r.id == pending.id)
        assert healed.status == "error"
        assert healed.content == "写到一半"
        assert [r.seq for r in rows] == sorted(r.seq for r in rows)


@pytest.mark.asyncio
async def test_touch_session_updates_meta_independently():
    async with async_session() as db:
        session = await ss.get_or_create_session(db, user_id="u_meta", novel_id="n_meta")
        await ss.touch_session(
            db, session.id, page_cursor="volume", grants={"tier": "allow_book"}
        )
        await db.refresh(session)
        assert session.page_cursor == "volume"
        import json

        assert json.loads(session.grants_json) == {"tier": "allow_book"}
        # compact 只动自己的列
        await ss.touch_session(db, session.id, compaction={"boundary_index": 5})
        await db.refresh(session)
        assert session.page_cursor == "volume"
        assert json.loads(session.compaction_json)["boundary_index"] == 5


@pytest.mark.asyncio
async def test_reset_session_clears_messages_and_compaction():
    async with async_session() as db:
        session = await ss.get_or_create_session(db, user_id="u_reset", novel_id="n_reset")
        await ss.append_message(db, session.id, novel_id="n_reset", role="user", content="hi")
        await ss.touch_session(db, session.id, compaction={"boundary_index": 3})
        await ss.reset_session(db, session.id)
        rows = await ss.load_messages(db, session.id)
        assert rows == []
        await db.refresh(session)
        assert session.compaction_json == "{}"


@pytest.mark.asyncio
async def test_load_session_rejects_foreign_user():
    async with async_session() as db:
        session = await ss.get_or_create_session(db, user_id="u_owner", novel_id="n_own")
        foreign = await ss.load_session(db, session.id, user_id="u_attacker")
        assert foreign is None
        ok = await ss.load_session(db, session.id, user_id="u_owner")
        assert ok is not None and ok.id == session.id
        assert await ss.load_session(db, "../../evil", user_id="u_owner") is None
