# c-chapter-default-words 任务清单

## 1. 后端：book-prefs KV 与端点

- [x] 1.1 `filesystem/paths.py`：新增 `BOOK_PREFS_PATH` / `BOOK_PREFS_KEY` 并进
  `route_relative_path`（专用键，不进 `PATH_TO_KEY`——不进通用 /settings/{type}）。
  验证：`tests/test_db_storage.py` 路由断言绿。
- [x] 1.2 `settings/book_prefs_model.py`（新）：区间/缺省常量单源、写入口归一
  （越界/非整数抛 ValueError）、读归一与生成链取值（未设置/损坏 → 2500）。
  验证：`tests/test_book_prefs.py::TestModel` 绿。
- [x] 1.3 `settings/book_prefs_router.py`（新）＋`main.py` 注册（先于 settings 通用
  路由）：GET 空态 `{}`；PUT 字段缺省＝无操作、null＝清除、越界/非整数 400；
  越权/不存在项目 404。验证：`tests/test_book_prefs.py::TestRouter` 绿。
- [x] 1.4 `write/chapter_writer.py`：`WORD_TARGET_*` 改为从 book_prefs_model 引入
  （历史名保留为别名，防两处各写一份）；`clamp_word_target(value, default=...)`；
  `build_chapter_context` 章纲未填时按本书偏好兜底。
  验证：`tests/test_chapter_writer_context.py::test_word_target_default_from_book_prefs`
  绿（含「至少 3000 字」进 user 素材与损坏值回落）。
- [x] 1.5 前后端区间/缺省对拍：`tests/test_shared_constants_parity.py` 新增
  `TestChapterWordTargetParity`（chapterTarget.ts ↔ book_prefs_model.py；写章别名同源）。
  验证：绿。

## 2. 前端：设置项与展示贯通

- [x] 2.1 `lib/chapterTarget.ts`（新，**登记 coverage-contract.ts**）：常量＋缓存读写＋
  变更订阅＋后端 load/save（先 PUT 成功才回写缓存）。验证：`__tests__/chapterTarget.test.ts`
  13 条绿、四支覆盖率 100%。
- [x] 2.2 `BookPrefsModal.tsx`：新增「章节默认字数」数字输入（500-6000/步进 100，
  `data-od-id="pref-word-target"`）；开启时从后端回灌（失败回落缓存）；保存先写后端，
  失败 toast 保持弹窗可重试。验证：tsc 零错、e2e modals-pr5 断言（后端落库＋回读，待
  起栈跑）。
- [x] 2.3 文案/校验/进度目标跟随：`OgPane.tsx`（opt 文案/placeholder/查看态默认，新
  prop `defaultWordTarget`）、`chapterForm.ts`（`ogFormIssues(form, defaultTarget?)`，
  clamp 用单源常量）、`ChapterWorkspace.tsx`（缓存同步读＋订阅＋项目切换回灌，传
  OgPane 与四处校验）、`useChapterData.ts`（`targetWords` 兜底＝本书默认）。
  验证：`__tests__/ogWordTarget.test.tsx` 4 条 + `chapterForm.promptGrid.test.ts` 新增
  动态文案用例 + `useChapterData.test.tsx`/`castMissDetector.test.tsx` 既有用例绿。

## 3. 回归与门禁

- [x] 3.1 前端全量：`npx vitest run --coverage` → 116 文件 / 1383 例绿，契约文件四支 100%。
  证据：`Test Files 116 passed / Tests 1383 passed`；chapterTarget.ts 行/支/函/语句 100。
- [x] 3.2 `npx tsc --noEmit` 零错；`npm run build` 零错（CI 门禁同口径）。
- [x] 3.3 后端全量：`pytest tests/ -q --timeout=30`（worktree、共享 venv 口径）。
  验证：汇总行贴 PR。
- [x] 3.4 `ruff check --extend-select F811,F821,F841 .`（0.16.3 钉版）零告警。
- [ ] 3.5 e2e `modals-pr5.spec.ts` 起栈跑（本会话未起 docker 栈）——改动仅为该 spec
  追加段落，未起栈自证；随发版链/常规 e2e 跑批复核。
- [ ] 3.6 原型先行缺口收口：`docs/design-c/prototypes/book.html` 的 `#modalPrefs`
  加该行 + `ADJUSTMENTS.md` 登记（本会话硬约束＝只改 client/；交设计侧会话）。

## 4. 用户复测口径（发版后）

- [ ] 4.1 改「章节默认字数」为 3200 → 新建/打开未填字数的章纲：提示与 placeholder
  显示 3200；生成正文提示词按至少 3200 字（可查 llm.log/提示词预览）。
- [ ] 4.2 未设置的书：一切仍是 2500（存量行为回归）。
