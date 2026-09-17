## Why

回退把章节转入旧稿支线后，书架列表的字数/章数/归档数聚合仍把这些支线章算进去，而工作台卷章树与右栏统计都已按「只算主线」过滤——同一本书在书架卡片和工作台内显示两个数字，且阶段标签（`stageFromChapters` 用 `total_chapters`/`total_archives`）可能与点开书后的落点自相矛盾（正是 novel-workspace 契约里明确禁止的场景）。2026-09-17 用户拍板口径：**主线变了后，只有在主线上的章才统计字数**。

## What Changes

- `GET /api/novels` 列表聚合（字数/章数/归档数）SHALL 只统计主线章（`ghost_of IS NULL`），与工作台卷章树（`list_volumes` 已过滤）和工作台全书字数同口径。
- 支线章的正文原样保留、可读，只是不参与书级统计；`total_archives` 本来就把支线章的归档状态改回 writing/outline（回退时），本次把字数与章数一并归主线。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `novel-workspace`：「Four-state workspace view machine」的卡片判据口径收紧——`total_chapters`/`word_count`/`total_archives` 均只统计主线章（旧稿支线不计入），保证卡片阶段与打开书后的落点、以及工作台内统计三者同结论。

## Impact

- 后端：`novels/router.py` 列表聚合查询加 `ghost_of IS NULL` 过滤（一处）。
- 前端：零改动（货架卡片继续消费同字段，只是数值口径变主线）。
- 测试：`tests/test_novel_list_enrichment.py` 新增支线排除用例（写章→归档→回退→断言字数/章数回落到主线）。
- 兼容性：无 schema 变化；已存在的分叉只体现在数值上，回退后自动归主线。
