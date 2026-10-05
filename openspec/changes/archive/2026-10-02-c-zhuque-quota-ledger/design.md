# Design: c-zhuque-quota-ledger

## Context

留痕侧已在位：`zhuque/service.py:check_chapter` 把响应里的 `makers_models_usage.total_tokens`（官方口径＝实际扣免费额度）以 `operation="zhuque-check"` 经 `record_usage` 写 `token_log`（独立会话，失败仅告警）；`api_configs/service.py` 五处写作用量汇总已排除 `zhuque-check`。展示侧：`ZhuquePanel` 已配置态 `zg-stats` 三卡（上次测试/静态免费额度/查看用量外链），数据全部来自 `GET /v1/zhuque/config` 单次取数。腾讯侧无余量 API，控制台累计用量是唯一外部权威。

## Goals / Non-Goals

**Goals:**
- 配置状态响应一次带回月度台账三字段，前端零新增请求
- 连通性测试消耗与整章检测同口径入账，台账不偏低
- 朱雀消耗（含测试）继续与写作模型用量严格隔离

**Non-Goals:**
- 不做跨设备/跨渠道额度同步（同 Key 他处消耗、网页版试用无法感知，口径以「本地估算」兜住）
- 不做按月历史曲线、按章消耗明细（token_log 有 created_at，将来可加，本次不铺）
- 不动 429 额度耗尽的既有错误语义（`zhuque_quota` 仍是权威「用完」信号）

## Decisions

1. **契约：扩展 `GET /v1/zhuque/config`，不新开端点。**
   ZhuquePanel 的 `refresh()` 已在挂载、测试、保存后各调一次；台账字段搭车即得「检测/测试后数值自动更新」。备选（独立 `/v1/zhuque/usage`）多一次请求且要前端并联合并，无收益。

2. **聚合口径：`operation LIKE 'zhuque-%'` 前缀制，不枚举。**
   月度求和过滤 `user_id` ＋ `created_at >= 本月一日`（UTC，与 `get_usage_summary` 既有惯例一致）＋ operation 前缀。备选（只算 `zhuque-check`）会让测试消耗进不了台账，与本 change 目的相悖。

3. **测试记账 operation 用 `zhuque-test`，五处汇总过滤泛化为 `NOT LIKE 'zhuque-%'`。**
   比复用 `zhuque-check` 多一次机械改动（`api_configs/service.py` 五处），换来台账自描述（测试/检测可分）和未来 `zhuque-*` 操作自动豁免；比逐处加第二个 `!=` 干净。`LIKE` 通配无注入面（operation 是本仓受控词汇）。

4. **免费额度常量 `ZHUQUE_MONTHLY_FREE_TOKENS = 500_000` 放 `zhuque/service.py`，env `ZHUQUE_MONTHLY_FREE_TOKENS` 可覆写。**
   活动口径可能变，覆写免发版；不落 DB（无配置界面价值，避免与「以腾讯云为准」的文案口径打架）。

5. **前端：中间统计卡内容位替换，卡数/版式/CSS 不动。**
   `<b>` 显「12,340 / 50 万 token」（已用量千分位、quota 由前端把 500000 格式化为「50 万」，非整万值直接显千分位数字），`<span>` 显「本月已用 · 本地估算，以腾讯云控制台为准」。无新档位、无新组件词汇，原型只改这一处内容。
   **响应缺 `usage` 时（版本偏差/防御臂）回退渲染旧静态额度卡内容（「50 万 token / 月 · 免费额度（以腾讯云控制台为准）」）——不引入「—」占位**：`zhuqueConfig.test.tsx:264` 用 `getByText("—")` 精确匹配「上次连接测试」的空值占位（多节点即抛）、`:421` 断言卡片 textContent 不含「—」，新占位字符会同时打红这两个既有用例。

6. **未配置态 `usage` 照返。**
   台账按作者维度（token_log 行不随 Key 软删消失），同月重配后统计连续；前端未配置态不渲染台账卡（版面纪律不变）。配置卡删除 Key 后 token_log 外键为 `SET NULL`（api_config_id 置空），行仍在，聚合不受影响。

## Risks / Trade-offs

- [本地台账≠腾讯侧真值（他处消耗/网页版试用/月界时点）] → 文案钉死「本地估算，以腾讯云控制台为准」＋保留「查看用量」外链；429 仍是权威耗尽信号
- [token_log 不在备份/恢复范围，DB 损坏或换代后本地台账清零] → 口径「本地估算」可容；备份域不动（本次不扩 backup 能力）
- [月界用 UTC 与腾讯侧重置时点（疑为 UTC+8）有最多 8 小时错位] → 影响仅限每月头尾几小时的展示数字，口径「估算」已覆盖；不引时区配置
- [零 token 的 classify 响应（上游异常但 200）不记账] → 沿用 `record_usage` 既有零 token 早退纪律，视为无消耗，不算偏低
- [e2e/单测若钉死旧文案「50 万 token / 月」会假红] → 实勘 `zhuque.spec.ts` 与 `zhuqueConfig.test.tsx` 均未钉死该文案；实现时仍先 grep 确认

## Migration Plan

纯增量：新字段、新记账操作、内容位替换。无 DDL（token_log 既有表结构够用）、无数据迁移。回滚＝还原前端卡片与后端两处即可，残留 token_log 行无副作用（五处过滤泛化后依旧被隔离）。

## Open Questions

（无）
