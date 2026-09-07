# docs/design-s/prototypes —— S端 界面原型资产

> S端 首个原型目录（openspec: s-pay-ui-design，2026-08-28 立）。自包含 HTML，双击即可评审。

## 文件

| 文件 | 屏 | 状态 |
| --- | --- | --- |
| `cashier.html` | 购买收银台 | 选套餐（时长主轴·免费/PRO/MAX 三档对比；常态/首购活动/MAX 未上架/生效期升级双入口四变体）/ 等待支付（普通单·升级单）/ 已到货 / 已升级（自动换档·无激活环节）/ 已过期 / 下单失败 / 核对中 / 支付失败反馈 / 未登录（右上切换） |
| `orders.html` | 控制台·订单记录 | 六种订单状态行 + 空态（右上切换） |
| `order-detail.html` | 订单详情 | 六状态详情（信息全量 + 状态相关操作聚合；退款进度区块随有退款单显示） |
| `refund.html` | 退款申请 | 折算预览 / 确认弹层 / 处理中 / 已退款 / 拒绝态（右上切换）；升级单两腿退款两态（两腿明细+原套餐不恢复，配 s-pay-upgrade-proration） |
| `invoice.html` | 发票详情 | 可打印版式（@media print 隐藏工具栏）+ 蓝字/红冲两种状态 |
| `devices.html` | 设备管理 | 额度头 + 设备行 + 解绑（实现期弹窗确认） |
| `account-deletion.html` | 注销账号（openspec: account-deletion） | 设置页入口 / 向导（后果清单 / 权益处置二选一 / 密码确认·含错误态）/ 提交成功 / 撤销期控制台 / 撤销确认·成功 / 已注销之后（右上切换，每态标注 spec Requirement）；配套故事地图 `../account-deletion-story-map.md` |
| `storymap.html` | 购买旅程故事地图 | 入口池 → 八阶段主线 → 四条典型路径（评审导航图） |
| `ADJUSTMENTS.md` | 偏差登记簿 | 每个原型的偏差与非基线元素登记 |

## 与 design-c（C端 原型）的差异

- **无像素 parity 门禁**：cross-end.html 既定裁决——S端 无一对一基线场景，证据 = 实现期"原型 ↔ 实现截图"对照入 change 目录；因此本目录**没有** baselines/、没有 design:check 消费方
- **词汇同源**：原型内联样式取自 `server/frontend/src/design/base.css` 共享段（@cross 段，与 C端 逐字同源）+ S端 本地段（.panel 家族 / .notice 四语气），登记簿注明来源
- **lint 不扫原型**：`server/frontend/scripts/design-lint.mjs` 只扫 `src/`；原型词汇合规靠本 change 的自查门禁（tasks 3.1）与实现期 lint 兜底

## 评审与实现期用法

1. **评审**：双击打开 HTML，右上角切换器浏览全部状态（切换器是非基线元素，截图对照时排除，已登记 ADJUSTMENTS）
2. **实现对照**：实现 change（s-wxpay-native）的验收 = 每屏实现截图 vs 原型对照图，入 change 目录 `evidence/`
3. **改口径**：资金数字与折算示例集中在每个文件顶部的 `MOCK` 常量区；业务口径变更先改 `docs/prd/s-payment-explore.md`，再同步原型 MOCK 区并在 ADJUSTMENTS 登记
