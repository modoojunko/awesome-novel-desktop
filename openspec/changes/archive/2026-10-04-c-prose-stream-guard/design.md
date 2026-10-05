# Design: 正文生成中的现场保护

## Context

- 流式会话（网络流、`streamReceivedRef` 缓冲、插入位置）全部活在 `ProsePane` 组件内；`ProsePane.tsx` 的「卸载/切章」effect cleanup 目前只做 `abortRef.current?.abort()` + `streamingRef.current = false`，不落库、不复位 UI 态。
- 「停止」按钮（`stopWriting`）已有正确的收尾语义：`abort()` 后调 `finishStream(streamReceivedRef.current, false)`——半截内容经 `setProse` 走自动保存，且 `finishStream` 内部复位 `streaming`/`aiState.streaming` 并解锁编辑器。
- 落库链路自带兜底：`useChapterData` 的 `ChapterStore` 是模块级每章单例，`setProse` 标脏＋1.5s 防抖保存；末位消费者卸载时 `release()` 对脏数据立即 `doSave()`。切章（旧 store refCount 归零）与卸载两条路都覆盖。
- 编辑器流式时已挂 `.generating` class（`ProsePane` 排版 effect）；book.css 对它只有 `cursor: progress`。
- 「AI 正在生成…」徽章＋「停止」按钮现在渲染在 `editor-status` 容器内，而该容器 `hidden={chTab !== "prose"}`——离开正文页签后生成状态完全不可见。
- `OutlineTree` 挂在 `NovelWorkspace`（左栏 col-tree），而 `aiState` state 就在 `NovelWorkspace`——锁定信号传递无新增层级。

## Goals / Non-Goals

**Goals:**

- 生成现场在中断风险面前可幸存：半截内容任何路径下都落库。
- 生成状态在四个页签下都可见；危险口子（左栏树）生成中锁定。
- 顺带修复切章后流式 UI 态残留（编辑器锁定、徽章不消）。

**Non-Goals:**

- 不做后台续流（流式会话提升到模块级 store、换页回来续显）——工程量大，当前保护面够用。
- 不做全页禁点（pointer-events 全局封锁）——分钟级生成锁死整页读作「卡死」。
- 不改回书主页确认弹窗、不改后端流式接口、不动页签/设定/预览的常驻挂载机制。

## Decisions

1. **cleanup 照抄 `stopWriting` 两步，而不是另写保存逻辑**：cleanup 改为先 `abortRef.current?.abort()` 再 `finishStream(streamReceivedRef.current, false)`。复用既有收尾（半截并入正文、自动保存、UI 态复位、解锁编辑器）零新语义；`finishStream` 开头的 `streamingRef` 早退守卫使其天然幂等（生成已正常结束的切章为 no-op）。次生 bug 随之消失，不再单独写复位代码。备选「cleanup 里手动 setProse＋setStreaming」被否：两处维护同一收尾语义必然漂移。
2. **执行顺序与生命周期安全性**：先 abort 再 finishStream（防 abort 落地前 chunk 继续到达改写缓冲）；React cleanup 逆序执行保证该 effect 的 cleanup 先于 `useEditor` 的销毁 cleanup 运行，`finishStream` 内的编辑器两步收尾（删流式区间＋整段写回）在编辑器仍存活时执行；`isDestroyed` 守卫兜底真卸载竞态。
3. **树锁定用置灰＋守卫，不用确认弹窗**：可逆的中断动作（生成随时可重来）不制造弹窗疲劳；置灰态与呼吸灯同屏在场，原因自明。实现为 `OutlineTree` 新增 `locked` prop（`aiState.streaming` 直传）：章/卷行点击与行内操作按钮（新建/改名/删除等）全部守卫＋`aria-disabled`＋`title` 指路文案。全树锁定而非只锁章/卷行：新建章会跳转编辑器、删除当前章同样摧毁生成现场，逐一豁免的口径成本高于统一锁。§13「补救语句带可点击出口」的出口实体＝页签行常显的「停止」按钮（tooltip 无法承载按钮，文案指路即可）。
4. **呼吸灯挂在既有 `.generating` class 上**：book.css 为 `.editor.generating` 加 box-shadow 呼吸 `@keyframes`，参数以用户拍板的独立演示页为准（2026-10-04「就这个」）：`streamBreath 2s ease-in-out infinite`，0%/100% 帧＝`0 0 0 1px` 环（accent 18%）＋`0 0 14px` 晕（accent 6%），50% 帧＝环（accent 55%）＋`0 0 28px` 晕（accent 20%）；`var(--accent)` 令牌，零裸 hex；不动 base.css 共享段。原型先行按用户拍板豁免（不改 `book.html` 整页设计），演示页即验收基准。不另加 `prefers-reduced-motion` 分支——与站内既有 `.ai-streaming .pulse` 动画口径一致（后者也未做）。
   - 修正：落库路径**不依赖 cleanup 与 `useEditor` 销毁的执行顺序**——收尾落库走 `setProse(base + streamReceivedRef)`（纯 ref 计算），编辑器存活与否只影响「删流式区间＋整段写回」的 DOM 同步步骤（有 `isDestroyed` 守卫）；`ChapterStore` 的 release 兜底 flush 与 setProse 再标脏两条路都保证半截落库。
5. **生成中徽章提升到页签行**：徽章＋「停止」从 `editor-status`（被 `hidden` 的容器）移出，改为流式期间条件渲染在章工作台页签行——四个页签下都可见，正文页签下 `editor-status` 内不再重复渲染。备选「放宽 editor-status 的 hidden 条件」被否：会把字数/保存态整条状态栏带到其它页签，噪音大于收益。e2e 中定位该徽章/按钮的断言需随位置更新。

## Risks / Trade-offs

- [归档提取中 `setProse` 被软锁，若恰逢流式收尾会静默丢半截] → 归档受理制在提取期全程软锁写作入口，流式与提取不可能并发；不改代码，靠既有互斥。
- [finishStream 在切章 cleanup 中执行时，编辑器两步收尾写的是旧章文档] → 正确行为：cleanup 先于新章数据载入运行，收尾与 `setProse` 闭包捕获的都是旧章 store，落库进旧章。
- [树锁定覆盖面宽（全树交互），重度用户生成中想顺手改名别章会被挡] → 生成是分钟级操作，锁定窗口有限；「停止」随时可解锁。先统一锁，真出现高频诉求再细化豁免清单。
- [e2e 既有用例若在流式中断言过旧徽章位置或依赖流式中切树] → 实现批次内 grep `ai-streaming`/`停止` 相关断言与流式 e2e，同批更新。

## Migration Plan

纯前端改动，随下一版本发布，无数据迁移；回滚＝revert 单批提交。

## Open Questions

（无）
