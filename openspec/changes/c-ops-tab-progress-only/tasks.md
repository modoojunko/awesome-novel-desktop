# Tasks

## 1. 前端

- [x] ReconcilePane：`kinds` 过滤＋免费档渲染 null＋已决行默认折叠＋错误单行省略
- [x] ChapterWorkspace：「设定」页签挂 lore 提案（本章变化区下方）、「伏笔」页签挂 hooks 提案（HooksPane 上方）、操作页签撤收尾区
- [x] 归档卡：已归档已提取态「重新归档」入口＋去向文案；ArchiveModal 重归档变体（确认走 retryExtraction，不重跑收尾的计划区不出现）
- [x] book.css：`.rc-error` 省略号＋已决折叠样式

## 2. 测试

- [x] vitest ReconcilePane：kinds 过滤／免费档 null／已决折叠
- [x] e2e reconcile.spec：两类提案分别到设定/伏笔页签操作；免费档零请求
- [x] e2e chapter-dossier.spec：受影响断言（操作页签无提案行）

## 3. 门禁与交付

- [x] vitest 全量＋tsc＋design:lint
- [x] 受影响 e2e（隔离栈）
- [x] PR＋合并；演示栈前端镜像重建（从本 worktree）
