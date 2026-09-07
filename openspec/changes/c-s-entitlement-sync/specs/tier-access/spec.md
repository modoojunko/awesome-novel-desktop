# tier-access 变更（Delta）

## MODIFIED Requirements

### Requirement: Tier bypass predicate

- The system SHALL provide `tier_bypass()` returning True exactly when the current user has no paid entitlement.
- A user has no paid entitlement when their tier is `none`, OR when `check_permission()` reports `allowed=False` (e.g. expired/invalid paid subscription, **trial without expiry in production——与过期同口径：allowed=False、免费基线，从而 tier_bypass=True 走免费旁路**）。
- The predicate SHALL NOT be a bare string equality on tier alone; expired paid users SHALL be treated as free.
- `check_permission()` 的会员判定源 SHALL 为权益快照优先：完整快照下 `is_member` 由快照自证（features 非空或建书上限不限）、`project_limit` 取快照 `limits.max_projects`；无快照时按档位兜底名单（须含 trial/pro/max 及历史档位名 monthly/quarterly/yearly/lifetime）判定。
- 档位白名单 SHALL NOT 出现在快照存在的主判定路径上。

#### Scenario: Free tier bypasses

- Given a local config with `tier: "none"`
- When tier_bypass is evaluated
- Then it is True

#### Scenario: Expired paid tier bypasses

- Given a local config with a paid tier whose `expires_at` is in the past
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

#### Scenario: Trial without expiry is free in production

- Given tier 为 "trial"、expires_at 为空、且未设置开发/测试宽限环境变量
- When check_permission is evaluated
- Then allowed 为 False（与过期同口径）、is_member 为 False、project_limit 为 1，tier_bypass 为 True（走免费旁路）

### Requirement: Tier-or-gate wrapper

- The system SHALL provide `tier_or_gate(db, project, gate_fn, *args)` that delegates to `gate_fn(*args)` when `tier_bypass()` is False (PRO path).
- When `tier_bypass()` is True, it SHALL return `GateResult(valid=True, warnings=[], hard_block=False)` WITHOUT invoking `gate_fn`.
- The PRO path SHALL return the gate function's `GateResult` unchanged (hard_block semantics preserved).

#### Scenario: Free bypasses gate without invoking it

- Given tier is none and a gate function that records invocations
- When tier_or_gate is called
- Then the gate function is not invoked and the result is valid with no warnings

#### Scenario: PRO runs the gate

- Given an unexpired paid member with a member snapshot
- When tier_or_gate is called
- Then the gate function runs and its GateResult is returned unchanged
