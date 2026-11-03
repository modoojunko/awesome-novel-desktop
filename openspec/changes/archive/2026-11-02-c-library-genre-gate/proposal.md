# Proposal: c-library-genre-gate

## Why

真机实锤（boss 2026-11-02）：「现在有的角色缺字段啊，题材。不可能让都市的角色去修仙小说里面当角色吧」。三层问题：

1. **归一漏了**：拆书产物题材「灵异志怪」经 `normalize_theme` 归一出空串（目录规范名是「志怪/民俗灵异」，整名双向包含匹配不上词序），拆书入库的题材继承因此恒空——39 张角色卡全空题材。
2. **存量没补**：已入库的空题材卡没有回填机制。
3. **消费零门禁**：`apply_to_book`（用到新书／书内从库导入同一后端流）不校验题材，都市角色可复制进修仙书。

## What Changes

- **归一兜底**：`normalize_theme` 在精确/整名双向包含之后增加**组件匹配**（目录名按「/」拆分，任一组分出现在原文即命中，最长组件优先）。既有匹配语义不动，只在全部失配后兜底——「灵异志怪」→「志怪/民俗灵异」、「修真」→「仙侠/修真」。
- **存量回填**：`ensure_genre_backfill`——来源可解（拆书看任务产物 genre 维度、书来源看 story.genre，与收录同源）且题材为空的库卡条目补题材；**拍板口径同 c-kb-library-once-migration：不挂 boot、读面触达（知识库条目列表＋角色库卡列表）、幂等自熄**；解不出（手动卡、源已删）保持空＝跨题材通用。
- **跨题材硬门（boss 拍板选 A 硬拦）**：`apply_to_book` 校验卡题材与目标书题材同域才可落卡（两侧同走 normalize_theme；任一侧空放行）；不同域 400 `genre_mismatch` 可读文案。前端两弹窗按同口径过滤：用到新书只列同题材书（书题材未设放行），书内从库导入只列同题材卡（卡题材空放行）；全滤时空态给题材提示。
- **接口形状**：库卡与 `/novels` 列表各加 `genre_norm`（归一题材名）供前端同口径过滤；后端仍为权威校验。

## Impact

- specs: character-library（MODIFIED 角色卡的字段契约——归一补组件匹配＋存量回填场景；MODIFIED 用到新书——题材门）
- 代码：genres/theme_catalog.py、library/service.py（ensure_genre_backfill/apply_to_book/_card_view/list_cards）、kb/router.py、novels/router.py、libraryApi.ts、UseInNovelModal.tsx、ImportFromLibraryModal.tsx
- 测试：tests/test_library_genre_gate.py（8 钉）＋ characterLibraryBranches.test.tsx（题材门 4 钉）
