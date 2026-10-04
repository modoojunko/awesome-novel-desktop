# Change: 正文生成中的现场保护（呼吸灯＋树锁定＋半截落库）

## Why

正文流式生成期间换页会静默掐断生成且丢弃已生成的半截内容：流式会话（网络流、缓冲、插入位置）全部活在 `ProsePane` 组件内部，左栏点另一章/点卷、或任何导致编辑器卸载的导航都会触发 abort-only cleanup，`finishStream` 不执行、半截正文不落库，用户切回来发现「什么都没有」。且现有「生成中」提示几乎不可见（编辑器仅 `cursor: progress`、顶栏 6px 脉冲点、且离开正文页签后徽章被 `hidden` 一并藏掉），用户往往意识不到生成正在进行。手动点「停止」却会保留半截（abort 后 `finishStream` 收尾落库）——同一份生成内容「手点停止有、切页没有」是明确的语义裂缝。

## What Changes

- **生成中状态可视**：编辑器流式期间加 accent 色「呼吸灯」边框动画（挂在既有 `.generating` class 上）；「AI 正在生成…」徽章在非正文页签（章纲/操作）也保持可见（现挂在 `editor-status` 内被整体 `hidden`）。
- **危险口子锁定**：流式期间左栏卷/章树置灰不可点，hover 提示指路「停止」；点「停止」或生成结束即恢复。顶栏「写作」回书主页的既有确认弹窗口径不变；页签切换（正文/章纲/操作）与切设定/预览不受影响（这些路径本就不丢流）。
- **半截内容落库（保底）**：`ProsePane` 卸载/切章 cleanup 照抄「停止」的两步收尾（abort 前先 `finishStream(streamReceivedRef, false)`），半截生成内容经自动保存落库——即使被确认弹窗放行、或未来新增导航路径，内容也不丢。
- **修复次生 bug**：现 cleanup 只复位 `streamingRef` 不复位 UI 态，切章后编辑器保持锁定（`setEditable(false)`）、「生成中」徽章残留直到下次生成结束；`finishStream` 收尾统一复位。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 新增 Requirement「正文生成中的现场保护」：生成中状态可视（呼吸灯＋徽章常显）、左栏树生成中锁定、切章/卸载保留半截落库、流式 UI 态切章复位。既有「页签回默认主页」的流式确认场景与「正文编辑器核心契约」的停止收尾语义不变，本需求是其保护面的补全。

## Impact

- **代码**（全部 C端 前端，无后端改动）：
  - `client/frontend/src/components/novel/workbench/ProsePane.tsx`：cleanup 收尾、流式态复位。
  - `client/frontend/src/components/novel/NovelWorkspace.tsx`：把 `aiState.streaming` 传入左栏树。
  - `client/frontend/src/components/novel/workbench/OutlineTree.tsx`：节点锁定态与提示。
  - `client/frontend/src/components/novel/workbench/ChapterWorkspace.tsx`：生成中徽章移出 `editor-status` 的 `hidden` 作用域（非正文页签可见）。
  - `client/frontend/src/design/book.css`：`.editor.generating` 呼吸灯动画（复用既有 accent 令牌，零裸 hex）。
- **不改动**：回书主页确认弹窗文案与行为、页签/设定/预览的常驻挂载机制、后端流式接口。

## Design Impact

- **受影响端**：仅 C端。
- **受影响屏/弹层**：写作视图章工作台——正文编辑区（呼吸灯）、底部状态条（徽章作用域）、左栏卷/章树（锁定态）；不涉弹层。
- **对象状态**：编辑器既有「生成中」状态（状态语言总表内的进行时态）强化可见性，不新增对象状态档位；左栏树新增「生成中锁定」禁用态，复用既有 disabled 语义（置灰＋指路文案），不引入第四种胶囊/语气词。
- **文案口径（§13）**：树节点提示与徽章补救语句均带可点击出口（「停止」按钮）；无按钮词新增；不出现内部术语（门控/SSE/abort 等）。
- **两端共享段**：不触碰（改动全部落在 book.css 工作台局部类与 C端 组件，不动 base.css 令牌与基础组件类），无需 design-cross。
- **原型先行**：按用户 2026-10-04 拍板豁免——不改 `book.html` 整页原型；特效以独立演示页确认（应用内浏览器实机播放，「就这个」），演示页参数即验收基准（已回填 design.md）。
- **设计工件产出**：实现侧自查（无新令牌/词汇，视觉为既有 accent 色的动效应用）。
