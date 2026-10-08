# tier-gating Specification

## Purpose
TBD - created by archiving change 003-two-tier-foundation. Update Purpose after archive.

## Requirements

### Requirement: License tier single source of truth

- The system SHALL provide a `LicenseProvider` React context mounted above the novel workspace that exposes the current user's tier and entitlement to all descendants.
- On mount, the provider SHALL call the verify endpoint at most once and cache the response at module level, so remounting or multiple provider instances do not issue duplicate requests.
- The provider SHALL expose `{ tier, isFree, isStandard, isPro, isMax, isMember, entitlement, entitlementDegraded, trialRemainingDays, loading, error, refetch }`。
- `isFree` SHALL be `true` when the user is **非有效会员**（`!isMember`，即免费层或已过期——与后端 check_permission 口径一致）。
- **四档拆开（原 `isPro === isMember` 等价退役）**：`isMember` SHALL 为「有效会员」（快照 features 非空或建书上限不限，含 standard/pro/max/trial）；`isStandard`/`isPro`/`isMax` SHALL 分别为 tier 命中 standard／pro 与 max（pro/max 同权归一化）／max。功能级锁定判定 SHALL 使用 `useFeature(key)`，SHALL NOT 用 isPro 做功能门控（保留 isPro 仅供档位展示类用途）。
- `entitlement` SHALL be the raw entitlement snapshot from the verify response when present; `entitlementDegraded` SHALL be true when the backend reports the snapshot failed integrity checks and was served from fallback.
- On network failure or non-OK response, the provider SHALL degrade to `tier: "none"` (`isFree: true`) and set `error`, without throwing to the tree.
- `refetch` SHALL clear the module-level cache, re-run the verify request, and update state.
- **路由切换刷新是两跳**：进入工作台或书列表（60 秒去抖）SHALL 先请求 `/auth/check-auth`（S端 静默往返、更新本地快照与档位目录缓存），再调用 `refetch` 刷新上下文；SHALL NOT 引入定时轮询。只调 verify 不调 check-auth 的实现 SHALL NOT 视为满足本条。

#### Scenario: Provider fetches tier once

- Given a mounted LicenseProvider with no cached verify result
- When it mounts
- Then it calls the verify endpoint once and provides `{tier, isFree, isStandard, isPro, isMax, isMember, entitlement}` to descendants

#### Scenario: Remount reuses cached tier

- Given a LicenseProvider that has already fetched a paid tier
- When a new provider instance mounts without refetch
- Then no additional verify request is issued and descendants receive the cached tier

#### Scenario: Free tier reports isFree

- Given a verify response with `tier: "none"`
- When the provider state is computed
- Then `isFree` is true and `isMember` is false

#### Scenario: Standard member reports member but not pro

- Given a verify response with `tier: "standard"` and a features array containing `ai-plan`
- When the provider state is computed
- Then `isMember` is true, `isStandard` is true, `isPro` is false（标准档用户界面按 useFeature 分档锁定，isPro 不再驱动门控）

#### Scenario: Verify carries entitlement

- GIVEN verify 响应携带 `entitlement` 原文
- WHEN provider state is computed
- THEN `entitlement` 原文透传给 descendants，`entitlementDegraded` 为 false

#### Scenario: Degraded snapshot flags the UI

- GIVEN verify 响应带 `entitlement_degraded: true`
- WHEN provider state is computed
- THEN `entitlementDegraded` 为 true，界面据此展示权益异常客服提示条

#### Scenario: Verify failure degrades to free

- GIVEN the verify request rejects
- WHEN the provider finishes its fetch
- Then `tier` is "none", `isFree` is true, `error` is set, and no exception escapes

#### Scenario: Route change refetches with debounce

- WHEN 用户 60 秒内首次进入工作台路由
- THEN 先请求 /auth/check-auth（S端 往返更新本地快照与档位目录缓存），随后 refetch 刷新上下文；60 秒内再次切换不再触发


### Requirement: useTier hook

- The system SHALL provide a `useTier()` hook returning the nearest `LicenseContext` value.
- When called outside a `LicenseProvider`, the hook SHALL return safe defaults `{ tier: "none", isFree: true, isStandard: false, isPro: false, isMax: false, loading: false, error: null, refetch }` and SHALL NOT throw.

#### Scenario: Descendant reads tier
- Given a component inside a LicenseProvider
- When it calls `useTier()`
- Then it receives the provider's `{tier, isFree, isStandard, isPro, isMax}`

#### Scenario: useTier outside provider is safe
- Given a component not wrapped by LicenseProvider
- When it calls `useTier()`
- Then it receives free defaults without throwing

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
  - `ai-polish`（新增）：去AI味加工（热片驱动＋选区兜底的重写），仅 MAX 发放（生成时内嵌的反AI基线不设 key，全档质量底线）。
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

### Requirement: TierGate and TierField components

