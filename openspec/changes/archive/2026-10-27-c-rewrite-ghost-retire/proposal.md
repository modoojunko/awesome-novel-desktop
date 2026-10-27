# Proposal: c-rewrite-ghost-retire

## Why

用户拍板（2026-10-27）：重写第 5 章后左栏常驻一块「旧稿支线（只读）」——重写旧稿作为一等 UI 概念入侵大纲树，且它**完全冗余**：每次正文实质落库（保存/导入同源）都写 `chapter_versions` 快照，重写前那份旧稿必然已是当时最新一条快照，「版本历史」弹窗就是它的找回入口。左栏支线分组只该服务真正需要它的场景——回退（revert）把后续章整段移出主线，支线是这些章唯一的可见形态。

## What Changes

- **重写不再转存支线**：`POST /chapters/{ref}/rewrite` 退役「旧稿快照转支线」步——一次事务只剩「归档章解锁回可写＋下游『基于旧设定』置位＋章档级联」；响应不再带 `ghost_ref`/`ghost_created`。确认前 flush 落盘保留（保证重写前正文必有版本快照）。
- **存量重写旧稿行零迁移即隐形**：`GET /ghosts` 与卷视图 `ghost_count` 与列表同口径——ref 带 `-r{8hex}` 内容寻址后缀的历史行不列出不计数；行本身只读无害、随备份往返保留（不可达但零风险）。
- **文案三处**：归档横幅「旧稿自动转存支线」→「旧稿留存于版本历史」；重写卡与影响面确认弹窗同步改口径；重写 toast →「旧稿在版本历史」。
- **回退支线不动**：revert 链路、支线只读口径、左栏 ghost 分组（回退来源）全部保持。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `workbench`：「重写这一章（旧稿转支线＋下游旧设定角标）」重写为「旧稿存版本历史」形态（REMOVE 旧名＋ADD 新名）；「回退与旧稿支线」的 `GET /ghosts` 契约补存量过滤口径。

## Impact

- 后端：`client/backend/chapters/rewrite.py`（退役快照步）、`chapters/router.py`（docstring）、`volumes/service.py`（`list_ghosts` 过滤＋`ghost_count` 同口径）。
- 前端：`workbench/ChapterWorkspace.tsx`（横幅/重写卡/toast/响应类型）、`workbench/modals.tsx`（影响面确认弹窗）。
- 测试：`tests/test_rewrite.py`、`tests/test_rewrite_roundtrip.py`、`e2e/chapter-rewrite.spec.ts`、`__tests__/rewriteFlow.test.tsx`、`__tests__/NovelWorkspace.test.tsx`。
- 不动：回退链（`frontier.revert_to_chapter`）、支线只读守卫（`frontier.is_writable`）、备份往返、`chapterRef.ts` ref 语法单源（存量 ref 仍需正确解析）。
