# Proposal: c-zhuque-quota-ledger — 朱雀额度本地台账

## Why

朱雀检测每月 50 万 token 免费额度是作者最关心的消耗资源，但腾讯云侧没有公开的余量查询 API（只有控制台累计用量页）。而每次检测/测试响应里的 `makers_models_usage.total_tokens`（官方口径：实际扣免费额度的字段）已经在本地逐次留痕进 `token_log`（operation=`zhuque-check`），只是：a) 没有任何端点/UI 把它按月聚出来给作者看；b) 连通性测试（classify("ping")）的真实消耗没有记账，台账偏低。本 change 把既有留痕升格为「本月已用/估算剩余」台账并补齐测试记账。

## What Changes

- **后端**：`GET /api/v1/zhuque/config` 状态响应新增 `usage` 块——`month_used_tokens`（自然月内 operation=`zhuque-%` 的 token_log 求和）/ `month_free_quota`（默认 500_000，env `ZHUQUE_MONTHLY_FREE_TOKENS` 可覆写）/ `month_remaining_tokens`（前者相减，负数截 0）。
- **后端**：`POST /api/v1/zhuque/test` 连通性测试把 classify 响应中的 `makers_models_usage.total_tokens` 以 `operation="zhuque-test"` 记入 token_log（此前漏记）。
- **后端**：写作模型用量汇总的五处 `operation != "zhuque-check"` 过滤泛化为 `NOT LIKE 'zhuque-%'`，使新增的 zhuque-test 同样不混写作用量。
- **前端**：朱雀配置卡（已配置态）`zg-stats` 中间统计卡由静态「50 万 token / 月」改为台账卡——本月已用量（含测试消耗）＋免费额度口径；数据来自 config 状态响应（检测/测试后的既有 refresh 自动刷新）；保留「查看用量 ↗」外链作为权威口径。
- **文案**：台账数字口径注明「本地估算，以腾讯云控制台为准」（同 Key 在他处使用、朱雀网页版试用不计入本地台账；腾讯侧按月重置时点未知）。

不改变：检测结果不落库边界、检测/测试的请求链路、未配置态版面、显示开关行为。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `zhuque-config`: 新增「额度台账」Requirement（配置状态响应 usage 契约＋已配置态台账卡展示与口径）；MODIFIED「朱雀 Key 单槽生命周期」Requirement——连接测试的实际消耗 SHALL 记入本地台账（既有全部场景保留）。

## Impact

- **后端**：`client/backend/zhuque/service.py`（get_config_status 扩展 usage、test_config 记账、新增月度聚合）、`client/backend/api_configs/service.py`（五处汇总过滤泛化）、常量 `ZHUQUE_MONTHLY_FREE_TOKENS`（zhuque/service.py，env 覆写）。
- **前端**：`client/frontend/src/components/api-config/ZhuquePanel.tsx`（台账卡）、类型 `ZqStatus`。
- **测试**：`client/backend/tests/test_zhuque.py`（usage 契约＋测试记账＋月界）；`client/frontend/src/__tests__/zhuqueConfig.test.tsx`（台账卡渲染）；`client/frontend/e2e/zhuque.spec.ts`（已配置态断言补台账卡，现有断言未钉死旧文案，无回归负担）。
- **不做兼容层**：`usage` 块为纯新增字段，旧前端读到不感知；无破坏性。

## Design Impact

- **受影响端**：仅 C端（S端无朱雀功能）。
- **受影响屏**：模型配置页（`/config`）→「朱雀 AI 检测」页签 → 已配置态配置卡的 `zg-stats` 统计行（中间一卡换内容，卡数与版式不变）。无新增弹层。
- **对象状态**：沿用既有组件词汇——`.zg-stats .st` 统计卡（mono 数字＋11px 灰说明）、`.lnk` 外链；无新状态档位，不触状态语言总表。
- **两端共享段**：不触碰（不新增/修改 base.css 令牌与基础组件类，纯内容位替换）。
- **原型先行**：需要——`docs/design-c/prototypes/model-config.html` 朱雀页签已配置态 `zg-stats` 中间卡同步改，ADJUSTMENTS.md 登记。
- **设计工件产出**：实现侧自查（内容位级改动，无新形态）。
- **语气词汇**：无新增语气档（台账为静态展示，不引入 notice/pill 新形态）。
