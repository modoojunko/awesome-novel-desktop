## 1. 双端影响判定

- [ ] 1.1 双端影响判定：纯 S端 后端实现层重构，响应字节级同形、无界面改动——Design Impact「不适用」，skip_specs（行为由既有 test_payments_api 守卫）

## 2. 服务抽取

- [ ] 2.1 新增 `app/application/payments/skus_view.py`（build_skus_view：三态开关/selling_points/discount_display/price_fen/popular_sku/retired 过滤）——diff 贴进 change 目录
- [ ] 2.2 `get_skus` 收薄为 HTTP 适配（取仓储→调服务→包 code/data）——diff 贴进 change 目录
- [ ] 2.3 死变量 `rehearsal_list` 删除——grep 证实读后未用记录贴进 change 目录

## 3. 回归

- [ ] 3.1 S端 pytest 全量（含 test_payments_api）输出结论贴进 change 目录
- [ ] 3.2 ruff check 触碰文件输出结论贴进 change 目录
- [ ] 3.3 前端门禁不适用（判定依据见 1.1）
