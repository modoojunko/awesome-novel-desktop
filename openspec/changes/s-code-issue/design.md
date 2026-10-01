# Design: s-code-issue

## Context

发码现状：S端 公网管理端点（admin_token 门）＋config.py 硬编码 TIER_POLICY 查时长；无单据、无总量约束。购买链路已是数据驱动（tiers/skus 表，订单冻结快照）。运营定位已拍板：一枚码=一份短时套餐；发码走本地脚本，不动 S端。生产库=CloudBase PG HTTP API（PostgREST 单表 CRUD，`TCB_PG_ENV_ID`/`TCB_PG_API_KEY`），无跨表事务；生产 DDL 为带外操作（既有做法），sqlite 侧走 ORM 建表。

## Goals / Non-Goals

- Goals：发码总量有预算硬约束；每批有单可查（三态＋对账）；档位/时长与购买同源且显式；S端 公网面零发码入口。
- Non-Goals：兑换端点设计（s-code-redeem）；S端 台账 UI（触发条件：第二个运营角色/渠道自助看数/周对账>10 分钟）；整批有效期、单人兑换上限、渠道结算价字段（理由见 proposal「明确不动」）；TIER_POLICY 整体退役（tier-plan-four-tiers）。

## Decisions

1. **脚本形态**：`scripts/code_issue.py`，Python 直连 PostgREST（import 复用 `app.infrastructure.repositories.pg_http` 客户端与 `global_config` 表名常量），凭据只从本机环境变量读（与 S端 生产同名 `TCB_PG_ENV_ID`/`TCB_PG_API_KEY`）。不做任何 HTTP 服务形态。
2. **预算账本与扣减顺序**：`global_config` 单键 `codes.issue.budget`（int 字符串，剩余张数）。`new-batch` 顺序＝**先插码行与批次单，后 CAS 扣预算**（`UPDATE global_config SET value=新值 WHERE key=... AND value=旧值`）；CAS 失败（预算不足/并发）→ 当场把本批码行置 revoked＋批次单删行，整批报错。选「先插后扣」而非「先扣后插」：扣了没插是静默资金损失，插了没扣是可当场回收的多余码——后者失败模式可自愈。残余风险（进程在插码后、回收前被杀）由对账不变式兜底（见 4）。
3. **批次单表**：`code_batches`（id 主键、batch_id=业务号 `CB-YYYYMMDD-xxxx`、tier、duration_days、count、channel、note、created_by、budget_consumed、created_at）。codes 加 `batch_id`（nullable；NULL=历史存量桶）。发放留痕复用 `trade_events`（event_key=`codes:{batch_id}:issued`，payload 带全批码号，order_no=None——列可空已核）。
4. **对账不变式**：`show` 每次对每张单校验 `count == budget_consumed == 实插码行数(不含作废回收残行)`，不平即输出 err 语气告警行；这是「先插后扣」残余风险与一切手工 SQL 的兜底探测。负债行恒输出：「在外未兑 N 张 / 合计 X 天（分 tier）」，人工红线不进系统。
5. **三态与 revoke 收窄**：脚本对批次码只承认 unused/active/revoked 三态（frozen/pending_activation 属订单码族，`show` 遇到即告警异常数据）。`revoke` 的 WHERE 恒带 `status='unused'`＋必填 `--reason` 落码行（复用 status_detail 或 note 列，apply 时按现有列定）；active 码请求作废直接拒绝。
6. **档位/时长**：`--tier` 白名单当场查 `tiers` 表（status='live'），拒绝时列出可发档位；`--days` 必填，1–365，`--force` 才放行超限。天数写批次与每枚码行 `duration_days`，兑换侧（s-code-redeem）按码行起算，已对齐。TIER_POLICY 在发码路径零引用（其本体与其他消费方不动）。
7. **S端 摘除**：删 `admin_api/codes.py` 与 `GenerateCodeRequest`/`QueryCodesRequest`；`test_web_api.py`/`conftest.py` 的发码种子改直灌 code_repo；admin_api 仅剩 deletion（admin_token 机制保留）。限流清单不动（这两端点本就不在 SENSITIVE_PATHS）。
8. **DDL 与自检**：sqlite 侧 ORM 模型（`models/code.py` 加 CodeBatchORM）随 create_all/alembic 走既有路径；`pg_schema.py` 自检清单登记 `code_batches` 表与 `codes.batch_id` 列；生产带外 DDL 两条 SQL 落 `docs/ops/`（建表＋ALTER），变更任务含「生产执行时人工核对」步骤。

## Risks / Trade-offs

- [脚本进程中断留下已插未扣的码] → 对账不变式每次 show 校验；残行三态里「凭空多的 unused 码」可被 show-code 定位、revoke 收拾。
- [global_config 被绕过直改] → 该 key 本就是运营权限的化身（能改库=能加预算），预算防的是失控与误操作，不是防持钥者；trade_events 留痕保证可追溯。
- [无跨表事务的窗口期] → 单请求单表是 PostgREST 语义边界；发码低频人工在场，回补逻辑＋对账足够，不值得为它引入事务网关。
- [脚本与 S端 各写各的 codes 行] → 唯一事实仍是码行本身；脚本只写 source=admin 族，订单族字段（order_id/grant_start）脚本零触碰。

## Migration Plan

顺序：DDL（sqlite+pg 登记）→ 脚本＋测试 → S端 摘除端点（同一批或其后均可，端点删除不影响兑换）→ 生产执行带外 DDL＋播预算种 → 发首批码冒烟（发 1 张→S端 兑换→三态翻转）。回滚：脚本与端点互不相依，任一回退都不影响码行数据；DDL 纯增量不回滚。

## Open Questions

（无——「出库标记」已被 PM 评审否决（生成即发放）；若未来出现分批出库场景，加列十分钟，不预付。）
