## 1. 原型核对与登记（design-system 流程：本次为追平原型既有口径，不改原型文件）

- [x] 1.1 核对 6 处修复点均可（已核：book.html `.col-panel/.panel/.og-pane`、genre-signup 列衬垫、storyline `.e-pad`；无新设计）在原型找到对应对照（book.html `.col-panel/.panel/.og-pane`、genre-signup 列衬垫、storyline `.e-pad`），确认无新设计。
- [x] 1.2 `ADJUSTMENTS.md` 新章（已落，7 条含范围切分）「书内中栏节奏单源（c-workbench-col-rhythm）」：单源机制、豁免清单（settings 1180 / sub-fill / 卷壳）、两轮事故索引（09-19 卷视图、09-20 设定页与空态）、sub-fill 分隔线内缩说明。
- [x] 1.3 新档位/变量登记（`--col-pad-*`/`--col-measure` 随 1.2 章条目 1 落笔）（`--col-pad-*`、`--col-measure`；book.css 不在 lint 扫描面，人工登记）。

## 2. 实现（book.css 单文件）

- [x] 2.1 中栏单源变量＋删除归零对（`.panel{max-width:none}` → 默认 660＋卷壳豁免）；`.col-panel{padding:0}` 保留（通栏条依赖）。
- [x] 2.2 内容型面板衬垫继承：章页签 5 类 pane＋设定 `.panel`＋通栏条负边距出血；`.e-pad` 纳入变量。
- [x] 2.3 版心修复（首版一次到位，普查复测：文风行 838→≤670、操作卡 924→670 对齐）：文风/操作等行级 `max-width: var(--col-measure)`（首版→普查脚本实测→迭代）。
- [x] 2.4 `npm run design:lint` exit 0；`npx tsc --noEmit` exit 0；`npx tsc --noEmit` exit 0（无 tsx 改动，防御回归）。

## 3. 验证与回归

- [x] 3.1 普查脚本复测（建临时书→设定 8 面板/章 8 页签/卷视图）：设定页 8 面板 0→48px、章页签 5 类衬垫统一 26/48/60、版心 660 生效：❌→有衬垫且版心生效、✅ 4 处不回归（写作空态由并行 change `c-0vol0ch-empty-state` 处理，本 change 不测其观感）；输出摘要＋截图留档 `evidence/`。
- [x] 3.2 烘镜像进主栈（index-CuJ7eBbH）；`npm run design:check` 8 passed（书架七场景＋preview 零波及）（书架 parity 七场景＋preview）不受影响。
- [x] 3.3 vitest 691 全绿；相关 e2e（workbench-features / landing-view / ui-spec-parity / free-writing-flow）＋全量 e2e 全绿；vitest 全量绿。
- [x] 3.4 右栏（AI rail 未动）/预览/书架（design:check 七场景）对照确认零波及。

## 4. 收尾

- [x] 4.1 `git status` 清点：本批＝book.css（仅我的 hunk，+34/-4 精确暂存）＋ADJUSTMENTS 章（+21 精确暂存）＋change 目录；并行会话 `c-0vol0ch-empty-state` 的 7 文件改动留在工作区未暂存，零裹挟；临时脚本已清（仅 book.css＋ADJUSTMENTS＋change 目录）；临时脚本与截图清理。
