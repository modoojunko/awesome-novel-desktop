# 删书后任务不再显示已建书 — 实施任务

## 1. 后端读时校正

- [x] 1.1 `deconstruct/service.py`：新增 `live_book_ids(db, ids)`（一次 `select Novel.id where id in (…) and status != 'deleted'`）；
      `task_view(task, *, live_books=None)` 按 D1 判定并下发 `book_missing`；`list_tasks` 内部取集合后逐行套用。
      验证：单测三臂（书在 → 原样；书已删 → completed + book_id null + book_missing；无 book_id → 不变）。
- [x] 1.2 `deconstruct/router.py:get_task`：传入 `live_books`。验证：契约用例走一遍详情端点，断言删书后
      `status=completed`、`book_id=null`、`book_missing=true`。

## 2. 前端说明句

- [x] 2.1 `lib/deconstructApi.ts` 详情类型加 `book_missing?: boolean`；
      `TaskDetailPage.tsx` 在 `completed` 分支且 `book_missing` 时渲染 `notice info`「原建书已删除，可以重新建书」。
      验证：组件用例断言横幅不出现、说明句出现；无 book_missing 时不渲染。

## 3. 回归

- [x] 3.1 后端：`pytest tests/test_deconstruct_api.py tests/test_deconstruct_import_async.py -q`。
- [x] 3.2 前端：`npx vitest run --coverage`（覆盖率门禁）+ `tsc --noEmit`。
- [ ] 3.3 真机：删掉建出的书 → 详情横幅消失、说明句出现；点「选择去向 → 就建这本书」能重建。

## 4. 归档

- [ ] 4.1 delta sync + `openspec archive c-import-stale-book --yes`，validate 与基线对拍无新增红。
