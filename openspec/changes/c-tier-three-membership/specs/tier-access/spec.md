## MODIFIED Requirements

### Requirement: Tier bypass predicate

- The system SHALL provide `tier_bypass()` returning True exactly when the current user has no paid entitlement.
- A user has no paid entitlement when their tier is `none` or `free`, OR when `check_permission()` reports `allowed=False` (e.g. expired/invalid paid subscription, **trial without expiry in production——与过期同口径：allowed=False、免费基线，从而 tier_bypass=True 走免费旁路**).
- The predicate SHALL NOT be a bare string equality on tier alone; expired paid users SHALL be treated as free.
- `check_permission()` 的会员判定源 SHALL 为权益快照优先：完整快照下 `is_member` 由快照自证（features 非空或建书上限不限）、`project_limit` 取快照 `limits.max_projects`；无快照时按**档位目录缓存**兜底（目录亦无时按已知档兜底名单，须含 free/pro/max/trial 及存量档位名 standard/monthly/quarterly/yearly/lifetime）。
- **主判定分支 SHALL 为通用规则**：`none`/`free` 直接免费基线；**其余任何档名一律进入快照/目录判定**——档位枚举名单 SHALL NOT 作为快照存在时的准入闸。
- 无快照且目录缓存命中时，SHALL 按目录行**合成 features**（该档标准权益），供 feature 门禁消费；SHALL NOT 只置 is_member 而不带 features。
- **三档会员口径（2026-11-25）**：`free`＝标准（免费）档，`is_member=False`、`project_limit=1`；`pro`/`max`＝有效会员、`project_limit=None`；存量 `standard` 作为 legacy 付费档保留到到期，`is_member` 与 `project_limit=3` 按快照/目录判定，不再新售。

#### Scenario: 标准（免费）档 bypasses

- Given a local config with `tier: "free"`
- When tier_bypass is evaluated
- Then it is True and project_limit is 1

#### Scenario: None tier bypasses

- Given a local config with `tier: "none"`
- When tier_bypass is evaluated
- Then it is True

#### Scenario: Expired paid tier bypasses

- Given a local config with a paid tier whose `expires_at` is in the past
- When tier_bypass is evaluated
- Then it is True

#### Scenario: PRO with snapshot is member

- Given 本地 tier 为 "pro" 且快照 features 非空、max_projects 为 null
- When check_permission is evaluated
- Then is_member is True and project_limit is None

#### Scenario: MAX with snapshot is member

- Given 本地 tier 为 "max" 且快照 features 非空、max_projects 为 null
- When check_permission is evaluated
- Then is_member is True and project_limit is None

#### Scenario: 存量 standard 保留会员（不再新售）

- Given 本地 tier 为 "standard" 且快照完整（legacy features、max_projects=3）
- When check_permission is evaluated
- Then is_member is True、project_limit 为 3、tier_bypass 为 False；该档不在新售目录

#### Scenario: Unknown tier name enters snapshot path

- Given 本地 tier 为一个新增档位键（代码不认识）且快照完整
- When check_permission is evaluated
- Then 判定按快照走（SHALL NOT 因名单不含该键而落免费基线）

#### Scenario: Trial without expiry is free in production

- Given tier 为 "trial"、expires_at 为空、且未设置开发/测试宽限环境变量
- When check_permission is evaluated
- Then allowed 为 False（与过期同口径）、is_member 为 False、project_limit 为 1，tier_bypass 为 True（走免费旁路）

#### Scenario: Free tier bypasses

- Given a local config with `tier: "none"`
- When tier_bypass is evaluated
- Then it is True

#### Scenario: Active paid tier does not bypass

- Given a local config with an unexpired paid tier and a complete member snapshot
- When tier_bypass is evaluated
- Then it is False

#### Scenario: Normalized tier pro with snapshot is member

- Given 本地 tier 为 "pro" 且快照 features 非空、max_projects 为 null
- When check_permission is evaluated
- Then is_member is True and project_limit is None

#### Scenario: Normalized tier pro without snapshot falls back

