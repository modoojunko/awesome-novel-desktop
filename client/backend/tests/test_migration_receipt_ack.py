"""c-carry-receipt-ack — 完成回执「收起」持久化单测。

口径：用户报修「完成提示条点 × 后刷新又冒出来」（原实现 × 只改组件内 state）。
× 语义改为「收起并记住」：写 `migration.receipt_acked`（绑候选 stamp、存当前库
app_meta），candidates 据此置 `receipt_acked`；源数据件变化＝新一次迁移，对拍
不命中即回执重开（不吞新数据，规则与 snoozed 同源）。
"""

import asyncio
import json
import sqlite3
from pathlib import Path

from migration import router


def _run_candidates(monkeypatch, *, last, acked, scanned=None):
    def fake_get(key: str):
        if key == "migration.last":
            return json.dumps(last) if last is not None else None
        if key == router.RECEIPT_ACK_KEY:
            return acked or None
        return None

    monkeypatch.setattr(router, "_app_meta_value", fake_get)
    items = scanned or [{"filename": "novel-v0.24.db", "stamp": "S1",
                         "stamp_legacy": "S1-legacy",
                         "recommended": True, "unreadable": False}]

    def fake_scan(root, ver, active):
        return [dict(it) for it in items]

    monkeypatch.setattr(router, "scan_migration_candidates", fake_scan)
    return asyncio.run(router.candidates())["data"]["candidates"]


COMPLETE_LAST = {"source_stamp": "S1",
                 "report": {"status": "ok", "tables_skipped": [],
                            "fk_violations": [],
                            "book_count_source": 2, "book_count_present": 2}}


def test_stamp_match_marks_receipt_acked(monkeypatch):
    """已阅键命中候选 stamp → carried 且 receipt_acked 双真（前端不再渲染完成行）。"""
    cands = _run_candidates(monkeypatch, last=COMPLETE_LAST, acked="S1")
    assert cands[0]["carried"] is True and cands[0]["receipt_acked"] is True


def test_no_ack_key_keeps_receipt(monkeypatch):
    """未收起过（无键）：回执照常呈现（完成行渲染的默认态）。"""
    cands = _run_candidates(monkeypatch, last=COMPLETE_LAST, acked="")
    assert cands[0]["carried"] is True and cands[0]["receipt_acked"] is False


def test_ack_bound_to_stamp(monkeypatch):
    """已阅绑指纹：只命中被收起的那一份，其余候选不受影响。"""
    scanned = [
        {"filename": "novel-v0.24.db", "stamp": "S1", "stamp_legacy": "S1-l",
         "recommended": True, "unreadable": False},
        {"filename": "novel-v0.23.db", "stamp": "S2", "stamp_legacy": "S2-l",
         "recommended": False, "unreadable": False},
    ]
    cands = _run_candidates(monkeypatch, last=COMPLETE_LAST, acked="S2", scanned=scanned)
    assert cands[0]["receipt_acked"] is False and cands[1]["receipt_acked"] is True


def test_data_drift_reopens_receipt(monkeypatch):
    """数据件变了（旧版又写过）：已阅对拍不命中 → 回执重开（不吞新数据）。"""
    scanned = [{"filename": "novel-v0.24.db", "stamp": "S1-new",
                "stamp_legacy": "S1-legacy-new",
                "recommended": True, "unreadable": False}]
    cands = _run_candidates(monkeypatch, last=COMPLETE_LAST, acked="S1", scanned=scanned)
    assert cands[0]["receipt_acked"] is False


def test_legacy_form_stamp_still_matches(monkeypatch):
    """c-carry-modal-reshow 兼容双形态对拍：旧三件套指纹形态的已阅记录同样命中。"""
    cands = _run_candidates(monkeypatch, last=COMPLETE_LAST, acked="S1-legacy")
    assert cands[0]["receipt_acked"] is True


