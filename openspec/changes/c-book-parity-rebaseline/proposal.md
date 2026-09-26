# c-book-parity-rebaseline — 书工作台屏 parity 基线重录（对齐当前实现）

## Why

`design-parity-book.spec.ts` 四例（free·workbench / modal-delete / modal-prefs / modal-upgrade）长期红：4.71% / 2.901% / 2.76% / ~2.7%（阈值 0.2%），且为**全页级漂移**——差异像素铺满每个色带（y 0-900、x 17-1424），不是局部元素差。根因是 book.html 工作台屏的基线停在多个 change 之前：#465 起的历次改动（三页签回默认主页＋书主页卡、抽卡「上接」、卷纲屏迁移 storyline.html、信息差块、章纲 13 格……）都只改实现＋登记 ADJUSTMENTS，未同步 book.html。`#465` 已把这批红按存量漂移登记（当时 4.501/2.642/2.558/2.559%），此后每换一次字体/布局，差距只会继续扩大。本 change 一次性把基线拉回当前实现，让 parity 门禁重新具备「抓未来回归」的判别力。

## What Changes

- **逐差异区裁决**（对 4 例的 diff 图逐区判定，产出裁决清单进 design 附录）：
  - 实现侧是**更新的产品意图**（历次 change 已合、ADJUSTMENTS 已登记）→ **改 book.html 对齐实现**（预期占绝大多数：书主页卡/三页签/落点卡 2 项/章纲 13 格/信息差块等）；
  - 原型侧是**更优设计且实现属漂移** → 改实现对齐原型，并在实现侧补该修正的回归依据；
  - 两边都对/无法判定 → 保留实现形态，在 ADJUSTMENTS 单条登记理由。
- 基线重录：4 例的 proto/app/diff 三张图按重录后的 book.html 重新生成。
- `ADJUSTMENTS.md` 汇总登记本批裁决（替代 #465 的存量漂移登记条目）。
- **不改动**：应用侧的行为语义（除「原型为准」裁决命中项）；`design-parity.spec.ts`（书架屏，已 8/0）与 `design-parity-preview` 的基线。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——本 change 是把 parity 基线资产对齐已合入的实现，不改变任何已规格化的行为；故设 `skip_specs: true`。若逐区裁决命中「原型为准→改实现」项，其行为修正按该裁决在实现侧以既有 capability 口径落地，并在裁决清单中标注。）

## Impact

- `docs/design-c/prototypes/book.html`（工作台屏区块）、`ADJUSTMENTS.md`、`docs/design-c/baselines/book.*`（基线三图重录）。
- 门禁：`design-parity-book.spec.ts` 4 例转绿（0.2% 阈值）；`npm run design:lint`／`design:check` 不回归；`tsc`／vitest 不回归（若命中「原型为准→改实现」项则同步跑相关单测）。

## Design Impact

- 受影响端＝C端；受影响屏＝书工作台（章纲/书主页/三个弹窗态）。本 change 本身就是设计资产的校准动作，由实现侧产出裁决清单与基线重录；裁决清单在动手前先出，作为设计侧可复核的依据。
