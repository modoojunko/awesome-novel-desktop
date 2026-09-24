## Why

`/api/pay/skus` 的业务规则（支付三态开关、折扣展示换算、热门位选择、档位过滤/映射）长在接口层 `web_api/payments.py:75-133`——与同文件其余端点「interfaces 薄适配 → application 服务」的范式不一致（复审 P2：业务规则长在接口层）。规则同域（payments 定价/目录展示）但散在 HTTP 处理函数体内，无法被其它入口（管理端、未来的 landing 数据源）复用。

## What Changes

- 新增 `app/application/payments/skus_view.py`：`build_skus_view(sku_repo, tier_repo, config_repo)` 承载全部目录组装规则（三态开关、selling_points 解析、discount_display/price_fen 换算、popular_sku 选择、retired 档位过滤）。
- `web_api/payments.py` 的 `get_skus` 收薄为「取仓储 → 调服务 → 包 `{code:0, data}`」HTTP 适配。
- 顺带删除死变量 `rehearsal_list`（读后未用）。
- 行为零变化：响应字节级同形（既有 payments API 测试为守卫）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——纯实现层重构，`skip_specs: true`：对外响应形状/语义零变化，既有 `test_payments_api.py` 即行为守卫。）

## Design Impact

- 不适用：无任何界面改动。

## Impact

- `server/app/interfaces/web_api/payments.py`（收薄）、`server/app/application/payments/skus_view.py`（新）。
- 门禁：S端 pytest 全量（payments API 用例即守卫）＋ ruff。
