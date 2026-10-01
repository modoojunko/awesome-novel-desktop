# Proposal: s-code-issue

## Why

激活码发放当前挂在 S端 公网管理接口上（`/api/generate_code`、`/api/query_codes`，仅 admin_token 门），是有意收窄的攻击面；且发码无单据、无总量约束（单次限 100 张但可无限次调），档位/时长查的是 config.py 硬编码 TIER_POLICY 字典而非数据库——与购买链路（tiers/skus 表）双源漂移，已实锤「发 tier=pro 得 0 天废码」坑。运营定位拍板：**一枚码=一份短时套餐**，发码走本地脚本＋预算制＋批次单据。

## What Changes

- **S端 摘除发码管理面**：删除 `POST /api/generate_code`、`POST /api/query_codes`（admin_api/codes.py 整文件、对应 DTO、既有测试改直灌种子；admin_api 只剩 deletion）。S端 公网面从此没有任何发码入口。
- **本地发码脚本**（`scripts/`，Python 直连 PostgREST，复用 `TCB_PG_ENV_ID`/`TCB_PG_API_KEY` 环境变量）：`new-batch`（生成整批入单）/ `show`（单内明细＋三态统计＋对账＋CSV）/ `show-code`（一枚码反查）/ `list`（单子列表）/ `revoke`（作废）/ `set-budget`（加预算）。
- **预算制（不能无限发码）**：`global_config` 键 `codes.issue.budget`＝剩余可发张数；脚本发码**先插码后扣预算**（CAS 扣减），扣失败当场回收刚插的码；`show` 每次跑对账不变式（单内 count＝budget_consumed＝实插行数）；作废不退预算（预算=累计发放上限）；加预算=显式 set-budget 动作。
- **批次单据（三态）**：新表 `code_batches`（tier/duration_days/count/channel/note/created_by/budget_consumed），codes 表加 `batch_id` 列（存量 NULL=历史存量桶）；每批写一条 trade_events（`codes.issued`，payload 带全批码号）。码的三态口径：**未兑换（unused）→已激活（active）／已作废（revoked）**——生成即发放，channel 即发放记录，不做「出库标记」动作。
- **档位/时长与购买同源**：`--tier` 对 **DB tiers 表**校验（status=live 才可发），不再查 TIER_POLICY；`--days` 必填显式、落批次与每枚码行（码行即合同），合理性护栏 1–365 天（超出须 `--force`，发码=短时套餐通道，年卡/永久走正式购买）。
- **作废语义收窄**：`revoke` 只允许 unused 且必填原因；已激活码的收回只走系统链（账号注销 revoke 链）或人工 SQL 留痕，不进脚本常规命令。
- **负债可视**：`show` 输出「在外未兑：N 张 / 合计 X 天（分 tier）」，运营定人工红线，不设系统硬顶。
- **明确不动**：兑换端点（s-code-redeem 已立项）零耦合；TIER_POLICY 本体保留（其他消费方照旧，整体退役归 tier-plan-four-tiers）；不做 S端 台账 UI、整批有效期、单人兑换上限、渠道结算价字段。

## Capabilities

### New Capabilities

- `code-issuance`: 发码运营通道——批次单据与三态台账、预算制与对账不变式、档位取 tiers 表＋天数显式（码行即合同）、发码面退出 S端 公网 API、作废只对未兑换码。

### Modified Capabilities

（无——specs 未钉过 generate_code/query_codes 端点；s-payments「到货-激活两段式」Requirement 约束的是台账行写入纪律（created_at UTC 口径），脚本直插同样受约束，不构成 requirement 变更）

## Impact

- **代码（S端 后端＋脚本，S端 前端/C端 零改动）**：
  - 删 `server/app/interfaces/admin_api/codes.py`；`dto.py` 删 `GenerateCodeRequest`/`QueryCodesRequest`；`server/tests/test_web_api.py`、`conftest.py` 发码用例改直灌种子。
  - 新 `scripts/code_issue.py`（复用 `pg_http` 客户端与 `MockTransport` 测试套路）。
  - 新 `code_batches` ORM 模型＋codes 模型加列；sqlite 侧建表；`pg_schema.py` 自检清单登记新表/新列（生产带外 DDL 操作单随 change 落 docs）。
- **数据**：带外 DDL＝建 `code_batches`＋`codes` 加 `batch_id`；`global_config` 播 `codes.issue.budget` 种。
- **测试**：pytest（脚本逻辑单测：预算 CAS/插码失败回补/对账不变式/revoke 收窄/三态统计；端点摘除后 admin_api 零引用对拍）；隔离栈冒烟：发一批→S端 页面「我的套餐」兑换→三态翻转。
- **安全**：service_role key 只落运营本机环境变量；S端 无发码端点后，激活码爆破面只剩兑换端点（s-code-redeem 已带限流）。

## Design Impact

- **受影响端**：S端 后端 only＋仓库脚本；**S端 前端、C端 零改动**。
- **受影响屏/弹层**：无（无任何 UI 变化；兑换侧用户界面归 s-code-redeem）。
- **对象状态**：无新增组件词汇/状态档位（三态是台账数据口径，非 UI 状态语言）。
- **共享段**：不触碰。
- **原型先行**：免（无 UI）。
- **设计工件产出**：实现侧自查。
