## Why

用户截图反馈（2026-10-08，第六章生成现场）：编辑态/生成中的绿色呼吸框（`.editor` 680px 版心列）高度只随正文内容走，内容不足一屏时框停在正文末尾，到状态栏之间是一大片死空白——中栏明明还有整屏可用面积。定诊：`.editor-wrap`（滚动容器）本就 `flex:1` 撑满剩余高度，但 `.editor` 列没有拉伸语义，`padding-bottom:120px` 进一步放大了空白观感。

## What Changes

- 编辑态（`.editor-wrap.editing`）把编辑列沿 wrap→包装层→editor 逐级 flex 撑满滚动区剩余高度；内容超出一屏时 `flex-basis:auto` 照常滚动，查看态不加（阅读面随文走）。
- 编辑态底部留白 120px→36px，与顶部对称——框沿贴近视窗底但不顶死。
- `ProsePane.tsx` 给 TipTap v3 `EditorContent` 包装层挂 `className="editor-host"` 作 flex 链稳定钩子（v3 渲染 `<div ref {...rest}>` 透传，dist 实勘）。
- **不动**（明确出界）：查看态布局、呼吸灯参数（c-prose-stream-guard 拍板）、生成中现场保护链、滚动恢复/贴底跟随算法（scrollHeight/scrollTop 几何与布局模式无关）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`：「正文页签查看/编辑两态」requirement MODIFIED——成形编辑框新增**撑满**语义：编辑框正文列（含生成中呼吸灯）SHALL 撑满中栏滚动区剩余高度，短内容时框沿直通状态栏上方（底留白与顶部对称），框内空白为可聚焦书写面；内容超屏照常滚动。原「进编辑态可见框」场景同步补断言，并新增「短内容编辑列撑满」场景。

## Impact

- 代码（全部 C端 `client/frontend`，后端零改动）：
  - `src/design/book.css`：`.editor-wrap.editing` 三条 flex 规则＋底 padding 36px（带 `[hidden]` 全局守卫注释）；
  - `src/components/novel/workbench/ProsePane.tsx`：`EditorContent` 挂 `editor-host` 类（1 行）。
- 测试：`tsc --noEmit` 零错；相关 vitest 7 套 100 例绿（NovelWorkspace/chapterWorkspace.plotFlow/proseStream/proseDoc/features/castReviewFlow/zhuqueWorkbench）；PR #733 CI 全绿。e2e 无编辑态布局断言需改（滚动恢复 e2e 的 LONG 文本千字必溢出，ratio>0 断言不受撑满影响）。
- 门禁：不触 `design:check` parity 页集（parity spec 不进编辑态）；不触两端共享段（`book.css` 为 C端自有，`base.css` 零改动）。
- 验证补充：真机（演示栈 5274）量测 flex 链生效（host=flex、editor `1 0 auto`、wrap 底 padding 36px）＋长文呼吸框通到状态栏；短内容场景用 5274 下发的同一份编译 CSS 搭静态 harness 复验（3 段短文框直通状态栏、空白可点击聚焦）。

## Design Impact

- 受影响端：仅 C端。
- 受影响的屏/弹层：章工作台正文页签编辑态（含生成中呼吸灯态）；查看态与其余页签零改动。
- 用到/新增的对象状态：零新增状态档位、零新增视觉词汇——纯既有成形编辑框（c-prose-edit-affordance 已立）的布局行为补全。
- 是否触碰两端共享段：否（`book.css` C端自有；`design-cross` 零差异）。
- 是否需要原型先行：不需要——无新视觉词汇，撑满是既有编辑框在有限高度容器内的布局行为。
- 设计工件由谁产出：无。
