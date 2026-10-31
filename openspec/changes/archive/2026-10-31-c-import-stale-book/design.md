## Context

`import-book` 受理侧已有幂等键校验（`router.import_book`：书已删 → 解绑 → 按勾选重建），
但读侧没有：`service.task_view` 直接回 `task.book_id`，`list_tasks` 同理。前端 `imported`
分支只看状态就渲染「已建成 + 打开这本书」，于是删书后留下死链（日志实证 404）。

现有代码位置：`deconstruct/service.py:task_view`（同步，无 db 入参）、`list_tasks`（有 db，
逐行构造 dict）、`deconstruct/router.py:get_task`（调 `task_view`）。

## Goals / Non-Goals

**Goals:** 删书后任务回到「已完成 · 待选去向」，详情不再给死链；清单行状态同步回落。
**Non-Goals:** 不改受理侧逻辑；不改库里的 `book_id`（只在读侧判定）；不做「删书时反向清理任务」的写路径。

## Decisions

**D1 · 读时校正放 service，用「有效书 id 集合」入参**
`task_view(task, *, live_books: set[str] | None = None)`：传入集合时，`book_id` 不在集合里即判
`book_missing`（`book_id=None`，状态 `imported|import_failed → completed`）；不传集合时行为与今天一致
（其它调用方/测试不受影响）。`list_tasks` 内部自己取集合：`select Novel.id where id in (book_ids)
and status != 'deleted'` 一次查询，逐行套同一判定。

**否掉的替代**：把 `task_view` 改成 async 并在内部查库（调用方与测试都要跟着改，且列表会退化成 N 次查询）。

**D2 · 前端只加一句说明，不加新状态**
后端把状态回落成 `completed` 后，「已建书」横幅自然不渲染（它挂在 `status === "imported"` 上）。
详情在 `book_missing` 时补一条 `notice info`：「原建书已删除，可以重新建书」。不新增胶囊/语气。

## Risks / Trade-offs

- [列表多一次查询] 每页一次 `id in (...)`，可忽略；空集合直接跳过。
- [旧客户端] 老前端不认 `book_missing`：状态已回落 `completed`，横幅同样不渲染 → 行为已正确。
- [性能/正确性边界] 只校验 `status != 'deleted'`（与 `get_novel` 同口径），不做跨用户校验——任务本来就按
  user 过滤，`book_id` 只可能指向自己的书。

## Migration Plan

零 schema 变更；发布即生效。回滚无副作用（读侧判定，不落库）。
