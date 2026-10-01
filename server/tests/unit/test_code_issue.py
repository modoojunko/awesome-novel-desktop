"""code_issue.py（s-code-issue）发码脚本单测：httpx MockTransport 模拟 PostgREST。

覆盖 spec code-issuance 的护栏：预算 CAS/不足整批回收/CAS 失配回补、档位 tiers 表
校验、天数护栏与 --force、作废收窄（active 拒绝）、对账不变式告警、三态统计。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

_REPO = Path(__file__).resolve().parents[3]  # server/tests/unit → repo root


def _load_tool_class():
    spec = importlib.util.spec_from_file_location(
        "code_issue", _REPO / "scripts" / "code_issue.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["code_issue"] = mod
    spec.loader.exec_module(mod)
    return mod


code_issue = _load_tool_class()
CodeIssueError = code_issue.CodeIssueError

ENDPOINT = "https://env.api.tcloudbasegateway.com/v1/rdb/rest"


class FakeStore:
    """内存表：按 (table, 唯一键) 存行，处理脚本用到的 GET/POST/PATCH/DELETE。"""

    UNIQUE = {"global_config": "key", "code_batches": "batch_id",
              "codes": "code_id", "trade_events": "event_key", "tiers": "key"}

    def __init__(self):
        self.tables: dict[str, list[dict]] = {"global_config": [], "code_batches": [],
                                              "codes": [], "trade_events": [], "tiers": []}
        self.budget_cas_fail = False

    def seed_tier(self, key: str, status: str = "live"):
        self.tables["tiers"].append({"id": 1, "key": key, "status": status})

    def seed_budget(self, value: int, *, key_missing: bool = False):
        if not key_missing:
            self.tables["global_config"].append(
                {"key": code_issue.BUDGET_KEY, "value": str(value)})

    # ── 请求处理 ──

    def handle(self, request: httpx.Request) -> httpx.Response:
        table = request.url.path.rsplit("/", 1)[-1]
        method = request.method
        params = {k: v for k, v in request.url.params.items()}
        if method == "GET":
            rows = list(self.tables.get(table, []))
            control = {"limit", "offset", "select", "order"}
            for k, v in params.items():
                if k in control:
                    continue
                want = v[3:] if v.startswith("eq.") else v
                rows = [r for r in rows if str(r.get(k)) == want]
            return _ok(rows)
        if method == "POST":
            doc = json.loads(request.read() or b"{}")
            uk = self.UNIQUE.get(table)
            if uk and any(r.get(uk) == doc.get(uk) for r in self.tables[table]):
                return httpx.Response(409, json={"message": "duplicate"})
            self.tables[table].append(doc)
            return httpx.Response(201, json=doc)
        if method == "PATCH":
            match: list[dict] = []
            for r in self.tables.get(table, []):
                ok = all(
                    (str(r.get(k)) == v[3:]) if v.startswith("eq.") else r.get(k) == v
                    for k, v in params.items()
                )
                if ok:
                    match.append(r)
            if self.budget_cas_fail and table == "global_config":
                match = []
            for r in match:
                r.update(json.loads(request.read() or b"{}"))
            return httpx.Response(200, json=match)  # return=representation
        if method == "DELETE":
            before = len(self.tables.get(table, []))
            self.tables[table] = [
                r for r in self.tables.get(table, [])
                if not all(
                    (str(r.get(k)) == v[3:]) if v.startswith("eq.") else r.get(k) == v
                    for k, v in params.items())
            ]
            return httpx.Response(200, json=[{}] * (before - len(self.tables[table])))
        return httpx.Response(405, json={"message": "method?"})


def _ok(rows: list) -> httpx.Response:
    return httpx.Response(200, json=rows)


def _tool(store: FakeStore) -> code_issue.CodeIssueTool:
    client = code_issue.PgRestClient(ENDPOINT, "test-key",
                                     transport=httpx.MockTransport(store.handle))
    return code_issue.CodeIssueTool(client)


def test_new_batch_success_writes_all_rows_and_deducts_budget():
    store = FakeStore()
    store.seed_tier("pro")
    store.seed_budget(10)
    tool = _tool(store)
    result = tool.new_batch("pro", days=30, count=3, channel="渠道A",
                            note="首发", created_by="ops")
    assert len(result["codes"]) == 3
    assert all(c.startswith("AC-") for c in result["codes"])
    assert len(store.tables["codes"]) == 3
    batch = store.tables["code_batches"][0]
    assert batch["count"] == 3 and batch["budget_consumed"] == 3
    assert batch["channel"] == "渠道A"
    budget = store.tables["global_config"][0]
    assert budget["value"] == "7"  # 10-3
    ev = store.tables["trade_events"][0]
    assert ev["event_type"] == "codes.issued"
    assert ev["payload"]["codes"] == result["codes"]
    # 码行纪律：source=admin、未绑定、显式 created_at（UTC 无时区后缀）
    row = store.tables["codes"][0]
    assert row["source"] == "admin" and row["user_id"] is None
    assert "+00:00" not in row["created_at"]


def test_budget_insufficient_refuses_whole_batch():
    store = FakeStore()
    store.seed_tier("pro")
    store.seed_budget(2)
    with pytest.raises(CodeIssueError, match="预算不足"):
        _tool(store).new_batch("pro", days=30, count=3, channel="", note="", created_by="ops")
    assert store.tables["codes"] == []          # 一枚码都不留下
    assert store.tables["code_batches"] == []
    assert store.tables["global_config"][0]["value"] == "2"


def test_budget_cas_mismatch_rolls_back_inserted_rows():
    store = FakeStore()
    store.seed_tier("pro")
    store.seed_budget(10)
    store.budget_cas_fail = True  # 扣减时并发失配
    with pytest.raises(CodeIssueError, match="已整体回收"):
        _tool(store).new_batch("pro", days=30, count=3, channel="", note="", created_by="ops")
    assert all(r["status"] == "revoked" for r in store.tables["codes"])
    assert store.tables["code_batches"] == []   # 批次单删行


def test_tier_must_be_live_in_db_not_code_dict():
    store = FakeStore()
    store.seed_tier("pro", status="planned")
    store.seed_budget(10)
    with pytest.raises(CodeIssueError, match="可发档位"):
        _tool(store).new_batch("pro", days=30, count=1, channel="", note="", created_by="ops")
    with pytest.raises(CodeIssueError, match="可发档位"):
        _tool(store).new_batch("diamond", days=30, count=1, channel="", note="", created_by="ops")


def test_days_guard_and_force():
    store = FakeStore()
    store.seed_tier("pro")
    store.seed_budget(10)
    tool = _tool(store)
    with pytest.raises(CodeIssueError, match="1–365"):
        tool.new_batch("pro", days=366, count=1, channel="", note="", created_by="ops")
    with pytest.raises(CodeIssueError, match="天数至少 1 天"):
        tool.new_batch("pro", days=0, count=1, channel="", note="", created_by="ops", force=True)
    tool.new_batch("pro", days=366, count=1, channel="", note="", created_by="ops", force=True)
    assert store.tables["codes"][0]["duration_days"] == 366


def test_revoke_only_unused_and_requires_reason():
    store = FakeStore()
    store.seed_budget(0)
    store.tables["codes"] = [
        {"code_id": "AC-U1", "status": "unused", "tier": "pro", "duration_days": 30},
        {"code_id": "AC-A1", "status": "active", "tier": "pro", "duration_days": 30,
         "user_id": 7},
    ]
    tool = _tool(store)
    with pytest.raises(CodeIssueError, match="必须附原因"):
        tool.revoke(["AC-U1"], "  ")
    done = tool.revoke(["AC-U1", "AC-A1", "AC-NOPE"], "渠道作废")
    assert done == 1
    assert store.tables["codes"][0]["status"] == "revoked"
    assert store.tables["codes"][1]["status"] == "active"  # 已激活不动
    ev = store.tables["trade_events"][0]
    assert ev["event_type"] == "codes.revoked"
    assert ev["payload"]["reason"] == "渠道作废"


def test_show_reconciliation_invariant_flags_mismatch(capsys):
    store = FakeStore()
    store.seed_budget(0)
    store.tables["code_batches"] = [
        {"batch_id": "CB-1", "tier": "pro", "duration_days": 30, "count": 3,
         "budget_consumed": 3, "channel": "", "note": "", "created_by": "ops",
         "created_at": "2026-10-01T00:00:00"},
    ]
    store.tables["codes"] = [
        {"code_id": f"AC-{i}", "batch_id": "CB-1", "status": "unused",
         "tier": "pro", "duration_days": 30, "user_id": None,
         "activated_at": None, "expires_at": None}
        for i in range(2)  # 单内 count=3，实插只有 2 → 对账不平
    ]
    _tool(store).show("CB-1")
    out = capsys.readouterr().out
    assert "对账不平" in out
    assert "三态" in out and "unused 2" in out


def test_show_code_reports_legacy_bucket(capsys):
    store = FakeStore()
    store.seed_budget(0)
    store.tables["codes"] = [
        {"code_id": "AC-OLD", "status": "unused", "tier": "pro", "duration_days": 30,
         "batch_id": None, "user_id": None, "activated_at": None, "expires_at": None},
    ]
    tool = _tool(store)
    tool.show_code(" ac-old ")
    out = capsys.readouterr().out
    assert "历史存量桶" in out
    with pytest.raises(CodeIssueError, match="不存在"):
        tool.show_code("AC-MISS")
