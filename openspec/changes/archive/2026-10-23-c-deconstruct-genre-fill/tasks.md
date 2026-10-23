# c-deconstruct-genre-fill · tasks

## 1. 映射

- [x] 1.1 `settings_map.genre_extras`：产物新字段优先，旧产物按题材/主线/代价推断 core_promise/forbidden/cost_ratio/battlefield
- [x] 1.2 `intro_genre_body` 接收 mainplot/world，返回题材五字段
- [x] 1.3 `apply.import_book` 一次写 core_promise/promise_note/forbidden_list/cost_ratio/battlefield；标签映射 genre_vocab id
- [x] 1.4 推断字段写 warning；关键词收窄（查/命/伤/村/爱 → 多字词）

## 2. 验证

- [x] 2.1 单测：旧产物补齐、产物字段优先、普通都市文本不误判
- [x] 2.2 集成测试：建书后五字段与 forbidden/battlefield 关联行
- [x] 2.3 桌面仓 #927（946548fd）：拆书套件 182 passed；带源全量 2695 passed/1 skipped；ruff 全过
- [x] 2.4 demo live 书 `f1e5f741` 修复并 API 复查

## 3. 归档

- [x] 3.1 归档本 change 并 sync `deconstruct-book` 主 spec
