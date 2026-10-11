# Proposal: c-update-strip-below-appbar（全局提示条挂顶栏之下，不推移顶栏）

## Why

全局更新/到期提示条（UpdateNotice / ExpiryNoticeBar）原挂 ClientShell 顶端、占正常文档流，呈现时把顶栏（Navbar，48px 应用栏）从窗口顶端整体推下去——书架屏首当其冲（用户实测截图：更新条悬浮在窗口最顶、爱小说顶栏被顶到第二行）。原型（list.html/book.html）确实把提示条画在 appbar 之上，但落地为「推移顶栏」的常态布局后，顶栏（品牌、主导航、账户胶囊入口）被一条可关闭的提示条挤离窗口顶，观感与可用性都不成立：提示条是临时层，顶栏是常驻骨架。

## What Changes

- **顶栏恒在窗口顶端**：Navbar 上移 ClientShell（壳层骨架：顶栏 → 提示条 → 页面内容 → 状态条），App.tsx 不再渲染顶栏。
- **提示条挂顶栏之下**：UpdateNotice / ExpiryNoticeBar 的壳层实例改挂 Navbar 之下、页面内容之上——呈现时只推页面内容，不推顶栏。
- **书内态同规则**：/novel/* 下壳层顶栏与两条提示条整组让位（工作台行头归一后自带 48px 应用栏），两条提示条改由 NovelWorkspace 渲染在其应用栏之下，工作台顶栏同样不被推走。
- **非目标**：提示条视觉样式、文案、关闭语义（按版本记忆）一律不变；ExpiryNoticeBar 在工作台的呈现宽度维持既有居中口径，不在本批调整。

## Capabilities

### Modified Capabilities

- `client-update`: 「更新提示条交互」Requirement 补挂载位置口径——提示条呈现在所在屏顶栏正下方，顶栏 MUST 保持窗口顶端不被推移；常规屏由壳层挂载，工作台沉浸态由 NovelWorkspace 挂其应用栏之下。

## Impact

- **C端 前端**（`client/frontend/src/`）：`ClientShell.tsx`（收编 Navbar + 路由感知让位）、`App.tsx`（摘 Navbar）、`NovelWorkspace.tsx`（应用栏之下补挂两条提示条）、`index.css` / `UpdateNotice.tsx` 注释口径；`ClientShell.stability.test.tsx`（harness 补 QueryClientProvider/auth mock 扩面 + 新增 DOM 序钉与书内让位钉）、`authRouting.test.tsx`（shell mock 同构）。
- 行为面零变化：检测节奏、文案、动作、关闭记忆、e2e 桩口径全部不动；书架启动请求预算不变（常规屏两条提示条仍恒挂载一次）。
