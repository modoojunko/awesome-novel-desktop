# c-library-genre-align — 实现任务

## 1. 原型/基线

- [x] 库页无 parity 基线（既有 ADJUSTMENTS 豁免）；drafts 原型不追补（评审基线为已合入版）；ADJUSTMENTS 追加登记。

## 2. 后端

- [x] `genres/theme_catalog.py`：新增 `THEME_NAMES`＋`normalize_theme()`（精确/双向包含/空）。
- [x] `library/service.py`：`clean_payload` 题材按目录校验归一（目录外 400 `invalid_genre`）；`_story_genre`（收录继承）与 `_deconstruct_genre`（拆书产物）同口径归一。
- [x] 测试：归一四例（精确/包含/反向包含/目录外）；写入口 400 与空值；收录继承目录内大类与历史自由文本归一（`TestGenreAlignment`）。

## 3. 前端

- [x] `CardEditorModal`：题材格 `<select>`（未分题材＋`THEMES`，与开书面板同源）。
- [x] 测试：选择器选项断言；保存值断言；既有用例值改目录内大类。

## 4. 门禁与回归

- [x] 后端 24 例（库域＋第三出口）绿、ruff 绿；前端全仓 **1962 例**绿、覆盖率契约四维 100%、tsc 绿。
- [x] e2e 既有桩用例的题材输入改 `selectOption("都市")`（本地跑通口径）。
- [x] 文案核对：400 文案指向开书题材目录（作者语言，无内部术语）。
