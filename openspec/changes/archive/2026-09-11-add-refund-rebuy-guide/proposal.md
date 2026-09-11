# Proposal: add-refund-rebuy-guide 换档引导文案（轻量路线）

## Why

「升级到更高档」的需求已拍板走轻量路线（09-07）：现有支付链路已支持"先按剩余时长退款、再买高档"，且与补差方案每天数同价、总天数更多——补差体系（升级差价/双入口/退款实体）整体封存（方案稿 docs/prd/s-pay-refund-rebuy-guide-design.md，两份搁置稿同目录）。唯余的用户缺口：**生效期用户不知道这条路径**，且直接下单高档会排队至原套餐到期后（原套餐退款成功前仍占起算日）——需要一句引导文案把路径和坑讲清。

## What Changes

- 选购页（CashierPage 态一）新增一条 `notice info`：对**已登录且有生效中付费档**的用户显示换档三步引导（先在「我的订单」申请退款 → 等退款成功 → 再选购高档立即生效），并明示"退款完成前下单会排队至原套餐到期后才计时"
- 显示条件：`license.tier ∉ {free, none}` 且 `remaining_sec > 0`；未登录/无套餐/接口失败不显示（onMounted 登录态才拉 `GET /pay/license`，失败静默）
- 「我的订单」为可点击出口，链现有路由 `/dashboard/orders`
- 随本变更一并入库：两份搁置 PRD（upgrade-proration / refund-entity，头部标注已搁置）、原型搁置演示态（cashier 升级双入口 3 态、refund 两腿 2 态）+ ADJUSTMENTS「搁置方案演示」登记

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `s-pay-cashier`: **ADDED** 需求「生效期用户换档引导」——选购页 SHALL 对有生效中付费档的登录用户显示"先退再买"三步引导与排队提醒；无生效档/未登录/接口失败 MUST NOT 显示；文案口径（动词开头/无内部术语/可点出口/info 语气）遵守 design-language

## Impact

- 前端 S端：`server/frontend/src/views/pay/CashierPage.vue`（+license 拉取与 computed、+一行 notice）；`e2e/mocks/api-handlers.ts` 默认 free 不触发 notice，现有用例零影响（新增 1 个 paid 档轻用例验证出现）
- 后端：**零改动**（复用既有 GET /pay/license）
- 法律四件套：不动（按剩余时长退款条款已有）
- Design Impact：S端 选购页新增一条 info 提示条（用户可见）；对象状态零新增（复用 license 投影）；不触碰两端共享段；文案级改动走实现侧自查（ADJUSTMENTS 登记），无需原型先行