- Given 本地 tier 为 "pro" 且无快照（旧服务端）
- When check_permission is evaluated
- Then is_member is True and project_limit is None

#### Scenario: Standard tier with snapshot is member（不再被名单拦截）

- Given 本地 tier 为 "standard"（存量 legacy）且快照完整（features 含 ai-plan、max_projects=3）
- When check_permission is evaluated
- Then is_member is True、project_limit 为 3、tier_bypass 为 False

#### Scenario: Standard without snapshot synthesizes features from catalog

- Given 本地 tier 为 "standard"（存量 legacy）、无快照、档位目录缓存含 standard 行
- When check_permission is evaluated
- Then 判定按目录行合成 features（legacy standard key 齐备），feature 门禁可正常消费

### Requirement: AI settings field generation gated

- `POST /settings/ai/{stype}/{field}` SHALL be gated by feature key `settings-ai-fields`（**PRO 起发放**；`require_ai_access` 的 feature 化形态）。
- Calling it without an API Key under 标准（免费）/expired tier SHALL return 403/503 (gate), not 500 or bypass；PRO/MAX 命中该 key 时放行；存量 `standard` 快照含该 key 时按 grandfathering 放行。

#### Scenario: 标准（免费）field generation rejected

- Given a 标准（免费）user with no API Key
- When POST /settings/ai/world/tech_level is called
- Then the response is 403 (or 503), not 500 and not a generated value

#### Scenario: PRO field generation allowed

- Given a PRO user whose snapshot contains "settings-ai-fields" and an active API Key
- When POST /settings/ai/{stype}/{field} is called with valid premise
- Then it proceeds

#### Scenario: 存量 standard 快照 grandfathering

- Given a legacy standard user whose snapshot still contains "settings-ai-fields"
- When POST /settings/ai/{stype}/{field} is called with valid premise
- Then it proceeds until the legacy entitlement expires

#### Scenario: Free field generation rejected

- Given a 标准（免费）user with no API Key
- When POST /settings/ai/world/tech_level is called
- Then the response is 403 (or 503), not 500 and not a generated value

#### Scenario: Standard field generation allowed

- Given a legacy standard user whose snapshot contains "settings-ai-fields" and an active API Key
- When POST /settings/ai/{stype}/{field} is called with valid premise
- Then it proceeds（存量权益 grandfathering，到期后回标准免费）

#### Scenario: PRO field generation unaffected

- Given a PRO user with an active API Key
- When POST /settings/ai/{stype}/{field} is called with valid premise
- Then it proceeds as before

## ADDED Requirements

### Requirement: Three-tier membership baseline

- 会员体系 SHALL 仅含三档：**标准（免费）**、**PRO**、**MAX**；`free`/`pro`/`max` 为内部键，`standard` 仅作存量兼容。
- 标准（免费）SHALL：`max_projects=1`、1 台设备、无官方库/无 AI 写手/无拆书/无人味检测/无 AI 图像。
- PRO SHALL：书不限、3 台设备、官方库 + AI 写手（规划/章纲/正文/执行，每写必确认）+ AI 拆书/导入 + 朱雀 + 提示词。
- MAX SHALL：书不限、5 台设备、PRO 全部 + 人味检测/逐行修改指引 + AI 图像 + 拆书建书 + 发散/推演/蒸馏 + 全权托管。
- 试用 SHALL 为 7 天 PRO，不发放 MAX 独有权益。

#### Scenario: 标准（免费）额度

- Given a 标准（免费）user
- When 创建第二本书
- Then 后端按 max_projects=1 拒绝并给出升级出口（PRO）

#### Scenario: PRO 额度

- Given a PRO user
- When 创建第三本书
- Then 允许（max_projects=null）

#### Scenario: 试用不送 MAX

- Given a 7 天试用用户
- When 访问人味检测/AI 图像/拆书建书
- Then 均锁定并走 MAX 升级出口；AI 写手/官方库/拆书可用

#### Scenario: 存量 standard 不追溯降级

- Given 一个未到期的存量 standard 用户
- When 升级到本版本
- Then 其原权益保留到到期；到期后回标准（免费）或按 PRO 升级券续费
