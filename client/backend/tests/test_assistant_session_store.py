"""会话存储测试（c-agent-session-files：coding agent 式文件后端）。

口径：每书一会话目录（sessions/<novel>/，文件名 日期__thread__id）；seq 单调递增；
悬挂 streaming 行加载自愈为 error（崩前内容保留）；unsafe session id 拒绝；
/new＝新文件旧留档（coding agent 语义）；meta 独立字段更新互不干扰。
"""

import json
import os
from pathlib import Path

import pytest

from assistant import session_store as ss


def test_safe_session_id():
    assert ss.is_safe_session_id("a3f9c2e1" + "0" * 20)
    assert not ss.is_safe_session_id("../../evil")
    assert not ss.is_safe_session_id("a/b")
    assert not ss.is_safe_session_id("")
    assert not ss.is_safe_session_id("x" * 200)


@pytest.mark.asyncio
async def test_get_or_create_session_unique_per_book():
    s1 = await ss.get_or_create_session(user_id="u1", novel_id="n1")
    s1_again = await ss.get_or_create_session(user_id="u1", novel_id="n1")
    s2 = await ss.get_or_create_session(user_id="u1", novel_id="n2")
    assert s1.id == s1_again.id and s1_again.path == s1.path
    assert s2.id != s1.id
    # 文件名契约：日期__thread__id（boss 口径 id+日期）
    name = os.path.basename(s1.path)
    assert name.startswith("20") and "__" in name and name.endswith(".jsonl")


@pytest.mark.asyncio
async def test_append_message_seq_monotonic_and_heal():
    session = await ss.get_or_create_session(user_id="u_seq", novel_id="n_seq")
    m1 = await ss.append_message(session, role="user", content="第一问", page="volume")
    pending = await ss.append_message(
        session, role="assistant", content="写到一半", page="volume", status="streaming"
    )
    m3 = await ss.append_message(session, role="user", content="第二问")
    assert m3.seq == pending.seq + 1
    assert pending.seq == m1.seq + 1

    rows = await ss.load_messages(session)
    # 刚创建的 streaming 行＝活跃 run（线程切换 GET 命中常态），不误标
    live = next(r for r in rows if r.id == pending.id)
    assert live.status == "streaming"
    # 把行改老（超墙钟宽限）→ 自愈为 error，崩前内容保留（文件被整段重写）
    rows = await ss.load_messages(session, heal=False)
    for r in rows:
        if r.id == pending.id:
            r.created_at = "2020-01-01 00:00:00"
    meta_d, msgs = ss._parse_file(session.__dict__["path"] and __import__("pathlib").Path(session.path))
    for o in msgs:
        if o.get("id") == pending.id:
            o["created_at"] = "2020-01-01 00:00:00"
    ss._dump_file(__import__("pathlib").Path(session.path), meta_d, msgs)
    rows = await ss.load_messages(session)
    healed = next(r for r in rows if r.id == pending.id)
    assert healed.status == "error"
    assert healed.content == "写到一半"
    assert [r.seq for r in rows] == sorted(r.seq for r in rows)


