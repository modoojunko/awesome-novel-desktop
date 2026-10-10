"""c-lossless-upgrade —「稍后带」抑制状态单测。

口径（db-generation delta）：snoozed 键绑候选 stamp、存当前库 app_meta；不完整
migration.last 永不抑制；搬完清除；旧 migration.dismissed（永久静默）不再参与抑制。
"""

import json

from migration import router


def _items(stamps):
    return [{"filename": f"novel-v{s}.db", "stamp": s, "recommended": i == 0,
             "unreadable": False} for i, s in enumerate(stamps)]


def _run_candidates(monkeypatch, *, last, snoozed, dismissed=""):
    state = {"snoozed": snoozed, "dismissed": dismissed}

    def fake_get(key: str):
        if key == "migration.last":
            return json.dumps(last) if last is not None else None
        return state.get(key.replace("migration.", "")) or None

    monkeypatch.setattr(router, "_app_meta_value", fake_get)
    scanned = _items(["S1", "S2"])

    def fake_scan(root, ver, active):
        return [dict(it) for it in scanned]

    monkeypatch.setattr(router, "scan_migration_candidates", fake_scan)

    import asyncio

    return asyncio.run(router.candidates())["data"]["candidates"]


def test_snoozed_stamp_suppresses(monkeypatch):
    cands = _run_candidates(monkeypatch, last=None, snoozed="S1")
    assert cands[0]["suppressed"] is True and cands[0]["carried"] is False
    assert cands[1]["suppressed"] is False  # 只抑制被 snooze 的那份


def test_incomplete_last_never_suppresses(monkeypatch):
    """不完整搬运＝未达成：stamp 相等也不抑制（常驻行继续提醒）。"""
    last = {"source_stamp": "S1", "report": {"status": "ok",
                                             "tables_skipped": [{"table": "x"}],
                                             "fk_violations": []}}
    cands = _run_candidates(monkeypatch, last=last, snoozed="")
    assert cands[0]["suppressed"] is False and cands[0]["carried"] is False


def test_complete_last_carries_and_suppresses(monkeypatch):
    last = {"source_stamp": "S1", "report": {"status": "ok", "tables_skipped": [],
                                             "fk_violations": [],
                                             "book_count_source": 2,
                                             "book_count_migrated": 2}}
    cands = _run_candidates(monkeypatch, last=last, snoozed="")
    assert cands[0]["carried"] is True and cands[0]["suppressed"] is True


def test_legacy_dismissed_key_no_longer_suppresses(monkeypatch):
    """旧 dismissed（永久静默）退役：存量用户升级后不被永久静默。"""
    cands = _run_candidates(monkeypatch, last=None, snoozed="", dismissed="S1")
    assert cands[0]["suppressed"] is False


def test_dismiss_endpoint_writes_snooze_key(monkeypatch):
    """dismiss 端点写 SNOOZE_KEY（不再产永久静默）。"""
    import asyncio
    from pathlib import Path as _P

    written = {}

    async def fake_set(key, value):
        written[key] = value

    def fake_validate(root, filename, active, allow_sentinel=False):
        f = _P(root) / filename
        f.write_bytes(b"x")
        return f

    monkeypatch.setattr(router, "_set_app_meta", fake_set)
    monkeypatch.setattr("db_lifecycle.validate_candidate_filename", fake_validate)
    # candidate_stamp 需要真文件（读三件套 stat）——上面已落盘占位
    monkeypatch.setattr(router, "DATA_ROOT", "/tmp")
    out = asyncio.run(router.dismiss(router.DismissBody(filename="novel-v0.24.db")))
    assert out == {"code": 0}
    assert router.SNOOZE_KEY in written and "migration.dismissed" not in written


def test_olderstamp_record_still_carries(monkeypatch):
    """c-carry-modal-reshow 兼容：升级前的完成记录是旧三件套指纹（含 -shm 分量），
    与现行扫描指纹（数据件形态）不同串——按「数据件未变即同一源」对拍，carried 仍
    为真（否则这台机器告知卡复弹不止，恰是真机事故形态）。"""
    import asyncio

    state = {"snoozed": "", "dismissed": ""}

    def fake_get(key: str):
        if key == "migration.last":
            return json.dumps({"source_stamp": "S1-legacy",
                               "report": {"status": "ok", "tables_skipped": [],
                                          "fk_violations": [],
                                          "book_count_source": 1,
                                          "book_count_present": 1}})
        return state.get(key.replace("migration.", "")) or None

    monkeypatch.setattr(router, "_app_meta_value", fake_get)
    scanned = [{"filename": "novel-v0.30.2.db", "stamp": "S1", "stamp_legacy": "S1-legacy",
                "recommended": True, "unreadable": False}]

    def fake_scan(root, ver, active):
        return [dict(it) for it in scanned]

    monkeypatch.setattr(router, "scan_migration_candidates", fake_scan)
    cands = asyncio.run(router.candidates())["data"]["candidates"]
    assert cands[0]["carried"] is True and cands[0]["suppressed"] is True


def test_data_drift_breaks_both_forms(monkeypatch):
    """数据件变了：现行与旧指纹都不命中 → carried/suppressed 均假（不放松
    「dismiss 不吞新数据」）。"""
    import asyncio

    state = {"snoozed": "S1-legacy", "dismissed": ""}

    def fake_get(key: str):
        if key == "migration.last":
            return json.dumps({"source_stamp": "S1",
                               "report": {"status": "ok", "tables_skipped": [],
                                          "fk_violations": [],
                                          "book_count_source": 1,
                                          "book_count_present": 1}})
        return state.get(key.replace("migration.", "")) or None

    monkeypatch.setattr(router, "_app_meta_value", fake_get)
    scanned = [{"filename": "novel-v0.30.2.db", "stamp": "S1-new", "stamp_legacy": "S1-legacy-new",
                "recommended": True, "unreadable": False}]

    def fake_scan(root, ver, active):
        return [dict(it) for it in scanned]

    monkeypatch.setattr(router, "scan_migration_candidates", fake_scan)
    cands = asyncio.run(router.candidates())["data"]["candidates"]
    assert cands[0]["carried"] is False and cands[0]["suppressed"] is False
