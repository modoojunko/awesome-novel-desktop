## 1. 空书态三面落地（PR #450，commit bbc01ea）

- [x] 1.1 顶栏 bar-here 补「空书」态（`volumes.length === 0` 分支；原 `hereTarget === null` 时整块留空）。验证：e2e `creation-flow` 断言 `.bar-here .bh-k` = 「空书」；同视口截图与原型对拍。
- [x] 1.2 中栏空态两分支：零卷零章＝`.e-empty` 起手卡（双入口）；有卷未选中＝一句选章引导；「开始创作」面板退役。验证：vitest NovelWorkspace（`.e-empty .be-acts .btn` 计 2、`data-od-id="book-empty"`）；e2e 三处文案断言更新后全绿。
- [x] 1.3 左栏：空态提示改设计稿原文；空书态底部 `.tree-add` 两入口替代「确认全部已填章节」；`.col-tree.empty-book` 修饰类让按钮组贴列底（非空书态不入此类）。验证：vitest 断言 `.col-tree.empty-book .tree-add`；DOM 实测列底位置与原型一致。
- [x] 1.4 起手链：空书「＋ 新增一章」先垫「第一卷」（`第${cnNum(1)}卷`）再排「第一章」，落章纲页签并提示。验证：e2e 新增用例「空书起手：中栏「＋ 新增一章」先垫第一卷并排上第一章」；vitest 断言两次 POST 顺序（`/volumes` → `/volumes/vol-1/chapters`）。
- [x] 1.5 右栏未选中态补原型无语境 aiShell（页签「未选」＋通用引导语＋四格全书统计＋免费档脚注；悬置伏笔懒取 `/hooks`，失败降级「—」）。验证：vitest 断言 `.col-ai .ai-ctx` 含「未选」、`idle-rail-stats` 四格；截图与原型 `.col-ai` 对拍。

## 2. 结构上提与样式

- [x] 2.1 `AddVolumeModal` 由 `OutlineTree` 移入 `modals.tsx`，工作台壳层（`NovelWorkspace`）持有，空书态三处入口共用同一实例。验证：e2e 既有 `getByTitle("添加卷")` 链路全绿（creation-flow/workbench-features/plot-sim 等）；弹窗内部契约（卷名必填＋卷摘要＋初始章数）逐字未动。
- [x] 2.2 `book.css` 补 `.e-empty/.be-k/.be-t/.be-acts`、`.tree-add/.add-btn`、`.col-tree.empty-book` 三条；`.empty-tree` 度量对齐原型 `.toc-empty`（12.5px / 14px 6px）。验证：`design:lint` 通过；截图对拍。

## 3. 登记与回归

- [x] 3.1 ADJUSTMENTS.md 新章「0vol0ch-empty-state.html 空书态落地」10 条（含两处不动的壳层文本留档：modnav 动态句、设定 N/7 计数）。验证：与并行 change `c-workbench-col-rhythm` 的同文件改动按 hunk 精确分割，互不裹挟。
- [x] 3.2 `npx tsc --noEmit` 0 错；`npx vitest run` 691 通过；`npm run design:lint` 通过。
- [x] 3.3 全量 e2e 166 通过／17 跳过（1 条 `session-invalid` 负载型抖动，单跑 ×2 绿，非本批回归）；空书态与原型同视口逐栏截图对拍（顶栏／左栏／中栏／右栏四处一致）。
- [x] 3.4 PR #450 squash 合入 main＝bbc01ea；本卷宗补记需求变化并归档（三条 MODIFIED 需求同步进 `openspec/specs/workbench/spec.md`）。
