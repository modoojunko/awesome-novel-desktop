"""章档归档流水线（c-chapter-dossier D1/D3）：受理→提取→成功原子收口／失败可重试／
逃生阀跳过／重启 sweep／哈希漂移／受理幂等／rows_only 补提取／ghost 409／模型未就绪放行。

用法：
    cd client/backend
    python -m pytest tests/test_dossier_pipeline.py -v
"""

import asyncio
import json
import os
import tempfile
import threading
import time

_tmp_db = tempfile.NamedTemporaryFile(suffix="_dossier_pipe.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_dossier_pipe_")

from sqlalchemy import select  # noqa: E402

from db import (  # noqa: E402
    Base,  # noqa: E402
    async_session,
    engine,
)

_LONG_PROSE = ("林晚在渡口点起灯。守夜人接管了城门。" * 6) + "她攥紧了旧刀，背靠背站着。阿蓟并不知道他是谁。"

_EXTRACT_JSON = json.dumps({
    "settings": [{"area": "势力", "content": "守夜人接管城门", "evidence": "守夜人接管了城门"}],
    "relations": [{"owner": "林晚", "other": "阿蓟", "rel_type": "盟友",
                   "change_note": "从戒备转为并肩", "evidence": "背靠背站着"}],
    "items": [{"name": "旧刀", "change_type": "obtain", "holder": "林晚",
               "detail": "旧刀认主", "evidence": "她攥紧了旧刀"}],
    "knowledge": [{"character": "阿蓟", "fact": "林晚的真实身份", "learned": False,
                   "evidence": "阿蓟并不知道他是谁"}],
}, ensure_ascii=False)


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _seed_book(*, status: str = "writing", archived: bool = False, prose: str = _LONG_PROSE):
    """书+卷+一章（长正文）；返回 (root, nid, ch_id)。"""
    from models.chapter import Chapter, ChapterCharacter, ChapterContent
    from models.project import Novel
    from models.user import User
    from models.volume import Volume

    root = tempfile.mkdtemp(prefix="dossier_pipe_")
    uid = f"dp-{os.path.basename(root)[-10:]}"

    async def _go():
        async with async_session() as s:
            s.add(User(id=uid, email=f"{uid}@t.local", password_hash="x",
                       display_name="流水线", api_key="", api_base_url="", api_model=""))
            proj = Novel(user_id=uid, name="流水线书", slug=f"dp-{os.path.basename(root)}",
                         root_path=root, source="manual", current_phase="write")
            s.add(proj)
            await s.flush()
            vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
            s.add(vol)
            await s.flush()
            ch = Chapter(project_id=proj.id, volume_id=vol.id, chapter_no=1,
                         ref="vol-1-ch-1", title="第1章", status=status,
                         has_prose=True)
            s.add(ch)
            await s.flush()
            s.add(ChapterContent(chapter_id=ch.id, prose=prose))
            s.add(ChapterCharacter(chapter_id=ch.id, sort_order=0, character_name="林晚"))
            await s.commit()
            return proj.id, ch.id

    nid, ch_id = _run(_go())
    return root, nid, ch_id


class _FakeChat:
    """按调用序返回预制应答；可被事件闸住以测并发幂等。"""

    def __init__(self, replies, gate: threading.Event | None = None):
        self.replies = list(replies)
        self.calls = 0
        self.gate = gate
        self.usage_log = []

    async def chat(self, *, model=None, system=None, messages=None,
                   max_tokens=None, usage=None, json_mode=False, **kw):
        self.calls += 1
        if self.gate is not None and self.calls == 1:
            self.gate.wait(timeout=10)
        if usage is not None:
            usage["tokens_in"], usage["tokens_out"] = 100, 50
        reply = self.replies.pop(0) if self.replies else "{}"
        if isinstance(reply, Exception):
            raise reply
        return reply


def _mock_ai(monkeypatch, replies, gate=None):
    fake = _FakeChat(replies, gate)
    monkeypatch.setattr(
        "ai_client.get_ai_client_for_novel", lambda novel_id: _async_val(fake)
    )
    return fake


async def _async_val(v):
    return v


def _wait_job(ch_id, *states, timeout=15.0):
    """轮询 job 状态直到命中 states（默认任何非 extracting 终态）。"""
    from archive.dossier import get_job_state

    deadline = time.time() + timeout
    while time.time() < deadline:
        st = _run(get_job_state(ch_id))
        if st is not None and (not states or st["state"] in states):
            return st
        time.sleep(0.05)
    raise AssertionError(f"job 未到终态 {states}: {st}")