- The system SHALL provide `components/novel/license/FeatureTier.tsx` exporting `TierGate` and `TierField`.
- `<TierGate feature>` SHALL render its children only when `isFeatureEnabled(feature, tier)` is true; otherwise render nothing.
- `<TierField feature locked>` SHALL render the field skeleton; when the feature is disabled, it SHALL render a lock indicator with **档位感知文案**（按 minTier 出「需开通解锁」/「PRO 专属」/「MAX 专属」，SHALL NOT 出现内部术语）and disable interaction, preserving the field structure for the paid unlock.

#### Scenario: Free hides AI subtree

- Given a tier of "none"
- When `<TierGate feature="ai-generate"><Button/></TierGate>` is rendered
- Then no Button is rendered

#### Scenario: Pro renders gated content

- Given a paid tier whose snapshot contains "ai-generate"
- When `<TierGate feature="ai-generate"><Button/></TierGate>` is rendered
- Then the Button is rendered

#### Scenario: Standard sees PRO-specific lock text

- Given a standard-tier user whose snapshot contains "ai-plan" but not "ai-generate"
- When `<TierField feature="ai-generate" locked>…</TierField>` is rendered
- Then a lock indicator with「PRO 专属」口径文案 is present and the inner input is disabled（同卡上 ai-plan 行不锁）

#### Scenario: Free shows locked field

- Given a tier of "none"
- When `<TierField feature="settings-ai-fields" locked>…</TierField>` is rendered
- Then a lock indicator with升级引导出口 is present and the inner input is disabled

### Requirement: Feature capability registry（词汇表 + 快照缺失兜底）

- `features.ts` SHALL 维护 FeatureKey 词汇表与静态注册表 `FEATURES: Record<FeatureKey, { minTier }>` 及 `minTierOf(key)`；注册表 SHALL 仅作词汇表与**快照缺失时的兜底口径**，快照存在时判定权归快照（见 useFeature）。
- WHEN 快照存在，注册表 minTier SHALL NOT 参与判定；快照缺失时兜底按「本地 tier 对档位目录缓存行」判定（目录亦无时按注册表保守口径：minTier 为 free 的 true、其余 false）。

#### Scenario: Registry is vocabulary not authority

- GIVEN 快照存在且含 "ai-generate"
- WHEN useFeature("ai-generate") 被调用
- THEN 判定来自快照而非注册表

### Requirement: useFeature hook

- The system SHALL provide a `useFeature(key)` hook returning whether the feature is enabled.
- WHEN 完整快照存在：enabled = 快照 features 包含该 key。
- WHEN 快照缺失：enabled SHALL 按档位目录缓存行判定；目录亦无时回退为静态注册表保守口径（minTier 为 free 的 true、其余 false）。
- The hook SHALL NOT throw outside a `LicenseProvider`（返回安全默认值）。

#### Scenario: Snapshot grants feature

- GIVEN 快照 features 含 "ai-generate"
- WHEN useFeature("ai-generate") 被调用
- THEN 返回 true

#### Scenario: Snapshot without key

- GIVEN 快照 features 不含 "prompt-panel"
- WHEN useFeature("prompt-panel") 被调用
- THEN 返回 false

#### Scenario: Fallback without snapshot

- GIVEN 无快照且无目录缓存
- WHEN useFeature("tree-crud")（静态免费项）与 useFeature("ai-generate")（静态会员项）被调用
- THEN 分别返回 true 与 false

### Requirement: 权益异常客服提示条

- WHEN verify 响应指示 `entitlement_degraded`
- THEN 书列表 SHALL 展示权益异常提示条（notice 家族 warn 语气），文案详情含**缺失字段、档位、快照抓取时间**（可一键复制）与"联系客服"可点击出口（复用客服链接单源模块）
- WHEN 后续 verify 不再指示降级
- THEN 提示条 SHALL 消失

#### Scenario: Degraded shows support notice

- GIVEN verify 响应 entitlement_degraded 为 true
- WHEN 书列表渲染
- THEN 出现含复制详情与客服出口的 warn 提示条

#### Scenario: Recovery hides the notice

- GIVEN 提示条已展示
- WHEN 下一次 verify 成功且无降级标志
- THEN 提示条消失

### Requirement: 档位显示名单源渲染

档位展示名（徽章/账号面板/偏好弹窗/升级弹窗）SHALL 渲染快照或档位目录下发的 `display_name`（tiers 表单源），SHALL NOT 在前端按档位键写死中文名或裸显档位键英文（如 "standard"）。档位目录不可达时方可用内置兜底文案。

#### Scenario: 标准档显示名不裸显键名

- WHEN standard 用户打开账号偏好弹窗
- THEN 档位行显示 tiers.display_name 配置的展示名，而非 "standard" 字面量

#### Scenario: 新档位显示名零代码

- **WHEN** 运营在 tiers 表新增档位并配置 display_name
- **THEN** 前端各档位展示位自动渲染该名，无前端发版
