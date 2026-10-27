# Tasks: c-rewrite-ghost-retire

## 1. 双端影响判定

- [x] 1.1 纯文案＋契约收紧，无新组件、不触共享段；左栏 ghost 分组保留（回退来源），免原型先行。验证：本任务即判定记录。

## 2. 后端

- [x] 2.1 `chapters/rewrite.py`：退役「旧稿快照转支线」步（`ghost_ref_for` 删除）；一次事务＝归档章解锁＋下游 stale/章档级联；响应去掉 `ghost_ref`/`ghost_created`。验证：`test_rewrite.py` 全绿。
- [x] 2.2 `volumes/service.py`：`list_ghosts` 过滤 `-r{8hex}` 存量行（origin 派生字段随之退役）；`get_volume` 的 `ghost_count` 与列表同口径。验证：`test_rewrite_roundtrip.py` 往返＋列表口径全绿。
- [x] 2.3 `chapters/router.py` rewrite 端点 docstring 同步。

## 3. 前端

- [x] 3.1 `ChapterWorkspace.tsx`：归档横幅「旧稿自动转存支线」→「旧稿留存于版本历史」；重写卡描述、toast、响应类型同步。验证：vitest＋tsc。
- [x] 3.2 `modals.tsx` RewriteModal：影响面「旧稿」行改「存入版本历史」口径。验证：`rewriteFlow.test.tsx`＋`NovelWorkspace.test.tsx` 改钉。

## 4. e2e

- [x] 4.1 `chapter-rewrite.spec.ts`：改钉「无支线分组」新契约（弹窗/toast 文案、`.ghost-group` haveCount 0）；下游角标链与刷新回读保留。回退链 e2e（free-writing-flow）不动。

## 5. 收尾

- [x] 5.1 本地门禁：pytest 全量＋ruff＋vitest＋tsc。
- [ ] 5.2 推送＋PR＋CI 双绿；同 PR sync delta＋归档（openspec-archive-in-implementation-pr）。
