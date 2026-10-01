#!/usr/bin/env python
"""发码运营脚本（s-code-issue）：发码唯一路径——S端 公网面零发码入口。

批次单（code_batches）＋预算制（global_config codes.issue.budget）＋三态台账
（unused → active / revoked，生成即发放，channel 即发放记录）。直连生产
PostgREST（CloudBase PG HTTP API），凭据与 S端 生产同源环境变量。

用法（server venv）：
  export TCB_PG_ENV_ID=... TCB_PG_API_KEY=...
  server/.venv/bin/python scripts/code_issue.py new-batch --tier pro --days 30 \
      --count 10 --channel 渠道A --note 首发活动 --created-by ops
  server/.venv/bin/python scripts/code_issue.py show --batch CB-20261001-0001 [--csv]
  server/.venv/bin/python scripts/code_issue.py show-code AC-XXXX-XXXX-XXXX-XXXX
  server/.venv/bin/python scripts/code_issue.py list [--csv]
  server/.venv/bin/python scripts/code_issue.py revoke --codes AC-... --codes AC-... --reason 渠道作废
  server/.venv/bin/python scripts/code_issue.py set-budget --value 100

护栏（spec code-issuance）：档位只认 tiers 表 status=live；天数 1–365（超出 --force，
发码定位=短时套餐）；先插码后扣预算（CAS），扣不动当场回收整批；作废只对 unused。
"""
from __future__ import annotations

import argparse
import secrets
import string
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from app.infrastructure.repositories.pg_http.client import PgRestClient  # noqa: E402

BUDGET_KEY = "codes.issue.budget"
BATCH_PREFIX = "CB-"
_DAYS_MAX = 365
_ERR = "✗"
_OK = "·"


class CodeIssueError(Exception):
    """运营可见失败（退出码 1）。"""


def _now_naive_iso() -> str:
    """显式 naive UTC（s-payments 台账行写入纪律，禁 DB 列默认时区漂移）。"""
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _gen_code_id() -> str:
    chars = string.ascii_uppercase + string.digits
    body = "-".join("".join(secrets.choice(chars) for _ in range(4)) for _ in range(4))
    return f"AC-{body}"


def _next_batch_id(client: PgRestClient) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    n = 1
    while True:
        candidate = f"{BATCH_PREFIX}{stamp}-{n:04d}"
        if not client.find_one("code_batches", {"batch_id": candidate}):
            return candidate
        n += 1


