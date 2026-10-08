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


# ── c-lossless-upgrade：完整性判定单源（report dict 形态）─────────────────

def test_last_with_complete_report_deletable(monkeypatch):
    """migration.last 内嵌完整 report（新格式）：直接判，不依赖 history。"""
    _set_meta(
        monkeypatch,
        last={"source_filename": "novel-v0.23.db", "source_stamp": "B",
              "report": {"status": "ok", "tables_skipped": [], "fk_violations": [],
                         "book_count_source": 2, "book_count_migrated": 2}},
        history=[],
    )
    assert router._migrated_stamps() == {"B"}


def test_last_with_incomplete_report_not_deletable(monkeypatch):
    """report 不完整（有整表跳过）：不进白名单——且同一判定供候选抑制消费。"""
    _set_meta(
        monkeypatch,
        last={"source_filename": "novel-v0.23.db", "source_stamp": "B",
              "report": {"status": "ok", "tables_skipped": [{"table": "x"}],
                         "fk_violations": [],
                         "book_count_source": 2, "book_count_migrated": 2}},
        history=[],
    )
    assert router._migrated_stamps() == set()


def test_is_complete_report_predicate():
    from migration.engine import completeness_from_history, is_complete_report

    ok = {"status": "ok", "tables_skipped": [], "fk_violations": [],
          "book_count_source": 3, "book_count_migrated": 3}
    assert is_complete_report(ok) is True
    assert is_complete_report(None) is False
    assert is_complete_report({"status": "error"}) is False
    # 书数不一致 / FK 违规 → 不完整
    assert is_complete_report({**ok, "book_count_migrated": 2}) is False
    assert is_complete_report({**ok, "fk_violations": [{"table": "t"}]}) is False
    # history（计数形态）经适配器等价
    entry = {"tables_skipped": 0, "fk_violations": 1,
             "book_count_source": 1, "book_count_migrated": 1}
    assert is_complete_report(completeness_from_history(entry)) is False
    assert is_complete_report(completeness_from_history(
        {"tables_skipped": 0, "fk_violations": 0,
         "book_count_source": 1, "book_count_migrated": 1})) is True