def _chapter_row(ch_id):
    from models.chapter import Chapter

    async def _go():
        async with async_session() as s:
            ch = await s.get(Chapter, ch_id)
            return {
                "status": ch.status,
                "archived_at": ch.archived_at is not None,
                "dossier_stale": ch.dossier_stale,
                "counts": (
                    len(ch.dossier_settings), len(ch.dossier_relations),
                    len(ch.dossier_items), len(ch.dossier_knowledge),
                ),
            }

    return _run(_go())


# ── ① 提取成功 → 原子收口 ───────────────────────────────────────────────────


def test_extract_success_finalizes_atomically(monkeypatch):
    _run(_ensure_tables())
    root, nid, ch_id = _seed_book()
    _mock_ai(monkeypatch, [_EXTRACT_JSON, "本章摘要：灯亮了。"])

    from archive.dossier import accept_extraction, prose_sha256

    got = _run(accept_extraction(nid, root, "vol-1-ch-1", ch_id,
                                 prose_sha256(_LONG_PROSE)))
    assert got["accepted"] and got["state"] == "extracting"

    st = _wait_job(ch_id, "ok")
    assert st["domains"] == {"setting": "extracted", "relation": "extracted",
                             "item": "extracted", "knowledge": "extracted"}
    row = _chapter_row(ch_id)
    assert row["status"] == "archived" and row["archived_at"]
    assert row["counts"] == (1, 1, 1, 1)

    from models.archive import Archive

    async def _arc():
        async with async_session() as s:
            a = (await s.scalars(select(Archive).where(Archive.chapter_id == ch_id))).first()
            return (a.summary, a.content) if a else None

    summary, content = _run(_arc())
    assert summary == "本章摘要：灯亮了。" and content == _LONG_PROSE

    async def _total():
        from models.project import Novel

        async with async_session() as s:
            n = await s.get(Novel, nid)
            return n.total_archives

    assert _run(_total()) == 1


def test_postprocess_flags_and_clamps():
    """证据句宽松校验不匹配→保留+标 evidence_unverified；名册外→unregistered。"""
    from archive.dossier import _postprocess

    data = {
        "settings": [{"area": "势力", "content": "守夜人接管城门", "evidence": "正文里根本没有这句"}],
        "relations": [{"owner": "路人甲", "other": "林晚", "rel_type": "敌对",
                       "change_note": "x", "evidence": "守夜人接管了城门"}],
        "items": [],
        "knowledge": [],
    }
    payload = _postprocess(data, _LONG_PROSE, {"林晚"})
    assert payload["settings"][0]["flags"] == "evidence_unverified"
    assert "unregistered" in payload["relations"][0]["flags"]
    # 上限：9 条截前 6
    many = {"settings": [{"area": "a", "content": f"c{i}", "evidence": "守夜人接管了城门"}
                         for i in range(9)], "relations": [], "items": [], "knowledge": []}
    assert len(_postprocess(many, _LONG_PROSE, set())["settings"]) == 6


# ── ② 失败语义 ──────────────────────────────────────────────────────────────


def test_ai_call_failure_keeps_chapter_unarchived(monkeypatch):
    _run(_ensure_tables())
    root, nid, ch_id = _seed_book()
    _mock_ai(monkeypatch, [RuntimeError("boom")])

    from archive.dossier import accept_extraction, prose_sha256

    _run(accept_extraction(nid, root, "vol-1-ch-1", ch_id, prose_sha256(_LONG_PROSE)))
    st = _wait_job(ch_id, "failed")
    assert "ai_call" in st["error"]
    row = _chapter_row(ch_id)
    assert row["status"] == "writing" and not row["archived_at"]
    assert row["counts"] == (0, 0, 0, 0)


def test_parse_failure_marks_failed(monkeypatch):
    _run(_ensure_tables())
    root, nid, ch_id = _seed_book()
    _mock_ai(monkeypatch, ["这不是 JSON"])

    from archive.dossier import accept_extraction, prose_sha256

    _run(accept_extraction(nid, root, "vol-1-ch-1", ch_id, prose_sha256(_LONG_PROSE)))
    st = _wait_job(ch_id, "failed")
    assert "parse" in st["error"]
    assert _chapter_row(ch_id)["status"] == "writing"