class CodeIssueTool:
    """脚本核心（测试注入 MockTransport 客户端）。"""

    def __init__(self, client: PgRestClient):
        self.c = client

    # ── 预算 ──

    def read_budget(self) -> int:
        row = self.c.find_one("global_config", {"key": BUDGET_KEY})
        try:
            return int(row["value"]) if row else 0
        except (TypeError, ValueError):
            return 0

    def set_budget(self, value: int) -> None:
        if value < 0:
            raise CodeIssueError("预算不能为负")
        row = self.c.find_one("global_config", {"key": BUDGET_KEY})
        if row is None:
            self.c.insert("global_config", {"key": BUDGET_KEY, "value": str(value)})
        else:
            self.c.update("global_config", {"key": BUDGET_KEY}, {"value": str(value)})
        print(f"{_OK} 预算已设为 {value} 张（加预算=显式动作，trade 台账不追溯）")

    # ── 发码 ──

    def _live_tiers(self) -> list[dict]:
        return self.c.find("tiers", {"status": "live"})

    def new_batch(self, tier: str, days: int, count: int, channel: str,
                  note: str, created_by: str, force: bool = False) -> dict:
        # 档位校验：与购买同源（tiers 表 status=live），不查代码字典
        tier_row = self.c.find_one("tiers", {"key": tier})
        if not tier_row or tier_row.get("status") != "live":
            live = ", ".join(t["key"] for t in self._live_tiers()) or "（无在售档位）"
            raise CodeIssueError(f"档位 {tier!r} 不在 tiers 表或非 live；可发档位：{live}")
        # 天数护栏：发码定位=短时套餐，1–365，超限须显式越权
        if not (1 <= days <= _DAYS_MAX) and not force:
            raise CodeIssueError(f"天数须 1–{_DAYS_MAX}（发码=短时套餐通道，年卡/永久走正式购买）；"
                                 f"确要发 {days} 天请加 --force")
        if days < 1:
            raise CodeIssueError("天数至少 1 天")
        if count < 1 or count > 500:
            raise CodeIssueError("张数须 1–500")
        budget = self.read_budget()
        if budget < count:
            raise CodeIssueError(f"预算不足：剩余 {budget} 张，申请 {count} 张；"
                                 f"加预算：set-budget --value 新剩余值")

        # 先插码与批次单，后扣预算（CAS）；扣不动当场回收整批
        batch_id = _next_batch_id(self.c)
        now = _now_naive_iso()
        code_ids: list[str] = []
        try:
            self.c.insert("code_batches", {
                "batch_id": batch_id, "tier": tier, "duration_days": days,
                "count": count, "channel": channel, "note": note,
                "created_by": created_by, "budget_consumed": count,
                "created_at": now,
            })
            seen: set[str] = set()
            while len(code_ids) < count:
                cid = _gen_code_id()
                if cid in seen:
                    continue
                seen.add(cid)
                self.c.insert("codes", {
                    "code_id": cid, "tier": tier, "duration_days": days,
                    "status": "unused", "status_detail": "unused",
                    "user_id": None, "source": "admin", "order_id": None,
                    "grant_start": None, "batch_id": batch_id,
                    "created_at": now, "created_by": "admin",
                })
                code_ids.append(cid)
            self.c.insert("trade_events", {
                "event_key": f"codes:{batch_id}:issued",
                "event_type": "codes.issued",
                "order_no": None,
                "payload": {"codes": code_ids, "tier": tier, "duration_days": days,
                            "channel": channel, "note": note, "operator": created_by,
                            "source": "issue"},
                "created_at": now,
            })
        except Exception as e:  # 插码中途失败：回收已插码行，整批失败
            self._rollback_batch(batch_id)
            raise CodeIssueError(f"批次 {batch_id} 写库失败已回收：{e}") from e

        rows = self.c.update_cas(
            "global_config",
            {"key": BUDGET_KEY, "value": str(budget)},
            {"value": str(budget - count)},
        )
        if rows == 0:
            self._rollback_batch(batch_id)
            raise CodeIssueError(
                f"预算被并发改动（读时 {budget}，CAS 失配），批次 {batch_id} 已整体回收；请重试")
        print(f"{_OK} 批次 {batch_id}：{count} 张 · {tier} · {days} 天 · 渠道={channel or '-'}")
        for cid in code_ids:
            print(f"  {cid}")
        print(f"{_OK} 预算剩余 {budget - count} 张（本批消耗 {count}）")
        return {"batch_id": batch_id, "codes": code_ids}

    def _rollback_batch(self, batch_id: str) -> None:
        """插码后预算扣减失败/写库中断的当场回收：码行置 revoked、批次单删行。"""
        try:
            self.c.update("codes", {"batch_id": batch_id}, {
                "status": "revoked", "status_detail": "revoked"})
            self.c.delete("code_batches", {"batch_id": batch_id})
        except Exception:
            print(f"{_ERR} 回收批次 {batch_id} 失败——残留行可用 revoke 清理，"
                  f"show 会以对账告警暴露", file=sys.stderr)

    # ── 台账 ──

    def show(self, batch_id: str, csv: bool = False) -> None:
        batch = self.c.find_one("code_batches", {"batch_id": batch_id})
        if not batch:
            raise CodeIssueError(f"批次 {batch_id} 不存在")
        rows = self.c.find("codes", {"batch_id": batch_id}, sort=[("created_at", "asc")])
        self._print_batch(batch, rows, csv=csv)
        # 对账不变式：单内 count = budget_consumed = 实插码行数（不平即告警）
        if batch["count"] != batch["budget_consumed"] or batch["count"] != len(rows):
            print(f"{_ERR} 对账不平！单内 count={batch['count']} · "
                  f"预算消耗={batch['budget_consumed']} · 实插行数={len(rows)} —— 立即核查")

    def list_batches(self, csv: bool = False) -> None:
        batches = self.c.find("code_batches", sort=[("created_at", "desc")])
        if csv:
            print("batch_id,tier,days,count,channel,created_by,created_at")
            for b in batches:
                print(f"{b['batch_id']},{b['tier']},{b['duration_days']},{b['count']},"
                      f"{b.get('channel','')},{b.get('created_by','')},{b['created_at']}")
            return
        if not batches:
            print("(无批次)")
            return
        for b in batches:
            print(f"{b['batch_id']}  {b['tier']:<10} {b['duration_days']:>4}天 × {b['count']:>3}张"
                  f"  渠道={b.get('channel') or '-'}  by {b.get('created_by') or '-'}"
                  f"  {str(b['created_at'])[:16]}")
        self._print_liability()

    def show_code(self, code_id: str) -> None:
        code = self.c.find_one("codes", {"code_id": code_id.strip().upper()})
        if not code:
            raise CodeIssueError(f"码 {code_id} 不存在")
        batch = (self.c.find_one("code_batches", {"batch_id": code["batch_id"]})
                 if code.get("batch_id") else None)
        print(f"码       {code['code_id']}")
        print(f"状态     {code['status']}"
              + (f"（{code['status_detail']}）" if code.get("status_detail") else ""))
        print(f"档位/时长 {code['tier']} · {code['duration_days']} 天")
        if batch:
            print(f"批次     {batch['batch_id']}（{batch.get('channel') or '-'} · "
                  f"{batch.get('note') or '-'} · by {batch.get('created_by') or '-'}）")
        else:
            print("批次     （无——历史存量桶）")
        print(f"激活     用户={code.get('user_id') or '-'}  于 {code.get('activated_at') or '-'}")
        print(f"起算/到期 {code.get('grant_start') or '-'} → {code.get('expires_at') or '-'}")

    def revoke(self, code_ids: list[str], reason: str) -> int:
        if not reason.strip():
            raise CodeIssueError("作废必须附原因（--reason），半年后要有人记得为什么")
        done = 0
        now = _now_naive_iso()
        for raw in code_ids:
            cid = raw.strip().upper()
            code = self.c.find_one("codes", {"code_id": cid})
            if not code:
                print(f"{_ERR} {cid}：不存在，跳过")
                continue
            if code["status"] == "active":
                print(f"{_ERR} {cid}：已激活并绑定用户（uid={code.get('user_id')}），"
                      f"拒绝作废——已激活权益收回仅限系统链或人工 SQL 留痕")
                continue
            if code["status"] != "unused":
                print(f"{_ERR} {cid}：状态 {code['status']}，只可作废未兑换（unused）的码")
                continue
            self.c.update_cas("codes", {"code_id": cid, "status": "unused"}, {
                "status": "revoked", "status_detail": "revoked"})
            self.c.insert("trade_events", {
                "event_key": f"codes:{cid}:revoked",
                "event_type": "codes.revoked",
                "order_no": None,
                "payload": {"reason": reason, "source": "issue_revoke",
                            "batch_id": code.get("batch_id")},
                "created_at": now,
            })
            print(f"{_OK} {cid}：已作废（原因：{reason}）")
            done += 1
        print(f"{_OK} 作废 {done}/{len(code_ids)} 张；预算不退（预算=累计发放上限）")
        return done

    # ── 内部 ──

    def _print_batch(self, batch: dict, rows: list[dict], csv: bool) -> None:
        if csv:
            print("code_id,tier,days,status,user_id,activated_at,expires_at")
            for r in rows:
                print(f"{r['code_id']},{r['tier']},{r['duration_days']},{r['status']},"
                      f"{r.get('user_id') or ''},{r.get('activated_at') or ''},"
                      f"{r.get('expires_at') or ''}")
            return
        print(f"批次 {batch['batch_id']}：{batch['tier']} · {batch['duration_days']} 天 × "
              f"{batch['count']} 张 · 渠道={batch.get('channel') or '-'} · "
              f"{batch.get('note') or '-'} · by {batch.get('created_by') or '-'} · {batch['created_at']}")
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        summary = " · ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "（无码行）"
        print(f"三态：{summary}")
        for r in rows:
            user = r.get("user_id") or "-"
            print(f"  {r['code_id']}  {r['status']:<8} 用户={user}  "
                  f"{str(r.get('activated_at') or '-')[:16]} → {str(r.get('expires_at') or '-')[:10]}")

    def _print_liability(self) -> None:
        """在外未兑（unused）负债合计：张数＋Σ天数，分 tier。人工红线不进系统。"""
        unused = self.c.find("codes", {"status": "unused"})
        by_tier: dict[str, int] = {}
        for r in unused:
            by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + int(r["duration_days"])
        days_total = sum(by_tier.values())
        detail = "，".join(f"{k} {v} 天" for k, v in sorted(by_tier.items())) or "0"
        print(f"在外未兑：{len(unused)} 张 / 合计 {days_total} 天（{detail}）"
              f"——未兑现的权益负债，人工红线自行把控")


