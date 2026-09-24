## 1. 原型先行（book.html ＋ ADJUSTMENTS.md）

- [ ] 1.2 `book.html` 批量确认按钮（:609 `btnBatch`）补禁用态建模：demo 数据下按「可确认章数＝0 → disabled + title 提示」切换；验证＝清空演示章节后按钮呈禁用态、恢复一章未确认后可用
- [ ] 1.3 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记批量确认空态禁用调整并注明：顶栏计数为纯行为修复无原型改动；章数目标布局已移交 c-volume-view-storyline（其卷纲编辑表单承载同款布局口径）。验证＝登记条目落盘、与本次 change 名关联

## 2. 顶栏章纲计数一致性（实现）

- [ ] 2.1 `client/frontend/src/components/novel/workbench/OutlineTree.tsx` 删除确认回调补刷：`wb.deleteNode(...)` 成功后补 `outline.refetchTree()`（写法与 handleBatchConfirm 的 Promise.allSettled 双刷同款）；验证＝vitest：删除一章后 `/tree` 被再次请求、顶栏计数数据源更新
- [ ] 2.2 行内加章 `commitInlineAdd` 成功后补 `outline.refetchTree()`；验证＝vitest：加章后计数数据源更新
- [ ] 2.3 Bug8 复验（qa-night：逐章确认后计数全程 0/6）：本机栈逐章确认观察顶栏 N 是否增长；若复现，按 design D1 定位（`refetchTree` 后 `buildStatuses` 重建是否冲掉乐观 confirmed → 核对 `/tree` 章级 status 是否回填已确认语义）并修复，保证重建不把已确认章降级；验证＝确认一章后顶栏计数变 1/N（e2e 或 vitest 断言留档）
- [ ] 2.4 vitest 组件测试补齐：0 章时显示 0/0、删章同步、加章同步、确认增长四场景；验证＝`npx vitest run` 相关文件全绿

## 4. 「确认全部已填章节」空态禁用（实现）

- [ ] 4.1 `OutlineTree.tsx` 批量确认按钮加禁用条件＝不存在未确认且未归档的章（与 handleBatchConfirm 跳过口径同源），禁用态 `disabled` + `title="没有可确认的章节"`；验证＝vitest 三态：0 章禁用、全部已确认禁用、存在未确认可用
- [ ] 4.2 e2e 最小覆盖（`client/frontend/e2e`）：0 章书批量确认按钮禁用断言＋删除章后顶栏计数同步断言；验证＝本机 docker 栈跑相关 spec 通过

## 5. 回归

- [ ] 5.1 C端门禁：`client/frontend` 下 `npm run design:lint` / `npm run design:check`（book 屏无像素 parity CASE，基线应与 main 一致，若有漂移按 ADJUSTMENTS 登记核对）/ `npx tsc --noEmit` / `npx vitest run` 全量；验证＝四项命令实际输出结论追加在本 checkbox
- [ ] 5.2 本机 docker 栈全量 e2e（按 c-client-e2e-runbook 配方，隔离栈 !override＋播种 config.json）；验证＝全量通过结论追加在本 checkbox，存量红项逐一对照登记非回归
