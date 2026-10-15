# c-prose-generation-headroom — Design

## Context

M3 实测（llm.log 90.034s 判死行）证明 90 秒守卫与 8192 共用预算是以 GLM 系思考时长标定的，对深度思考模型失效。用户实配为 anthropic 兼容端点——同时暴露 #851 剥离只覆盖 openai 路径的缺口（MiniMax anthropic 端点思考关断时把 `<think>` 内联进 text）。

## Goals / Non-Goals

**Goals**
- M3 正文生成能跑通：守卫与预算按「思考＋正文」合计给足。
- 内联思考卫生层两协议同构，用户切 thinking 开关都不泄漏。

**Non-Goals**
- 判定类短调用与其余 op 的守卫/预算（维持默认 90 秒与各自现值）。
- 思考呈现（c-thinking-display 另行）。
- 按模型/档位动态伸缩守卫（配置里的 thinking_enabled 抓不住「总是思考」的模型，常量一步到位，后续有实测数据再分级）。

## Decisions

1. **常量落 write/router 调用点（`PROSE_FIRST_CONTENT_TIMEOUT=600` / `PROSE_MAX_TOKENS=32768`），不动 ai_client 默认。** ai-client 的 FIRST_CONTENT_TIMEOUT=90 仍是「默认」语义，spec 措辞（默认 90 秒）保持为真；正文是唯一长思考 op，单点改。

2. **守卫 600 秒的依据**：M3 effort=low 实测 >90s；深度思考档可能到数分钟。600 秒内真挂死由 read 相邻事件间隔（120 秒）先行判死——守卫只封顶「健康流式但无正文」的畸形态。最坏静默 10 分钟是已知代价（呈现缺口的临时容忍，c-thinking-display 落地后有思考可见）。

3. **max_tokens 32768**：思考（M3 长链可达上万 token）＋正文（6000 字目标 ≈ 9-10k token）合计；按量计费未用不花钱。miniMax anthropic 端点为 Claude Code 生态设计，32k 在其常规 range（若端点打回上限错误，错误可见、届时按 chapter-plot-items 的降预算先例跟进——本期不加降级臂，避免为未发生的 400 预设分支）。

4. **anthropic 剥离＝复用同一 `_InlineThinkStripper`**：流式在 `text_delta` 处 feed（守卫撤点＝状态机放行正文，与 openai 分支同构），非流式在首个 text 块出口 `strip_inline_think`。独立 thinking 块照旧丢弃，两形态互不干扰。

## Risks / Trade-offs

- [非思考模型挂死要等 600 秒才报错] → read 超时（120 秒无任何事件）先判死绝大多数真挂死；守卫只余「持续吐垃圾增量不出正文」的畸形态。接受。
- [32768 被端点上限打回] → 400 可见、文案含上限语义；届时加降级臂（chapter-plot-items 先例）。
- [anthropic 剥离误伤] → 窄口径（`<think>` 起始才剥）；GLM/DeepSeek anthropic 端点不产该形态，行为零变化。

## Migration Plan

无数据迁移。回滚＝还原代码。

## Open Questions

无。
