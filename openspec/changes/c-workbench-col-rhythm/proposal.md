# 书内中栏节奏单源：内容衬垫与版心一处定义

## Why

storyline 皮肤曾用两条「整列归零」规则（`book.css:1355-1356`：`.col-panel` 左右衬垫→0、`.panel` 版心→不限）命中**书内全部三栏页面**，随后靠「各面板自己补衬垫」弥补。2026-09-20 全量普查（逐面板实测 + 截图）确认漏补共 **8 处**：设定页 8 面板全部贴栏左缘（含角色/伏笔双栏）、写作空态（0 卷 0 章）贴边且版心失控、章页签「操作/文风/角色关系」零衬垫（回退卡横跨整栏）、「章纲/提示词」版心被归零靠字段自带上限侥幸兜住、「设定（22px）/伏笔（16px）」节奏与「章纲（48px）」不一致。同类事故已发生两轮（09-19 卷视图、09-20 设定页与写作空态），根因是**节奏不是单源**。

## What Changes

- **中栏节奏单源**（新增 CSS 变量，定义一处）：`--col-pad-t/-x/-b`（内容衬垫，book.html 口径 26px / clamp(20px,4vw,48px) / 60px）与 `--col-measure`（表单内容宽度上限 76ch），挂在 `.wb .view.on.three-col` 上。
- **内容型面板统一继承**：章页签 `.settings-pane/.style-pane/.relations-pane/.actions-pane/.hooks-wrap` 与设定页 `.panel` 系列改为 `padding: var(--col-pad-*)`；行级内容（文风表单行/操作卡）不超过 `--col-measure`。
- **注（范围切分）**：写作空态（0 卷 0 章）的贴边问题由**并行 change `c-0vol0ch-empty-state`** 按其新原型（`0vol0ch-empty-state.html`，空态已重构为 `.e-empty` 起手卡）处理，本 change 不重复；本 change 只保证其所在容器遵守单源节奏变量。
- **通栏条出血**：设定页 `.panel-head/.panel-foot`（底部「保存修改」条）用负边距保持通栏观感，文字与内容对齐。
- **版心恢复与显式豁免**：删除 `.panel { max-width: none }` 归零；默认版心回 660（book.html `.panel`）；豁免清单＝设定页 1180 上限（既有决策，贴 AI 栏）、`sub-fill` 双栏（角色/伏笔）、卷壳（字段自带 76ch）。
- **卷/章编辑区节奏并入变量**：`.e-pad` 改引 `--col-pad` 系列（值不变 18/22/24 由独立变量 `--col-pad-editor` 承载，storyline 口径）。
- ADJUSTMENTS 新章登记：单源机制、豁免清单、两轮事故复盘索引。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 新增「中栏节奏单源」requirement——内容衬垫与版心在中栏级定义一次，全部内容型面板继承；通栏条出血；豁免面板显式声明；SHALL NOT 再出现「整列归零＋逐面板补衬垫」的补丁模式。

## Design Impact

- **受影响端**：C端 单端，书内页（设定视图 8 面板、写作视图空态与 8 个章页签、卷视图纳入单源）。
- **受影响屏/弹层**：书内三栏页中栏（/novel/:id 的设定/写作）；预览页（独立节奏）与右栏 AI 不在范围；书架不受影响。
- **对象状态**：无新状态、无语气词、无新组件形态（纯节奏与宽度）。
- **是否触碰两端共享段**：否——改动全部在 `book.css` 业务层（`.wb .view.on.three-col` 作用域），base.css 零改动。
- **是否需要原型先行**：**不需要新设计**——6 处修复点均为「实现追平原型既有口径」（book.html `.col-panel/.panel/og-pane`、genre-signup 列衬垫、storyline `.e-pad`）；原型文件不改，ADJUSTMENTS 登记单源机制与豁免清单。
- **设计工件产出方**：实现侧自查（对照既有原型值）。

## Impact

- 代码：`client/frontend/src/design/book.css`（单源变量＋应用点＋豁免；删除 1355-1356 归零对）；无 tsx 结构改动（唯读 class 不变）。
- 登记：`docs/design-c/prototypes/ADJUSTMENTS.md` 新章（单源机制＋豁免清单＋事故索引）。
- 验证：全量普查脚本复测（8 处 ❌ → 全部有衬垫/版心；4 处 ✅ 不回归）＋design:check（书架 parity 不受影响）＋tsc/vitest/相关 e2e（workbench-features、landing-view、ui-spec-parity）＋全量 e2e。
