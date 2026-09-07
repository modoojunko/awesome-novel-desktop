# Design: add-refund-rebuy-guide 换档引导文案

## Context

选购页 CashierPage.vue 态一（选套餐）当前无任何"当前套餐"感知（免费列静态渲染）；已拍板的轻量路线（设计事实源：docs/prd/s-pay-refund-rebuy-guide-design.md）只需对生效期付费用户显示一条换档引导。后端 `GET /pay/license`（LicenseView：tier/remaining_sec/...）已存在，前端 `apiPayLicense()` 现成；e2e mock（api-handlers.ts）license 默认 `tier:'free'`。

## Goals / Non-Goals

**Goals:** 生效期付费用户在选购页看到"先退再买"三步引导与排队提醒；其余用户页面逐字节不变。
**Non-Goals:** 不动后端；不动购买/退款任何流程逻辑；不做差价/双按钮/退款实体（全部封存于搁置稿）；mock 层结构不动。

## Decisions

1. **数据源**：onMounted 时 `isLoggedIn` 才拉 `apiPayLicense()`，结果存 `license` ref；`hasActivePaidPlan = license && !['free','none'].includes(license.tier) && license.remaining_sec > 0`。请求失败 catch 静默（console.error，不弹错）——spec 的静默降级 scenario。
2. **渲染位置**：态一页头 sub 之后、活动横幅/时长 tab 之前，`v-if="hasActivePaidPlan"` 的 `.notice.info`；「我的订单」用既有路由 `/dashboard/orders` 的 `<router-link>`。
3. **文案单源**：整段文案写死在模板内（单处使用，不抽常量）；措辞以 PRD 方案稿 §2 为准（已用户批准）。
4. **e2e**：mock 默认 free 不触发——现有用例零影响；新增一个用例：`setLicense({tier:'pro', remaining_sec:...})` 后断言 notice 出现且含排队提醒文案（覆盖 spec 首个 scenario；后两个 scenario 由显示条件的 computed 单测覆盖或断言免费态不出现）。

## Risks / Trade-offs

- license 拉取给选购页加了一个请求：失败静默、非阻塞，风险可忽略。
- 现有 cashier e2e 若有 DOM 结构全量断言，notice 不出现（free mock）故不受影响。
