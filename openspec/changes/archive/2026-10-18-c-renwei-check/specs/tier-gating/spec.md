## MODIFIED Requirements

### Requirement: Feature capability registry

- The system SHALL provide `lib/features.ts` defining a `FeatureKey` union type, a `FEATURES: Record<FeatureKey, { minTier: "free" | "standard" | "pro" | "max" }>` map, and helper `minTierOf(key)`；`isMemberFeature(key)`（=minTier !== "free"）SHALL 保留为兼容派生。
- `minTierOf` SHALL return `"free"` for free capabilities regardless of tier；`"standard"`/`"pro"`/`"max"` 为该功能所需的最低档（入口一律可见；**使用**由后端按 feature key 门禁统一拦截，前端弹对应档位的升级引导）。
- Free-enabled keys SHALL be exactly: `tree-crud`, `prose-edit`, `version-history`, `archive`, `volume-chapter-config`, `advanced-config-entry`, `settings-7-items`, **`ai-model`**。
  - `ai-model`（本书模型配置）SHALL 为**免费可用**——模型配置是人工路径能力，免费版也能配置本书模型（配好开通档位后直接可用）。
- 会员功能 key 及其最低档 SHALL be exactly:
  - `ai-plan`（**新**，标准起）：流程 AI 全家——卷规划三套走法/铺空缺、拆章三方向、帮写剧情三选一、章纲起草/补缺、人物盘点（含抽卡）、卷体检、建书元信息建议；
  - `chapter-review`（**新**，标准起）：章自检 AI 短评；
  - `settings-ai-fields`（标准起）：设定域右栏 AI 全家；
  - `outline-advanced-fields`（标准起）：章纲高级字段；
  - `ai-generate`（PRO 起）：正文 AI 全家（生成/润色/提示词润色）＋workbench 六类案头检查（ai-check 族，2026-10-05 终拍）；
  - `prompt-panel`（PRO 起）：提示词页签；
  - `ai-plot`（**新**，MAX）：剧情推演＋story 推演会话（六类冲突检测不在其内）；
  - `ai-detect`（**留 PRO**，2026-10-05 拍板撤销「上收 MAX」草案）：朱雀 AI 检测，PRO 起发放、trial 同权。
  - `style-suggest`（新增）：文风建议（自己写正文时的 AI 修改建议），标准起发放——与 style-quant 拆 key。
  - `style-quant`（新增）：文风蒸馏（贴旧稿蒸馏文风基线），仅 MAX 发放。
  - `ai-plot`（新增）：剧情推演，仅 MAX 发放（卷纲冲突检测不在其内——留 ai-check 族挂 ai-generate 门）。
- The module SHALL have no DOM dependency (pure TS).

#### Scenario: Free disabled AI features

- Given a tier of "none"
- When `minTierOf("ai-generate")` is evaluated
- Then it is "pro"（会员功能，入口可见、使用被后端拦截）

#### Scenario: 免费版可配置本书模型

- Given 免费版用户进入设定视图
- When 查看「本书模型」面板
- Then 可选模型、可确认落库（无会员拦截），而右侧 AI 助手仍为锁定态

#### Scenario: ai-detect 对非 MAX 锁定

- Given 快照存在且 features 不含 "ai-detect"（免费/标准用户——PRO 起发放、trial 同权）
- When useFeature("ai-detect") 被调用
- Then 返回 false（工作台检测行呈锁定态，入口可见、点击走 PRO 升级出口——ai-detect 留 PRO，2026-10-05 拍板）

#### Scenario: 新 key 进词汇表同批挂门

- When 一个新功能 key 被加入 FEATURES 注册表
- Then 该功能的端点 SHALL 在同一变更批次声明所需 key（端点 key ∈ 词汇表有对拍测试守卫），且 entitlement-defaults.json 同批升版
