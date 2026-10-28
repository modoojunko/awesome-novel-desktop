# Tasks: c-tree-batch-confirm-retire

## 1. 影响判定

- [x] 1.1 纯前端入口退役＋孤儿样式清理；确认链路（章纲页签「确认章纲」＋后端 confirm 端点）不动；零存量覆盖；评审补退役钉（SHALL NOT 无钉不上）。验证：本任务即判定记录。

## 2. 前端

- [x] 2.1 `OutlineTree.tsx`：删 `handleBatchConfirm` 与非空书态 `tree-foot` 分支（三元收敛为空书态 `tree-add` 单分支）。验证：tsc 无孤儿引用。
- [x] 2.3 `NovelWorkspace.test.tsx`：补退役钉（非空书无「确认全部已填章节」与 `.tree-foot`）。
- [x] 2.2 `book.css`：删 `.tree-foot .batch` 两规则；`.col-tree.ai-lock` 选择器组移除 `.tree-foot` 成员（`.tree-foot` 本身保留——设定页口径注在用）。验证：grep 无残留 `.batch` 引用。

## 3. 规格

- [x] 3.1 `specs/workbench/spec.md` delta：「EmptyState without settings gating (N4)」左栏条目改「全态退役」口径。

## 4. 收尾

- [x] 4.1 本地门禁：vitest 定向＋tsc＋openspec validate。
- [ ] 4.2 推送＋PR＋CI 绿；同 PR sync delta＋归档（openspec-archive-in-implementation-pr）。
