# Tasks: c-library-genre-gate

## 1. 归一兜底

- [x] 1.1 `normalize_theme` 组件匹配兜底（「/」拆分、最长命中、既有语义不动）
- [x] 1.2 归一用例钉（灵异志怪/仙侠修真/修真→目录名；都市修仙/精确/目录外不变）

## 2. 存量回填

- [x] 2.1 `ensure_genre_backfill`：拆书来源取任务产物 genre、书来源取 story.genre（与收录同源）→ 补 genre＋concept_id
- [x] 2.2 两读面挂点（kb 条目列表＋角色库卡列表），幂等自熄、失败降级
- [x] 2.3 回填钉（拆书/书来源补上、手动卡与源已删保持空、读面挂点即触发）

## 3. 跨题材硬门

- [x] 3.1 `apply_to_book` 题材门（同域放行；任一侧空放行；不同域 400 genre_mismatch）
- [x] 3.2 库卡 `_card_view` 与 `/novels` 富化各加 `genre_norm`
- [x] 3.3 前端：UseInNovelModal 只列同题材书（含题材空态文案）；ImportFromLibraryModal 只列同题材卡（含题材空态文案）
- [x] 3.4 门禁钉（跨题材拒/同题材放/通用放/书未设放）；前端题材门 4 钉

## 4. 验收与合入

- [x] 4.1 后端全量 pytest 绿＋ruff 绿；前端全量 vitest --coverage 绿
- [x] 4.2 openspec validate 绿
- [ ] 4.3 真机：39 张卡补成「志怪/民俗灵异」；跨题材用到新书被拦（合 main 装包后验）
- [x] 4.4 sync＋归档随实现 PR 走
