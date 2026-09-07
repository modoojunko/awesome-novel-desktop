# tier-gating Specification

## Purpose
TBD - created by archiving change 003-two-tier-foundation. Update Purpose after archive.

## Requirements

### Requirement: License tier single source of truth

- The system SHALL provide a `LicenseProvider` React context mounted above the novel workspace that exposes the current user's tier and entitlement to all descendants.
- On mount, the provider SHALL call the verify endpoint at most once and cache the response at module level, so remounting or multiple provider instances do not issue duplicate requests.
- The provider SHALL expose `{ tier, isFree, isPro, isMember, entitlement, entitlementDegraded, trialRemainingDays, loading, error, refetch }`.
- `isFree` SHALL be `true` when the user is **非有效会员**（`!isMember`，即免费层或已过期——与后端 check_permission 口径一致）；`isPro` SHALL equal `isMember`（有效会员即 PRO 待遇，含归一化档位 pro/max）。
- `entitlement` SHALL be the raw entitlement snapshot from the verify response when present; `entitlementDegraded` SHALL be true when the backend reports the snapshot failed integrity checks and was served from fallback.
- On network failure or non-OK response, the provider SHALL degrade to `tier: "none"` (`isFree: true`) and set `error`, without throwing to the tree.
- `refetch` SHALL clear the module-level cache, re-run the verify request, and update state.
- **路由切换刷新是两跳**：进入工作台或书列表（60 秒去抖）SHALL 先请求 `/auth/check-auth`（S端 静默往返、更新本地快照），再调用 `refetch` 刷新上下文；SHALL NOT 引入定时轮询。只调 verify 不调 check-auth 的实现 SHALL NOT 视为满足本条。

#### Scenario: Provider fetches tier once

- Given a mounted LicenseProvider with no cached verify result
- When it mounts
- Then it calls the verify endpoint once and provides `{tier, isFree, isPro, isMember, entitlement}` to descendants

#### Scenario: Remount reuses cached tier

- Given a LicenseProvider that has already fetched a paid tier
- When a new provider instance mounts without refetch
- Then no additional verify request is issued and descendants receive the cached tier

#### Scenario: Free tier reports isFree

- Given a verify response with `tier: "none"`
- When the provider state is computed
- Then `isFree` is true and `isPro` is false

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
- THEN 先请求 /auth/check-auth（S端 往返更新本地快照），随后 refetch 刷新上下文；60 秒内再次切换不再触发

## ADDED Requirements

### Requirement: useTier hook

- The system SHALL provide a `useTier()` hook returning the nearest `LicenseContext` value.
- When called outside a `LicenseProvider`, the hook SHALL return safe defaults `{ tier: "none", isFree: true, isPro: false, loading: false, error: null, refetch }` and SHALL NOT throw.

#### Scenario: Descendant reads tier
- Given a component inside a LicenseProvider
- When it calls `useTier()`
- Then it receives the provider's `{tier, isFree, isPro}`

#### Scenario: useTier outside provider is safe
- Given a component not wrapped by LicenseProvider
- When it calls `useTier()`
- Then it receives free defaults without throwing

### Requirement: Feature capability registry

- The system SHALL provide `lib/features.ts` defining a `FeatureKey` union type, a `FEATURES: Record<FeatureKey, {free: boolean}>` map, and a pure function `isFeatureEnabled(key, tier): boolean`.
- `isFeatureEnabled` SHALL return `true` for features whose `free` flag is true, regardless of tier.
- For features whose `free` flag is false, it SHALL return `true` only when `tier !== "none"` (paid).
- Free-enabled keys SHALL be exactly: `tree-crud`, `prose-edit`, `version-history`, `archive`, `volume-chapter-config`, `advanced-config-entry`, `settings-7-items`.
- Free-locked keys SHALL be exactly: `settings-ai-fields`, `outline-advanced-fields`, `ai-generate`, `prompt-panel`, `ai-model`.
- The module SHALL have no DOM dependency (pure TS).

#### Scenario: Free disabled AI features
- Given a tier of "none"
- When `isFeatureEnabled("ai-generate", "none")` is evaluated
- Then it is false

#### Scenario: Paid enables AI features
- Given a paid tier such as "monthly"
- When `isFeatureEnabled("ai-generate", "monthly")` is evaluated
- Then it is true

#### Scenario: Free core writing features always enabled
- Given a tier of "none"
- When `isFeatureEnabled("prose-edit", "none")` and `isFeatureEnabled("archive", "none")` are evaluated
- Then both are true

### Requirement: TierGate and TierField components

- The system SHALL provide `components/novel/license/FeatureTier.tsx` exporting `TierGate` and `TierField`.
- `<TierGate feature>` SHALL render its children only when `isFeatureEnabled(feature, tier)` is true; otherwise render nothing.
- `<TierField feature locked>` SHALL render the field skeleton; when the feature is disabled, it SHALL render a lock indicator (🔒 / "属 PRO") and disable interaction, preserving the field structure for the paid unlock.

#### Scenario: Free hides AI subtree
- Given a tier of "none"
- When `<TierGate feature="ai-generate"><Button/></TierGate>` is rendered
- Then no Button is rendered

#### Scenario: Pro renders gated content
- Given a paid tier
- When `<TierGate feature="ai-generate"><Button/></TierGate>` is rendered
- Then the Button is rendered

#### Scenario: Free shows locked field
- Given a tier of "none"
- When `<TierField feature="settings-ai-fields" locked>…</TierField>` is rendered
- Then a lock indicator is present and the inner input is disabled

### Requirement: Feature capability registry（词汇表 + 快照缺失兜底）

- `features.ts` SHALL 维护 FeatureKey 词汇表与静态注册表 `FEATURES: Record<FeatureKey, { memberOnly: boolean }>` 及 `isMemberFeature(key)`；注册表 SHALL 仅作词汇表与**快照缺失时的兜底口径**，快照存在时判定权归快照（见 useFeature）。
- WHEN 快照存在，注册表 memberOnly SHALL NOT 参与判定。

#### Scenario: Registry is vocabulary not authority

- GIVEN 快照存在且含 "ai-generate"
- WHEN useFeature("ai-generate") 被调用
- THEN 判定来自快照而非注册表

### Requirement: useFeature hook

- The system SHALL provide a `useFeature(key)` hook returning whether the feature is enabled.
- WHEN 完整快照存在：enabled = 快照 features 包含该 key。
- WHEN 快照缺失：enabled SHALL 回退为静态注册表的 memberOnly 取值的否定（免费功能 true、会员功能 false）。
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

- GIVEN 无快照
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
