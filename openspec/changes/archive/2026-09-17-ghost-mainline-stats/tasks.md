# Tasks

- [x] 1.1 `novels/router.py` 列表聚合加 `Chapter.ghost_of.is_(None)` 过滤（字数/章数/归档数三计同批）——验证：`tests/test_novel_list_enrichment.py::test_ghost_chapters_excluded_from_stats` 绿
- [x] 1.2 测试：建书 2 章 → 写章/归档/回退 → 断言 `word_count`/`total_chapters` 回落到主线、`total_archives` 正确——验证：同文件 4 passed
- [x] 1.3 规范：`novel-workspace` 增量（卡片判据口径收紧为仅主线）——验证：`openspec validate ghost-mainline-stats --strict`
- [x] 1.4 回归：受影响测试（novel list enrichment）＋ruff 全绿——验证：本机一次性容器执行
