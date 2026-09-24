## Context

`get_skus`（web_api/payments.py:75-133）现状：函数体内联 SkuRepo/TierRepo/config_repo 组装＋三态开关读取＋`_selling_points` 局部函数＋折扣/价格换算＋popular 选择。同文件其余端点（create_order/refund 等）已走 `app/application/payments/*` 服务。行为守卫：`tests/test_payments_api.py`。

## Goals / Non-Goals

**Goals:**

- 目录组装规则单点化（application 层），接口层收薄为 HTTP 适配。

**Non-Goals:**

- 不改响应契约（Z.4 SkusView 字段/形状零变化）。
- 不动 create_order/refund 等已服务化端点。
- 不迁移 landing（landing 未复制这些规则，无重复面）。

## Decisions

**D1：服务签名收仓储对象（与 create_order 同风格），不收 db。**
`build_skus_view(sku_repo, tier_repo, config_repo)`——依赖显式、测试可直接喂 fake repo。备选（已弃）收 db 自建仓储：签名隐含实现。

**D2：删除死变量 `rehearsal_list`。**
读后未用（本轮复审实勘）；若未来需要「彩排名单」语义应以其自身的规格立项。

## Risks / Trade-offs

- [响应字段遗漏/顺序变化] → 纯搬运＋既有 API 测试逐键断言兜底。

## Migration Plan

单 commit 搬运；回滚 = revert。