@pytest.mark.asyncio
async def test_heal_tz_transition_negative_age(tmp_path):
    """时区过渡钉（c-agent-session-files TZ 收口）：created_at 呈「未来」（旧本地
    时区串 × 新 UTC now）＝负年龄 → 按超龄收尾，不误判活跃 run 永挂。"""
    session = await ss.get_or_create_session(user_id="u_tz", novel_id="n_tz")
    from datetime import datetime, timedelta

    future = (datetime.now() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    pending = await ss.append_message(
        session, role="assistant", content="半截", status="streaming",
    )
    # 手工把 created_at 改到「未来」并直接落盘（模拟旧时区写入的行）
    p_jsonl = Path(pending.path)
    lines = p_jsonl.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        o = json.loads(line)
        if o.get("id") == pending.id:
            o["created_at"] = future
        out.append(json.dumps(o, ensure_ascii=False))
    p_jsonl.write_text("\n".join(out) + "\n", encoding="utf-8")
    rows = await ss.load_messages(session)
    healed = next(r for r in rows if r.id == pending.id)
    assert healed.status == "error", "负年龄行应按超龄收尾"


@pytest.mark.asyncio
async def test_touch_session_updates_meta_independently():
    session = await ss.get_or_create_session(user_id="u_meta", novel_id="n_meta")
    await ss.touch_session(session, page_cursor="volume", grants={"tier": "allow_book"})
    assert session.page_cursor == "volume"
    assert json.loads(session.grants_json) == {"tier": "allow_book"}
    # compact 只动自己的字段；重新解析确认落盘
    await ss.touch_session(session, compaction={"boundary_index": 5})
    again = await ss.get_or_create_session(user_id="u_meta", novel_id="n_meta")
    assert again.page_cursor == "volume"
    assert json.loads(again.compaction_json)["boundary_index"] == 5
    assert json.loads(again.grants_json) == {"tier": "allow_book"}


@pytest.mark.asyncio
async def test_new_session_creates_file_and_keeps_old():
    """coding agent 语义：/new＝新文件旧留档；grants 继承、compact 清零、消息清空。"""
    session = await ss.get_or_create_session(user_id="u_reset", novel_id="n_reset")
    await ss.append_message(session, role="user", content="hi")
    await ss.touch_session(session, compaction={"boundary_index": 3})
    old_path = session.path
    fresh = await ss.reset_session(session)
    assert fresh.id != session.id
    assert fresh.path != old_path
    assert os.path.exists(old_path)  # 旧文件留档
    rows = await ss.load_messages(fresh)
    assert rows == []
    assert fresh.compaction_json == "{}"
    assert json.loads(fresh.grants_json) == json.loads(session.grants_json)
    # 同 thread 解析回到最新（fresh），旧文件不混入
    again = await ss.get_or_create_session(user_id="u_reset", novel_id="n_reset")
    assert again.id == fresh.id


@pytest.mark.asyncio
async def test_load_session_rejects_foreign_user():
    session = await ss.get_or_create_session(user_id="u_owner", novel_id="n_own")
    foreign = await ss.load_session(session.id, user_id="u_attacker")
    assert foreign is None
    ok = await ss.load_session(session.id, user_id="u_owner")
    assert ok is not None and ok.id == session.id
    assert await ss.load_session("../../evil", user_id="u_owner") is None


@pytest.mark.asyncio
async def test_find_card_and_message_across_threads():
    """跨线程找产物卡/消息（adopt/undo 数据源）。"""
    a = await ss.get_or_create_session(user_id="u_card", novel_id="n_card", thread_key="ch:og")
    b = await ss.get_or_create_session(user_id="u_card", novel_id="n_card", thread_key="ch:prose")
    card = await ss.append_message(b, role="assistant", card_kind="struct", payload={"cardId": "cx1"})
    found = await ss.find_card_message("n_card", "cx1")
    assert found is not None and found.id == card.id and found.path == card.path
    assert await ss.find_card_message("n_card", "nope") is None

    msg = await ss.append_message(a, role="tool", content="写入", payload={"writeLog": {}})
    got = await ss.find_message("n_card", msg.id)
    assert got is not None and got.id == msg.id
    assert await ss.find_message("n_card", "missing") is None


@pytest.mark.asyncio
async def test_db_migration_exports_equivalent_jsonl_idempotent():
    """迁移钉（D4）：DB 播种 → migrate_db_sessions → 文件逐字段对拍 → 幂等重跑。"""
    from pathlib import Path

    from config import DATA_ROOT
    from db import async_session
    from models.assistant import AssistantMessage, AssistantSession

    # 播种：一个 DB 会话＋两条消息
    sid = "migsess0001hex0000000000000001"
    async with async_session() as db:
        db.add(AssistantSession(
            id=sid, user_id="u_mig", novel_id="n_mig", thread_key="ch:og",
            page_cursor="ch:og", grants_json='{"tier": "allow_book"}',
            compaction_json="{}", created_at="2026-11-18 08:00:00",
            updated_at="2026-11-18 08:30:00",
        ))
        db.add(AssistantMessage(
            id="migmsg0001hex0000000000000001", session_id=sid, novel_id="n_mig",
            seq=1, role="user", page="ch:og", content="迁移钉第一问",
            payload_json='{"k": "v"}', card_kind="", status="done",
            run_id="", tokens_in=0, tokens_out=0, created_at="2026-11-18 08:01:00",
        ))
        db.add(AssistantMessage(
            id="migmsg0002hex0000000000000002", session_id=sid, novel_id="n_mig",
            seq=2, role="assistant", page="ch:og", content="迁移钉回复",
            payload_json="{}", card_kind="struct", status="done",
            run_id="r1", tokens_in=10, tokens_out=5, created_at="2026-11-18 08:02:00",
        ))
        await db.commit()

    await ss.migrate_db_sessions()
    files = list((Path(DATA_ROOT) / "sessions" / "n_mig").glob("*migsess*.jsonl"))
    assert len(files) == 1, files
    meta_d, msgs = ss._parse_file(files[0])
    assert meta_d and meta_d["id"] == sid and meta_d["thread_key"] == "ch:og"
    assert meta_d["grants"] == {"tier": "allow_book"}
    assert [m["seq"] for m in msgs] == [1, 2]
    assert msgs[0]["content"] == "迁移钉第一问" and msgs[0]["payload"] == {"k": "v"}
    assert msgs[1]["card_kind"] == "struct" and msgs[1]["tokens_out"] == 5
    # 幂等重跑：不重复导出
    out2 = await ss.migrate_db_sessions()
    files2 = list((Path(DATA_ROOT) / "sessions" / "n_mig").glob("*migsess*.jsonl"))
    assert len(files2) == 1
    assert out2["skipped"] >= 1
    # 迁移后的会话可以被正常解析/续聊（get_or_create 命中迁移文件）
    again = await ss.get_or_create_session(user_id="u_mig", novel_id="n_mig", thread_key="ch:og")
    assert again.id == sid
    rows = await ss.load_messages(again)
    assert len(rows) == 2 and rows[0].content == "迁移钉第一问"


@pytest.mark.asyncio
async def test_meta_line_over_2kb_does_not_duplicate_session():
    """审查 P1 回归钉：compact 摘要撑大 meta 行（>2048 字节）后，线程解析
    必须仍命中原会话——截断读取会误判为新线程建重复文件、历史搁浅。"""
    import json as _json
    from pathlib import Path

    session = await ss.get_or_create_session(user_id="u_big", novel_id="n_big", thread_key="ch:og")
    big_summary = "长" * 2500  # SUMMARY_MAX_TOKENS=3000 量级的 compact 摘要
    await ss.touch_session(session, compaction={"boundary_index": 5, "summary_text": big_summary})

    # meta 行确实超 2048 字节（触发条件成立）
    raw_first = Path(session.path).read_text(encoding="utf-8").splitlines()[0]
    assert len(raw_first.encode("utf-8")) > 2048

    again = await ss.get_or_create_session(user_id="u_big", novel_id="n_big", thread_key="ch:og")
    assert again.id == session.id, "大 meta 行必须仍解析命中原会话"
    assert again.path == session.path
    assert _json.loads(again.compaction_json)["summary_text"] == big_summary
    # 目录里只有一个文件（无 duplicate）
    novel_dir = Path(session.path).parent
    assert len(list(novel_dir.glob("*.jsonl"))) == 1
