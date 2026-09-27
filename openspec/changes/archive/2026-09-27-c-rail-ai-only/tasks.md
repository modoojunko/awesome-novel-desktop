## 1. 实现（补录：已随 PR #510 落地，squash=d93fcdd7）

- [x] 1.1 `Rail.tsx`：撤「本章进度」块与死代码（editingTarget/commitTarget/fmt/target/pct、useState/DEFAULT_TARGET 导入）。完成证据＝PR #510 diff＋vitest 875 全绿
- [x] 1.2 `ChapterWorkspace.tsx`：e-meta 加「完成度 N%」「本书总字数 N」徽章（完成度随计划字数缺失不渲染）。完成证据＝workbench-features 头部徽章断言通过
- [x] 1.3 e2e 适配四处：workbench-features 进度卡断言改头部；free-writing-flow/settings-forms/modals-pr5 三处「本章已归档 · 只读」断言（原命中右栏归档卡）改 `.e-meta` 含「已归档」。完成证据＝隔离栈 e2e 47 条全绿
- [x] 1.4 ADJUSTMENTS 登记原型偏差。完成证据＝PR #510 内 diff
- [x] 1.5 本 change 归档（本 PR）：specs 同步 workbench 后移入 `archive/2026-09-27-c-rail-ai-only`
