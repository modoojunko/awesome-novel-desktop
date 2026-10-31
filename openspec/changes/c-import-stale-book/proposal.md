## Why

真机反馈：建出的书在书架删掉后，拆书任务详情仍显示「已建书 · 打开这本书」，点进去 404。
日志实证（v0.44.3，本机）：

```
13:35:41 DELETE /api/novels/96cd359e…  200   ← 书被删
13:35:56 GET    /api/novels/96cd359e…  404   ← 详情横幅仍在打开这本已删的书
```

根因：`import-book` **受理时**有校验（幂等键指向已删书 → 解绑 → 按勾选重建），但**读侧没有**——
`service.task_view` 与清单摘要把 `task.book_id` 原样下发，前端 `imported` 分支只要看到状态就渲染
「已建成 + 打开这本书」，于是删书后留下一条死链，任务状态也停在「已建书」。

## What Changes

- **读时校正幂等键**：`task_view` 与任务清单摘要 SHALL 校验 `book_id` 指向的书是否存在且未软删；
  已删/不存在时 SHALL 返回 `book_id: null`、`book_missing: true`，并把状态从 `imported`/
  `import_failed` 回落到 `completed`（回到「已完成 · 待选去向」，可重新建书）。
- **清单批量校验**：列表按 `book_id` 集合一次查询，SHALL NOT 逐行查询。
- **前端说明**：任务详情在 `book_missing` 时 SHALL 给一句「原建书已删除，可以重新建书」，
  SHALL NOT 再渲染「已建书」横幅与死链按钮。
- 不改受理侧逻辑（它已正确处理删书后重建），不改建书幂等语义。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `deconstruct-book`：「建书出口」新增一条——幂等键指向已删/不存在的书时，**读侧** SHALL 视为未建书
  （状态回落 `completed`、不下发 book_id、带 `book_missing` 标记），与受理侧的「键失效即重建」同口径。

## Design Impact

- **受影响端**：C端。
- **受影响屏**：拆书任务详情（删书后横幅消失、改显示一句说明）、任务清单行状态（`imported` → `completed`）。
- **对象状态**：沿用 `notice info` 与既有 pill 语气，不新增令牌/类名/胶囊形态。
- **共享段**：零改动。**原型先行**：不需要（无版式变化）。**设计工件产出**：实现侧自查。

## Impact

- **后端**：`deconstruct/service.py`（`task_view` / `list_tasks` 读时校正 + 批量校验）、
  `deconstruct/router.py`（详情端点传入有效书 id 集合）。
- **前端**：`lib/deconstructApi.ts`（类型加 `book_missing`）、`TaskDetailPage.tsx`（说明句）。
- **数据**：零 schema 变更；不改库里的 `book_id`（只在读侧判定），受理侧仍按现逻辑解绑重建。
