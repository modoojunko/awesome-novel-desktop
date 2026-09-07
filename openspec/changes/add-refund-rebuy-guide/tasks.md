# Tasks: add-refund-rebuy-guide 换档引导文案

## 1. 前端实现

- [x] 1.1 CashierPage.vue：+license ref / hasActivePaidPlan computed / onMounted 登录态拉 apiPayLicense（失败静默）
- [x] 1.2 态一模板：v-if 提示条（notice info，三步引导+排队提醒+「我的订单」出口），文案按 PRD 方案稿 §2

## 2. 测试

- [x] 2.1 e2e：现有 cashier 用例零影响确认（mock 默认 free）；新增 paid 档用例断言 notice 出现且含排队提醒文案
- [x] 2.2 本地构建 npm run build 绿 + e2e（cashier spec）绿

## 3. 随单入库的处置项

- [x] 3.1 两份搁置 PRD（upgrade-proration / refund-entity）入库 docs/prd/ 并头部标注已搁置（从主 worktree 拷入 + 标注）
- [x] 3.2 原型搁置演示态入库（cashier 升级双入口 3 态、refund 两腿 2 态，从主 worktree 拷入）+ ADJUSTMENTS 登「搁置方案演示」
