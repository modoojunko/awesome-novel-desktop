## MODIFIED Requirements

### Requirement: License tier single source of truth

- The system SHALL provide a `LicenseProvider` React context mounted above the novel workspace that exposes the current user's tier and entitlement to all descendants.
- On mount, the provider SHALL call the verify endpoint at most once and cache the response at module level, so remounting or multiple provider instances do not issue duplicate requests.
- The provider SHALL expose `{ tier, isFree, isStandard, isPro, isMax, isMember, entitlement, entitlementDegraded, trialRemainingDays, loading, error, refetch }`。
- `isFree` SHALL be `true` when the user is **非有效会员**（`!isMember`，即标准（免费）层或已过期——与后端 check_permission 口径一致）。
- **三档会员（2026-11-25 拍板）**：`free` 为**标准（免费）**档（展示名“标准”）；`pro` 为 AI 写手；`max` 为写作秘书；`standard` 仅保留为**存量付费标准档（grandfathered）**，不再新售。`isMember` SHALL 为「有效会员」（快照 features 非空或建书上限不限，含 pro/max/trial 与存量 standard）；`isStandard` SHALL 为 tier 命中 `free`（标准免费）或存量 `standard`；`isPro`/`isMax` SHALL 分别为 tier 命中 `pro`／`max`。功能级锁定判定 SHALL 使用 `useFeature(key)`，SHALL NOT 用 isPro 做功能门控。
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

#### Scenario: 标准（免费）档报非会员但 isStandard

- Given a verify response with `tier: "free"`
- When the provider state is computed
- Then `isFree` is true、`isMember` is false、`isStandard` is true、`isPro`/`isMax` 为 false

#### Scenario: 存量 standard 报会员不再新售

- Given a verify response with `tier: "standard"` and a legacy paid snapshot
- When the provider state is computed
- Then `isMember` is true、`isStandard` is true、`isFree` is false（存量权益保留，销售目录不再出现该档）

#### Scenario: PRO member

- Given a verify response with `tier: "pro"` and a snapshot containing `ai-plan`
- When the provider state is computed
- Then `isMember` is true、`isPro` is true、`isStandard` 为 false

#### Scenario: MAX member

- Given a verify response with `tier: "max"`
- When the provider state is computed
- Then `isMax` is true、`isPro` 为 false、`isStandard` 为 false

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

#### Scenario: Free tier reports isFree

- Given a verify response with `tier: "none"` or `tier: "free"`
- When the provider state is computed
- Then `isFree` is true and `isMember` is false

#### Scenario: Standard member reports member but not pro

- Given a verify response with `tier: "standard"`（存量 legacy）and a features array containing `ai-plan`
- When the provider state is computed
- Then `isMember` is true、`isStandard` is true、`isPro` is false（存量权益保留，不再新售）

### Requirement: Feature capability registry

- The system SHALL provide `lib/features.ts` defining a `FeatureKey` union type, a `FEATURES: Record<FeatureKey, { minTier: "free" | "standard" | "pro" | "max" }>` map, and helper `minTierOf(key)`；`isMemberFeature(key)`（=minTier !== "free"）SHALL 保留为兼容派生。
- `minTierOf` SHALL return `"free"` for free capabilities regardless of tier；`"pro"`/`"max"` 为该功能所需的最低档（入口一律可见；**使用**由后端按 feature key 门禁统一拦截，前端弹对应档位的升级引导）。`"standard"` 仅为存量 legacy 快照兼容保留，SHALL NOT 被任何新 key 使用。
- Free-enabled keys SHALL be exactly: `tree-crud`, `prose-edit`, `version-history`, `archive`, `volume-chapter-config`, `advanced-config-entry`, `settings-7-items`, **`ai-model`**。
- 会员功能 key 及其最低档 SHALL be exactly:
  - `ai-plan`（**PRO 起**）：流程 AI 全家——卷规划三套走法/铺空缺、拆章三方向、帮写剧情三选一、章纲起草/补缺、人物盘点（含抽卡）、卷体检、建书元信息建议；
  - `chapter-review`（**PRO 起**）：章自检 AI 短评；
  - `settings-ai-fields`（**PRO 起**）：设定域右栏 AI 全家；
  - `outline-advanced-fields`（**PRO 起**）：章纲高级字段 AI 填充；
  - `style-suggest`（**PRO 起**）：文风建议（AI 修改建议）；
  - `assistant-execute`（**PRO 起**）：助理可授权执行写操作（每写必确认）；
  - `ai-generate`（PRO 起）：正文 AI 全家（生成/润色/提示词润色）＋workbench 六类案头检查（ai-check 族）；
  - `prompt-panel`（PRO 起）：提示词页签；
  - `ai-detect`（PRO 起）：朱雀 AI 检测，PRO/trial 发放；
  - `deconstruct`（PRO 起）：AI 拆书（新建任务/续拆/重试上传/产物查看/导出 markdown/收进本地库）；
  - `kb-official`（**新，PRO 起**）：官方写作知识库读取/检索/按题材取文风；本地库（本书设定/人物/决策/条目）SHALL NOT 挂此 key；
  - `image-generate`（**MAX 起**）：AI 封面/头像/试画/批量头像；手动上传 SHALL NOT 挂此 key；
  - `human-taste`（**新，MAX 起**）：人味检测与逐行修改指引；
  - `assistant-diverge`（MAX 起）：发散起草（添人添事/剧情分支）；
  - `ai-plot`（MAX 起）：剧情推演＋story 推演会话；
  - `style-quant`（MAX 起）：文风蒸馏；
  - `deconstruct-import`（MAX 起）：拆书产物一键建书。
