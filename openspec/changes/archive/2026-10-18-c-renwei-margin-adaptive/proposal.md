# Proposal: c-renwei-margin-adaptive（人味边注随正文自适应）

## Why

大屏上人味边注与正文对不上，且窗口越宽边注离正文越远：

1. **大屏 zoom 被算了两次**：`large-screen.css` 在视口 ≥2000px 时给 `html` 设等比 `zoom`（2560 约 1.28，4K 封顶 1.75）。边注层用 `getBoundingClientRect()` 量段落位置，返回值已是放大后的视觉 px，原实现直接当 CSS `top` 用，在 zoom 层里被再放大一次——漂移量＝段落距层顶距离×(zoom−1)，越往下的段落漂得越多（真 Chromium 2560 实测：第 4 段 78px、第 10 段 233px）。
2. **横向贴窗口最右**：边注原 `right:12px` 钉在编辑栏最右，窗口/栏宽越大离正文越远，不再是「右边距批注」。
3. **窄栏不可用**：右侧留白放不下文字列时，原布局要么压住正文右缘、要么被裁切；设计说明 §8 已记为待拍板的最小窗宽问题。

## What Changes

- **大屏缩放折算**：边注纵向/横向位置一律按 `htmlZoom()` 折算回布局 px（与 `panelAnchor` / `CastHover` 同口径）。
- **贴正文右缘**：边注列左缘＝正文栏实测右缘＋16px，列宽吃掉右侧剩余留白（clamp 120~224px）；窗口再宽也保持与正文的距离。
- **跟随布局变化**：`ResizeObserver` 同时观察正文与 `.editor-wrap`——正文仍 680px、只是位置随栏宽移动时也会重新锚定；滚动/resize 原有重算保留。
- **详情卡方向自适应**：右侧留白 ≥264px＋8px 时详情卡朝右展开（不压正文），否则维持朝左。
- **窄栏兜底**：右侧放不下最小文字列时，边注收成段侧 severity 圆点（红/黄），悬停仍展开完整详情卡——不裁字、不压正文。这是设计说明 §8「胶囊＋浮层」的最小形态。
- **非目标**：边注文案、动作（标为已改/跳过）、逐段重扫节奏、朱雀批注左侧口径、正文宽度一律不变。

## Capabilities

### Modified Capabilities

- `renwei-check`：「正文左右分边注与覆盖层」Requirement 补自适应布局契约——大屏 zoom 折算后仍与段落对齐；边注列贴正文右缘固定间距、列宽吃剩余留白；布局变化重锚；详情卡方向自适应；窄栏退化为段侧圆点且不裁字不压正文。

## Impact

- **C端 前端**（`client/frontend/src/`）：`RenweiMarginNotes.tsx`（zoom 折算＋横向锚定＋ResizeObserver＋窄栏类）、`design/book.css`（边注列默认左缘/宽度、详情卡朝右、窄栏圆点）、`__tests__/renweiCheck.test.tsx`（zoom 折算与窄栏兜底回归钉）。
- 行为面：后端、端点、检测算法、数据存储零改动；正文宽度/位置与普通阅读态保持一致。
- 已随 PR #894 合入 main（squash `dfd5b496`，CI 绿）；本 change 只做规格落档与归档。
