## MODIFIED Requirements

### Requirement: Feature capability registry
- `ai-model` SHALL 为**免费可用**（`memberOnly: false`）——模型配置是人工路径能力，免费版也能配置本书模型（配好升级 PRO 后直接可用）；**免费版与会员的差别只在右侧 AI 助手**（免费版全灰 + 升级引导）。
- 原「Free-locked keys SHALL be exactly … `ai-model`」中 `ai-model` 一项 SHALL 移除；`settings-ai-fields`/`outline-advanced-fields`/`ai-generate` 等 AI 能力 key 的会员门控**不变**。
- `features.ts` 的 `ai-model` SHALL 改 `memberOnly: false`，`features.test.ts` 同步移入 FREE_FEATURES。

#### Scenario: 免费版可配置本书模型
- Given 免费版用户进入设定视图
- When 查看「本书模型」面板
- Then 可选模型、可确认落库（无会员拦截），而右侧 AI 助手仍为锁定态