def test_receipt_ack_endpoint_writes_key(monkeypatch):
    """端点在事务内写 RECEIPT_ACK_KEY（值＝候选 stamp），不产其他副作用。"""
    written = {}

    async def fake_set(key, value):
        written[key] = value

    def fake_validate(root, filename, active, allow_sentinel=False):
        f = Path(root) / filename
        f.write_bytes(b"x")
        return f

    monkeypatch.setattr(router, "_set_app_meta", fake_set)
    monkeypatch.setattr("db_lifecycle.validate_candidate_filename", fake_validate)
    monkeypatch.setattr(router, "DATA_ROOT", "/tmp")
    out = asyncio.run(router.receipt_ack(router.DismissBody(filename="novel-v0.24.db")))
    assert out == {"code": 0}
    assert written.get(router.RECEIPT_ACK_KEY)  # 值＝候选 stamp（非空）
    assert router.SNOOZE_KEY not in written  # 收起回执不动「本版不再提醒」抑制键


def test_receipt_ack_endpoint_rejects_unknown_file(monkeypatch):
    """白名单外/不存在的文件 → code 1，不写任何键（与 dismiss 同源校验）。"""
    written = {}

    async def fake_set(key, value):
        written[key] = value

    monkeypatch.setattr(router, "_set_app_meta", fake_set)
    monkeypatch.setattr("db_lifecycle.validate_candidate_filename",
                        lambda root, filename, active, allow_sentinel=False: None)
    out = asyncio.run(router.receipt_ack(router.DismissBody(filename="../../x.db")))
    assert out["code"] == 1 and written == {}


def test_receipt_ack_persists_end_to_end(tmp_path, monkeypatch):
    """端到端（真 app＋真库）：POST /receipt-ack 落进当前库 app_meta，重取候选即翻转。

    这是「刷新不复现」的最强判据——已阅态不在前端内存里，而在库里；重取一次候选
    （＝刷新页面）receipt_acked 为真，完成行不再渲染。
    """
    from fastapi.testclient import TestClient

    from config import DATABASE_URL
    from schema_version import candidate_stamp
    from tests.test_version_upgrade_acceptance import _app_meta, _make_lib

    root = tmp_path / "data"
    root.mkdir()
    src = _make_lib(root / "novel-v0.24.db", books=2, schema_id="s-0.24")
    monkeypatch.setattr(router, "DATA_ROOT", root)

    from main import app

    active = Path(DATABASE_URL.split("///")[-1])
    stamp = candidate_stamp(src.name, src)
    con = sqlite3.connect(active)
    prev = dict(con.execute("SELECT key, value FROM app_meta WHERE key IN ('migration.last', ?)",
                            (router.RECEIPT_ACK_KEY,)).fetchall())
    con.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES ('migration.last', ?)",
                (json.dumps({"source_filename": src.name, "source_stamp": stamp,
                             "report": {"status": "ok", "tables_skipped": [],
                                        "fk_violations": [],
                                        "book_count_source": 2,
                                        "book_count_present": 2}}),))
    con.commit()
    con.close()
    try:
        with TestClient(app) as client:
            first = client.get("/api/backup/db-migration/candidates"
                               ).json()["data"]["candidates"]
            assert first[0]["carried"] is True and first[0]["receipt_acked"] is False

            ack = client.post("/api/backup/db-migration/receipt-ack",
                              json={"filename": src.name})
            assert ack.json() == {"code": 0}
            # 落库证据：当前库 app_meta 真值（不经前端状态）
            assert _app_meta(active).get(router.RECEIPT_ACK_KEY) == stamp

            again = client.get("/api/backup/db-migration/candidates"
                               ).json()["data"]["candidates"]
            assert again[0]["receipt_acked"] is True
    finally:
        # 会话级共享库：按原值恢复本次写入（不污染后续用例）
        con = sqlite3.connect(active)
        con.execute("DELETE FROM app_meta WHERE key IN ('migration.last', ?)",
                    (router.RECEIPT_ACK_KEY,))
        con.executemany("INSERT INTO app_meta (key, value) VALUES (?, ?)", prev.items())
        con.commit()
        con.close()