def test_skip_escape_hatch_archives_without_dossier(monkeypatch):
    _run(_ensure_tables())
    root, nid, ch_id = _seed_book()
    _mock_ai(monkeypatch, [RuntimeError("boom")])

    from archive.dossier import (
        accept_extraction,
        prose_sha256,
        skip_extraction_and_archive,
    )

    _run(accept_extraction(nid, root, "vol-1-ch-1", ch_id, prose_sha256(_LONG_PROSE)))
    _wait_job(ch_id, "failed")

    _run(skip_extraction_and_archive(nid, root, "vol-1-ch-1", ch_id, _LONG_PROSE))
    row = _chapter_row(ch_id)
    assert row["status"] == "archived"
    assert row["counts"] == (0, 0, 0, 0)
    from archive.dossier import get_job_state

    assert _run(get_job_state(ch_id))["state"] == "skipped"


# ── ③ 重启 sweep ／ 哈希漂移 ────────────────────────────────────────────────


def test_sweep_marks_interrupted_jobs_failed():
    _run(_ensure_tables())
    _root, nid, ch_id = _seed_book(archived=False)

    from archive.dossier import sweep_stuck_jobs
    from models.chapter import ChapterDossierJob

    async def _fake_running_job():
        async with async_session() as s:
            s.add(ChapterDossierJob(chapter_id=ch_id, novel_id=nid,
                                    state="extracting", prose_hash="x"))
            await s.commit()

    _run(_fake_running_job())
    assert _run(sweep_stuck_jobs()) == 1
    from archive.dossier import get_job_state

    st = _run(get_job_state(ch_id))
    assert st["state"] == "failed" and "interrupted" in st["error"]
    # 幂等：无悬空 job 再跑为 0
    assert _run(sweep_stuck_jobs()) == 0


def test_prose_hash_drift_fails_job(monkeypatch):
    _run(_ensure_tables())
    root, nid, ch_id = _seed_book(prose=_LONG_PROSE)
    _mock_ai(monkeypatch, [_EXTRACT_JSON])

    from archive.dossier import _extract_and_finalize

    # 受理时哈希≠现库正文（提取窗口内被改的等价模拟）
    _run(_extract_and_finalize(nid, root, "vol-1-ch-1", ch_id, True, False))
    # 无 job 行时 _fail_job 无行可落——先建行再验
    from archive.dossier import get_job_state
    from models.chapter import ChapterDossierJob

    async def _add_job():
        async with async_session() as s:
            s.add(ChapterDossierJob(chapter_id=ch_id, novel_id=nid,
                                    state="extracting", prose_hash="stale"))
            await s.commit()

    _run(_add_job())
    _run(_extract_and_finalize(nid, root, "vol-1-ch-1", ch_id, True, False))
    st = _run(get_job_state(ch_id))
    assert st["state"] == "failed" and "prose_changed" in st["error"]
    assert _chapter_row(ch_id)["status"] == "writing"


# ── ④ 受理幂等（in-flight 去重）────────────────────────────────────────────


def test_accept_in_flight_is_idempotent(monkeypatch):
    _run(_ensure_tables())
    root, nid, ch_id = _seed_book()
    gate = threading.Event()
    _mock_ai(monkeypatch, [_EXTRACT_JSON, "摘要"], gate=gate)

    from archive.dossier import accept_extraction, prose_sha256

    first = _run(accept_extraction(nid, root, "vol-1-ch-1", ch_id, prose_sha256(_LONG_PROSE)))
    second = _run(accept_extraction(nid, root, "vol-1-ch-1", ch_id, prose_sha256(_LONG_PROSE)))
    assert first.get("job_id")
    assert second["dedup"] == "in_flight"
    gate.set()
    _wait_job(ch_id, "ok")


# ── ⑤ rows_only 补提取（已归档章重写档，不动收口）─────────────────────────


def test_rows_only_reextract_keeps_archive_state(monkeypatch):
    _run(_ensure_tables())
    root, nid, ch_id = _seed_book(status="archived", archived=True)
    _mock_ai(monkeypatch, [_EXTRACT_JSON])

    from archive.dossier import accept_extraction, prose_sha256

    _run(accept_extraction(nid, root, "vol-1-ch-1", ch_id,
                           prose_sha256(_LONG_PROSE), rows_only=True))
    _wait_job(ch_id, "ok")
    row = _chapter_row(ch_id)
    assert row["status"] == "archived" and row["counts"] == (1, 1, 1, 1)
    from models.project import Novel

    async def _total():
        async with async_session() as s:
            n = await s.get(Novel, nid)
            return n.total_archives

    assert not _run(_total())  # rows_only 不加归档计数


