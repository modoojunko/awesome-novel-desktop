# 拆书题材 02–05 补齐（c-deconstruct-genre-fill）

## Why

拆书建书后题材页只有 01/02 有内容，03 绝对禁止、04 吃苦指数、05 本小说斗什么长期为空。根因是 `deconstruct_genre` 旧产物只有 `genre/tags/promise`，没有这三个字段；C 端建书映射也只写了 `promise_note`。

## What Changes

- `deconstruct/settings_map.py` 新增 `genre_extras(...)`：优先采用产物新字段 `core_promise/forbidden/cost_ratio/battlefield`；旧产物缺字段时，按题材承诺、主线 fullstory/arcs、世界观 power/cost 给可编辑推断起点。
- `intro_genre_body(...)` 接收 mainplot/world，一次返回题材五字段；`apply.import_book` 通过 `put_novel_genre` 一次写入。
- 候选标签映射稳定 `genre_vocab` id；推断字段写入 import warnings，SHALL NOT 留空。
- 回归：旧产物补齐、产物新字段优先、建书后五字段与 forbidden/battlefield 关联行断言；关键词收窄负向测试。

## Capabilities

### Modified Capabilities

- `deconstruct-book`: 建书逐字段回填与旧产物兼容——题材五字段映射与旧产物推断补齐。

## Design Impact

- 仅 C 端拆书建书出口；不改设定页 schema。
- 03/04/05 是推断起点而非原文事实，warning 提示作者在设定页确认/修改。

## Verification

- 桌面仓 #927（946548fd）：拆书套件 182 passed；带源全量 2695 passed/1 skipped；ruff 全过。
- 当前 demo live 库书 `f1e5f741` 已用新映射补齐，API 复查五字段；备份见修复记录。
