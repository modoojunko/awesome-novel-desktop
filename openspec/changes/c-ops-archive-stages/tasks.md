# Tasks: c-ops-archive-stages

## 1. 归档卡三段进度

- [ ] 1.1 新 `ArchiveStages.tsx`：三段条组件（提取 active/done/fail/skip＋已运行秒数；确认 待确认 N 条/提案已处理；完成）＋`useElapsedSec` 走秒 hook
- [ ] 1.2 `ChapterWorkspace.tsx`：rearchive 扩 pending；归档卡按态渲染进度条（提取中/失败/已归档含未提取），提取说明行去重
- [ ] 1.3 `design/book.css`：`.arch-stages` 段样式（active/done/fail/skip 四态点色）

## 2. 测试与门禁

- [ ] 2.1 vitest `archiveStages.test.tsx`：状态矩阵（提取中/已归档待确认/全处理完/失败/跳过）＋走秒 hook
- [ ] 2.2 e2e `chapter-dossier.spec.ts`：全链用例补已归档条断言（待确认计数可见）；逃生阀用例补失败态断言
- [ ] 2.3 tsc＋全量 vitest（存量红除外）＋隔离栈 e2e chapter-dossier/reconcile
- [ ] 2.4 openspec validate --strict；PR＋归档
