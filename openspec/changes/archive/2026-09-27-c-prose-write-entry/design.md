## Context

见 proposal.md。入口迁移只有一处行为语义要保全：`requestAi` 的 `railData?.archived` 门控
（归档章先解锁）与解锁确认后的续跑（`pendingAiRef`）——按钮换位置不影响这条链。

## Decisions

- **D1 testid 沿用 `ai-write-btn`**：两处 e2e、一处单测按它定位，改位置不改锚。
- **D2 走 raActs 而非独立工具卡**：动作清单首项与「压缩啰嗦段落」并列，免费态 locked 置灰
  （原卡的 `pointer-events:none` 对真实点击等效；单测 fireEvent 可穿透旧 CSS 属测试伪影，
  以 disabled 表达后行为更严格）。
- **D3 真bug#2 断言重写**：旧断言「章纲页签触发→自动切回正文」的前提是入口全页签常驻，
  本次移除该前提；新口径钉住「章纲页签无入口＋正文页签确认生成编辑器可见」
  （`aiWriteSignal` 自动切页签逻辑保留，供未来新增入口复用）。

## Risks / Trade-offs

- 生成正文入口深一层（须在正文页签）——与「动作在对应页签」架构一致；顶栏「续写」CTA 与
  润色软提示 toast 的 AiModal 出口不受影响。

## Migration Plan

纯前端同批切换，无迁移。