- 存量 `standard` 档 SHALL 保留其原快照权益（`ai-plan`/`chapter-review`/`settings-ai-fields`/`style-suggest`/`outline-advanced-fields`/`ai-model`/`assistant-execute`）供 grandfathering；该档 SHALL NOT 出现在新售目录。
- The module SHALL have no DOM dependency (pure TS).

#### Scenario: 标准（免费）档 AI 写手能力锁定

- Given a tier of "free"
- When `minTierOf("ai-plan")` / `minTierOf("ai-generate")` / `minTierOf("assistant-execute")` are evaluated
- Then each is "pro"（入口可见、使用被后端拦截）

#### Scenario: 标准（免费）档可头脑风暴

- Given 标准（免费）用户进入工作台
- When 打开写作 AI 助理
- Then 可读章节/设定/大纲并与作家对话头脑风暴；起草/写类工具呈锁定态并走 PRO 升级出口

#### Scenario: PRO 可写可执行

- Given 快照 features 含 `ai-plan`/`ai-generate`/`assistant-execute`
- When `useFeature` 被调用
- Then 三项均为 true（PRO AI 写手；每写必确认）

#### Scenario: MAX 独有质量与图像

- Given 快照不含 `human-taste`/`image-generate`
- When `useFeature("human-taste")` / `useFeature("image-generate")` 被调用
- Then 均返回 false；MAX 快照含两项时返回 true

#### Scenario: 官方库与本地库分层

- Given 标准（免费）用户
- When 访问本书知识库/决策档案
- Then 可读可编辑；访问官方写作知识库（`kb-official`）时锁定并走 PRO 升级出口

#### Scenario: 新 key 进词汇表同批挂门

- When 一个新功能 key 被加入 FEATURES 注册表
- Then 该功能的端点 SHALL 在同一变更批次声明所需 key（端点 key ∈ 词汇表有对拍测试守卫），且 entitlement-defaults.json 同批升版

#### Scenario: Free disabled AI features

- Given a tier of "none" or "free"
- When `minTierOf("ai-generate")` is evaluated
- Then it is "pro"（会员功能，入口可见、使用被后端拦截）

#### Scenario: 免费版可配置本书模型

- Given 标准（免费）用户进入设定视图
- When 查看「本书模型」面板
- Then 可选模型、可确认落库（无会员拦截），而右侧 AI 写手仍为锁定态

#### Scenario: ai-detect 对非 MAX 锁定

- Given 快照存在且 features 不含 "ai-detect"（标准（免费）/过期）
- When useFeature("ai-detect") 被调用
- Then 返回 false；PRO 起发放（PRO/MAX/trial 快照含该 key 时返回 true）

## ADDED Requirements

### Requirement: Tier labels and upgrade hints

- `tierLabel("free")` SHALL be `"标准"`；`tierLabel("pro")` SHALL be `"PRO"`；`tierLabel("max")` SHALL be `"MAX"`；存量 `standard` SHALL 显示为 `"标准会员（旧）"`。
- `upgradeHintOf(key)` SHALL 按 key 最低档输出 `"需开通（PRO 专属）"` 或 `"MAX 专属"`；SHALL NOT 再出现 `"标准档起"`。
- 档位角标/等级文案 SHALL 使用 `标准 / PRO / MAX` 三档；SHALL NOT 把免费层写成“免费版”主标签（价格区可用 `¥0 · 免费` 辅助说明）。

#### Scenario: 免费档角标

- Given 标准（免费）用户
- When 渲染档位角标
- Then 文案为「标准」而不是「免费版」

#### Scenario: PRO 功能锁定文案

- Given 标准（免费）用户点击 AI 写手功能
- When 渲染升级提示
- Then 文案为「PRO 专属 / 需开通 PRO」，不得出现「标准档起」
