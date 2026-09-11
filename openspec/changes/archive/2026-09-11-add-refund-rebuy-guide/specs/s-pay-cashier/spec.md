# s-pay-cashier 换档引导文案 Delta

## ADDED Requirements

### Requirement: 生效期用户换档引导

选购页 SHALL 对已登录且名下有生效中付费档（`GET /pay/license` 返回 `tier ∉ {free, none}` 且 `remaining_sec > 0`）的用户显示一条 info 提示条，引导换档三步：先在「我的订单」对当前套餐申请退款（按剩余时长折算、未用部分原路退回）→ 等退款成功 → 再选购高档套餐立即生效；提示条 MUST 明示"退款完成前下单，新套餐将排队至原套餐到期后才计时"。「我的订单」SHALL 为可点击出口（链现有订单页路由）。未登录、无生效付费档、或 license 接口失败时 MUST NOT 显示（接口失败静默降级，不打断选购主流程）。提示条为纯展示，MUST NOT 改变选购/支付主流程的任何交互与接口调用契约（license 拉取失败静默）。

#### Scenario: 生效期付费用户看到换档引导

- **WHEN** 已登录用户名下有生效中付费档（如 PRO 计时中）进入选购页
- **THEN** 时长 tab 上方显示 info 提示条，含"申请退款→等退款成功→再选购"三步与排队提醒，「我的订单」可点击跳转

#### Scenario: 免费档或未登录不显示

- **WHEN** 未登录用户、或名下无生效付费档（tier 为 free/none 或 remaining_sec=0）进入选购页
- **THEN** 不渲染该提示条，页面结构与既有契约逐字节一致

#### Scenario: license 接口失败静默降级

- **WHEN** `GET /pay/license` 请求失败或超时
- **THEN** 不渲染提示条、不弹错、不阻塞选购主流程（console 记录，用户无感知）
