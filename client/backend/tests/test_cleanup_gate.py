"""c-db-version-hardening — 清理白名单收窄（_migrated_stamps）单测

规格（db-generation）：仅「本次成功带回」的源可删；含整表跳过/FK 违规的搬运
SHALL NOT 出现清理入口；老格式条目（缺完整性字段）保守排除——少删优于误删。
"""

import json

from migration import router


def _set_meta(monkeypatch, last: dict | None, history: list[dict]):
    def fake_get(key: str):
        if key == "migration.last":
            return json.dumps(last) if last is not None else None
        if key == router.HISTORY_KEY:
            return json.dumps(history)
        return None

    monkeypatch.setattr(router, "_app_meta_value", fake_get)


def test_only_last_complete_stamp_deletable(monkeypatch):
    _set_meta(
        monkeypatch,
        last={"source_filename": "novel-v0.23.db", "source_stamp": "B"},
        history=[
            {"source_stamp": "A", "tables_skipped": 2, "fk_violations": 0,
             "book_count_source": 1, "book_count_migrated": 1},
            {"source_stamp": "B", "tables_skipped": 0, "fk_violations": 0,
             "book_count_source": 1, "book_count_migrated": 1},
        ],
    )
    assert router._migrated_stamps() == {"B"}


def test_fk_violations_excluded(monkeypatch):
    _set_meta(
        monkeypatch,
        last={"source_filename": "novel-v0.23.db", "source_stamp": "B"},
        history=[{"source_stamp": "B", "tables_skipped": 0, "fk_violations": 3,
                  "book_count_source": 1, "book_count_migrated": 1}],
    )
    assert router._migrated_stamps() == set()


def test_count_mismatch_excluded(monkeypatch):
    _set_meta(
        monkeypatch,
        last={"source_filename": "novel-v0.23.db", "source_stamp": "B"},
        history=[{"source_stamp": "B", "tables_skipped": 0, "fk_violations": 0,
                  "book_count_source": 3, "book_count_migrated": 1}],
    )
    assert router._migrated_stamps() == set()


def test_legacy_entry_without_integrity_fields_excluded(monkeypatch):
    """老格式（无完整性字段）：保守视为不完整，不进待删清单。"""
    _set_meta(
        monkeypatch,
        last={"source_filename": "novel-v0.23.db", "source_stamp": "B"},
        history=[{"source_filename": "novel-v0.23.db", "source_stamp": "B",
                  "book_count_migrated": 1}],
    )
    assert router._migrated_stamps() == set()


def test_no_last_no_deletable(monkeypatch):
    _set_meta(monkeypatch, last=None,
              history=[{"source_stamp": "A", "tables_skipped": 0, "fk_violations": 0}])
    assert router._migrated_stamps() == set()
