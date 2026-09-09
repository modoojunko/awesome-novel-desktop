## MODIFIED Requirements

### Requirement: Feature capability registry

- The system SHALL provide `lib/features.ts` defining a `FeatureKey` union type, a `FEATURES: Record<FeatureKey, { memberOnly: boolean }>` map, and a pure function `isMemberFeature(key): boolean`.
- `isMemberFeature` SHALL return `false` for features whose `memberOnly` flag is false, regardless of tier.
- For features whose `memberOnly` flag is true, it SHALL return `true`（入口一律可见；**使用**由后端 `require_ai_access` 统一拦截，前端弹升级引导）。
- Free-enabled keys SHALL be exactly: `tree-crud`, `prose-edit`, `version-history`, `archive`, `volume-chapter-config`, `advanced-config-entry`, `settings-7-items`, **`ai-model`**。
  - `ai-model`（本书模型配置）SHALL 为**免费可用**——模型配置是人工路径能力，免费版也能配置本书模型（配好升级 PRO 后直接可用）；免费版与会员的差别**只在右侧 AI 助手**（免费版整卡可见 + 锁定 + 升级引导）。
- Free-locked keys SHALL be exactly: `settings-ai-fields`, `outline-advanced-fields`, `ai-generate`, `prompt-panel`（原列表中的 `ai-model` 已移除）。
- The module SHALL have no DOM dependency (pure TS).

#### Scenario: Free disabled AI features
- Given a tier of "none"
- When `isMemberFeature("ai-generate")` is evaluated
- Then it is true（会员功能，入口可见、使用被后端拦截）

#### Scenario: 免费版可配置本书模型
- Given 免费版用户进入设定视图
- When 查看「本书模型」面板
- Then 可选模型、可确认落库（无会员拦截），而右侧 AI 助手仍为锁定态
