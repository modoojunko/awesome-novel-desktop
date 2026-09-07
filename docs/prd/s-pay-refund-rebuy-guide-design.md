# S端 换档引导文案（轻量路线）方案稿（停审批口）

日期：2026-09-07
状态：**待用户审核，未开工**
定位：**替代性轻量落地**——09-07 用户拍板：当前支付系统已可运行，不再大动作；《套餐升级按秒补差》（docs/prd/s-pay-upgrade-proration-design.md，**已搁置**）与《退款实体升格》（docs/prd/s-pay-refund-entity-design.md，**已搁置**）两案封存，"升级"需求改由「先退再买」现有链路承载，本变更只补一句引导文案。

---

## 1. 决策链与唯一要防的坑

- 公平性已核：退了重买与补差**每天数同价**（max 牌价 ¥2/天），退了重买总天数反而更多（重开完整周期 vs 保原到期日）——两案分析全文见两份搁置稿，不复述
- **唯一要防的坑**：原套餐退款成功前仍是"生效中"，此时下单买高档**不会立即生效**，会排队到原到期日之后才开始计时。文案必须引导三步走：**先退 → 等退款成功 → 再买高档**
- 已核实技术事实：`GET /pay/license` 返回 `LicenseView{tier, remaining_sec}`（登录态）；`effective_tier` 取已激活最高档（free/none/pro/max）；CashierPage 已有 session store 与 isLoggedIn；e2e mock 的 license 默认 `tier:'free'`（notice 不会在现有用例中意外出现）

## 2. 文案（唯一落地物）

**放置**：CashierPage.vue 态一（选套餐），页头 sub 之后、时长 tab 之前；`notice info` 语气条（既有词汇零新增）

**显示条件**：已登录 且 `license.tier ∉ {free, none}` 且 `remaining_sec > 0`（有生效中付费档）；未登录/无套餐/接口失败一律不显示

**文案**：

> **想换更高档？** 可先在「我的订单」对当前套餐申请退款（按剩余时长折算、未用部分原路退回），退款成功后再选购高档套餐，立即生效。提醒：退款完成前下单，新套餐会排队至原套餐到期后才计时。

口径自查：「申请退款/选购」动词 ✓；无内部术语 ✓；补救出口「我的订单」可点击 ✓；info 语气 ✓

## 3. 实现要点

- CashierPage.vue：+`license` ref；onMounted 时登录态才拉 `apiPayLicense()`（401/失败静默，license=null=no notice）；+`hasActivePaidPlan` computed
- 模板：一行 `v-if="hasActivePaidPlan"` 的 notice；「我的订单」链到现有路由 `/dashboard/orders`
- e2e：mock license 默认 free → 现有 cashier 用例零影响、mock 层不动；可选加一个 `setLicense(paid)` 轻用例验证 notice 出现（默认做，成本一行）
- 验证：`npm run build` + 本地 e2e（cashier spec）

## 4. 随本变更一并入库的处置项

| 项 | 动作 |
|---|---|
| 两份搁置 PRD（upgrade-proration / refund-entity） | 入库 docs/prd/，头部标注「已搁置 09-07，轻量路线替代」 |
| 原型 cashier 升级双入口 3 态、refund 两腿 2 态 | 入库保留 + ADJUSTMENTS 登「搁置方案演示」（防误读为在途设计） |
| openspec/changes/s-pay-refund-entity | 封存留盘不删（未跟踪），记忆标注封存原因 |

## 5. 不做什么

- 不动退款/购买任何后端逻辑；不动法律四件套（按剩余时长退款条款已有）
- 不做升级差价、不做双按钮、不做退款实体（全部封存于两份搁置稿）

## 6. 待拍板项

文案措辞一条（§2 引用块）——其余无。批准后走 openspec propose（Modified: s-pay-cashier，ADDED 一条引导需求）→ 开工。
