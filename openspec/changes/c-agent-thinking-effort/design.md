## Context

见 `proposal.md`。当前 `_explicit_thinking_params(explicit)` 对非 disabled 形态直接返回 `{"thinking": explicit}`，不带 effort；配置开思考的 `_thinking_params()` 才带 effort（GLM 嵌套、其余顶层）。助手开关传 `{"type":"enabled"}`，于是吃供应商默认 high。

## Goals / Non-Goals

**Goals:**
- 助手显式开思考时按模型配置的强度下发（默认 low），显式自带 effort 优先。
- 判定类显式 disabled 仍不搭车强度；Gemini/opencode-go-claude 映射不变。
- 已知不支持思考参数的 base 不再多打一次被拒请求。

**Non-Goals:**
- 不改前端开关形态（仍开/关，不加低/高/深三档）。
- 不改配置开/关思考的既有下发形态与计费口径。

## Decisions

### 1. enabled 参数组补齐配置强度
`_explicit_thinking_params` 的非 disabled 分支调用 `_enabled_thinking_params`：
- 显式自带 `reasoning_effort`/`effort` → 原样 `{"thinking": explicit}`；
- GLM → `{"thinking": {**explicit, "reasoning_effort": config_effort}}`（顶层 effort 会被静默吞掉）；
- 其余 → `{"thinking": explicit, "reasoning_effort": config_effort}`（与配置开思考同款）。
- 理由：显式 enabled 的语义是「开思考」，强度应由配置决定；显式强度仍最高优先。
- 备选：让助手调用方自己带 effort（要暴露 client 私有配置/新增参数，改动面更大）。

### 2. 已知不支持 base 直接不发
非 disabled 分支若 base 命中 `_THINKING_UNSUPPORTED_BASES`，返回 None（不发思考参数）。理由：该 base 已被实证拒绝 enabled/无参形态，再发只会多一次失败请求；与 disabled 分支的口径一致。
- 备选：继续发、靠拒参重试记忆（浪费一次往返，否决）。

### 3. 不改 disabled / vendor 特例
disabled 的 FORCED/UNSUPPORTED/普通三态原样；Gemini 的 `reasoning_effort` 换算、opencode-go-claude 的 adaptive 原样。理由：这些是各自端点的实测契约，本次只补 enabled 的强度。

## Risks / Trade-offs

- [DeepSeek 对顶层 `reasoning_effort` 的接受度] → 与配置开思考路径同款形态；若端点拒绝，既有去参重试兜底，真机烟测验证（配置开→关两态）。
- [低强度思考可能让助手推理变浅] → 这是配置项的本意（默认 low）；用户可在模型配置里调高/深，助手开关不覆盖。
- [显式 enabled 自带 effort 的调用方] → 原样保留，不覆盖。

## Migration Plan

- 纯参数构造修复，无数据/API 迁移；回滚还原 `_explicit_thinking_params` 即可。

## Open Questions

（无）