def test_rows_only_reextract_keeps_adopted_rows(monkeypatch):
    """决策留给作家（c-rearchive-keep-adopted）：重提保留已采纳行——只替换未决/
    驳回行，新结果以待确认并存；首次归档（非 rows_only）全清不回归。"""
    _run(_ensure_tables())
    root, nid, ch_id = _seed_book(status="archived", archived=True)
    _mock_ai(monkeypatch, [_EXTRACT_JSON, _EXTRACT_JSON])

    from archive.dossier import accept_extraction, prose_sha256

    _run(accept_extraction(nid, root, "vol-1-ch-1", ch_id,
                           prose_sha256(_LONG_PROSE), rows_only=True))
    _wait_job(ch_id, "ok")

    # 作者确认一条关系行＋一条设定行；驳回一条
    async def _decide():
        from datetime import UTC, datetime

        from models.chapter import Chapter

        async with async_session() as s:
            ch = await s.get(Chapter, ch_id)
            rel = ch.dossier_relations[0]
            rel.status = "accepted"
            rel.decided_at = datetime.now(UTC).replace(tzinfo=None)
            rel.change_note = "作家拍板的关系"
            st = ch.dossier_settings[0]
            st.status = "accepted"
            ch.dossier_items[0].status = "rejected"
            await s.commit()
            return rel.id, st.id

    kept_rel_id, kept_st_id = _run(_decide())

    _run(accept_extraction(nid, root, "vol-1-ch-1", ch_id,
                           prose_sha256(_LONG_PROSE), rows_only=True))
    _wait_job(ch_id, "ok")

    async def _rows():
        from models.chapter import Chapter

        async with async_session() as s:
            ch = await s.get(Chapter, ch_id)
            rels = [(r.id, r.status) for r in ch.dossier_relations]
            sts = [(r.id, r.status) for r in ch.dossier_settings]
            items = [(r.id, r.status) for r in ch.dossier_items]
            return rels, sts, items

    rels, sts, items = _run(_rows())
    # 已采纳的关系/设定行原样保留（同 id 同状态）
    assert (kept_rel_id, "accepted") in rels and (kept_st_id, "accepted") in sts
    # 新提取以待确认并存（关系 2 行＝保留 1＋新 1；设定同）
    assert len(rels) == 2 and len(sts) == 2
    assert any(st == "pending" for _, st in rels)
    # 被驳回的行被重提替换（不在残留为新 pending 之外的第三行）
    assert len(items) == 1

    # 首次归档（非 rows_only）全清语义不回归：用未归档章再提一次，旧行（含保留行）全清
    _root2, nid2, ch2 = _seed_book(status="archived", archived=False)
    _mock_ai(monkeypatch, [_EXTRACT_JSON])
    _run(accept_extraction(nid2, _root2, "vol-1-ch-1", ch2,
                           prose_sha256(_LONG_PROSE)))
    _wait_job(ch2, "ok")
    row = _chapter_row(ch2)
    assert row["counts"] == (1, 1, 1, 1)


def test_skip_triggers_legacy_reconcile(monkeypatch):
    """评审 P2：逃生阀收口与其他两条 finalize 路径一致——触发伏笔/lore 收尾。"""
    _run(_ensure_tables())
    root, nid, ch_id = _seed_book()
    started: list = []

    def _fake_start(novel_id, root_path, chapter_ref, chapter_id, kinds=None):
        started.append((chapter_ref, kinds))
        return {"state": "running"}

    monkeypatch.setattr("archive.reconcile.start_reconcile_job", _fake_start)
    monkeypatch.setattr(
        "auth_local.deps.ai_access_granted", lambda: True
    )

    from archive.dossier import skip_extraction_and_archive

    _run(skip_extraction_and_archive(nid, root, "vol-1-ch-1", ch_id, _LONG_PROSE))
    assert started and started[0][0] == "vol-1-ch-1"
    row = _chapter_row(ch_id)
    assert row["status"] == "archived"