def _build_client() -> PgRestClient:
    import os
    env_id = os.getenv("TCB_PG_ENV_ID", "")
    key = os.getenv("TCB_PG_API_KEY", "")
    endpoint = os.getenv("TCB_PG_ENDPOINT", "") or (
        f"https://{env_id}.api.tcloudbasegateway.com/v1/rdb/rest" if env_id else "")
    if not endpoint or not key:
        raise CodeIssueError("需要环境变量 TCB_PG_ENV_ID 与 TCB_PG_API_KEY（或 TCB_PG_ENDPOINT）")
    return PgRestClient(endpoint, key)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="发码运营脚本（s-code-issue）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new-batch", help="生成一批码（先插码后扣预算，含批次单与发放留痕）")
    p_new.add_argument("--tier", required=True, help="档位 key（对 tiers 表 status=live 校验）")
    p_new.add_argument("--days", required=True, type=int, help="套餐天数（1–365，超限 --force）")
    p_new.add_argument("--count", required=True, type=int, help="张数（1–500）")
    p_new.add_argument("--channel", default="", help="发放渠道/对象（即发放记录）")
    p_new.add_argument("--note", default="", help="备注（可写结算价等）")
    p_new.add_argument("--created-by", default="ops", help="操作人")
    p_new.add_argument("--force", action="store_true", help="越过 365 天护栏（发码=短时套餐通道）")

    p_show = sub.add_parser("show", help="批次明细＋三态统计＋对账校验")
    p_show.add_argument("--batch", required=True)
    p_show.add_argument("--csv", action="store_true")

    p_sc = sub.add_parser("show-code", help="一枚码反查批次/状态/归属/激活时间")
    p_sc.add_argument("code")

    p_ls = sub.add_parser("list", help="批次列表＋在外未兑负债合计")
    p_ls.add_argument("--csv", action="store_true")

    p_rv = sub.add_parser("revoke", help="作废未兑换码（必附原因；已激活拒绝）")
    p_rv.add_argument("--codes", required=True, nargs="+")
    p_rv.add_argument("--reason", required=True)

    p_sb = sub.add_parser("set-budget", help="显式设置剩余可发张数（加预算=有意动作）")
    p_sb.add_argument("--value", required=True, type=int)

    args = ap.parse_args(argv)
    try:
        tool = CodeIssueTool(_build_client())
        if args.cmd == "new-batch":
            tool.new_batch(args.tier, args.days, args.count, args.channel,
                           args.note, args.created_by, force=args.force)
        elif args.cmd == "show":
            tool.show(args.batch, csv=args.csv)
        elif args.cmd == "show-code":
            tool.show_code(args.code)
        elif args.cmd == "list":
            tool.list_batches(csv=args.csv)
        elif args.cmd == "revoke":
            tool.revoke(args.codes, args.reason)
        elif args.cmd == "set-budget":
            tool.set_budget(args.value)
    except CodeIssueError as e:
        print(f"{_ERR} {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
