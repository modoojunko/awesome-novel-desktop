# tier-access Specification

## Purpose
TBD - created by archiving change 002-tier-free-bypass. Update Purpose after archive.

## Requirements

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

### Requirement: Tier-aware phase transition

- The system SHALL provide `tier_phase_transition(project, new_phase)`.
- When `tier_bypass()` is True, the phase transition SHALL be forced: `current_phase` is set to `new_phase` WITHOUT validating `can_transition` (idempotent advance per O3).
- When `tier_bypass()` is False, it SHALL behave exactly like `update_phase` (validate `can_transition`, raise ValueError on illegal jump).

#### Scenario: Free archive does not raise
- Given a new novel whose current_phase is "settings" (no outline/prompt/write traversed)
- When archive calls tier_phase_transition(project, "archive") under free tier
- Then current_phase becomes "archive" and no ValueError is raised (fixes N9 500)

#### Scenario: PRO illegal jump still raises
- Given an unexpired paid tier and a novel whose current_phase is "settings"
- When tier_phase_transition(project, "archive") is called
- Then a ValueError is raised

### Requirement: Gate access points honor tier bypass

- The following access points SHALL route their gates through `tier_or_gate` and phase changes through `tier_phase_transition`:
  - `POST /volumes` (create_volume): `gate_settings_complete` via tier_or_gate.
  - `POST /chapters/{ref}/confirm` (confirm_chapter): `gate_chapter_ready` via tier_or_gate.
  - `POST /workflow/transition`: the settings/chapter-ready/prompts-exist hard gates via tier_or_gate; the phase change via tier_phase_transition.
  - `POST /chapters/{ref}/archive`: phase change via tier_phase_transition.
- Under free tier, the above SHALL succeed without the prerequisite files (memo/segments/prompts).

#### Scenario: Free confirms a sparse chapter
- Given a chapter with empty memo/segments under free tier
- When confirm_chapter is called
- Then it returns 200 and the chapter status becomes "confirmed"

#### Scenario: Free transitions without prompts
- Given a project under free tier with no prompt files
- When workflow transition targets "write"
- Then it returns 200 and the phase advances

### Requirement: Free phase-status reports bypass

- `GET /workflow/phase-status` under free tier SHALL return `tier_bypass: true` and all six phases `complete` (no phase pestering UI, N14).
- Under PRO, phase-status SHALL retain current behavior.

#### Scenario: Free phase-status is all-complete
- Given a free-tier project with an empty outline
- When phase-status is fetched
- Then response has tier_bypass true and every phase is "complete"

### Requirement: Archive is free

- `POST /chapters/{ref}/archive`, `GET /archives`, and `GET /archives/{filename}` SHALL NOT require AI access.
- Archiving SHALL succeed with no API Key configured: the AI summary is degraded to the first 200 chars of the full text when `get_ai_client()` raises or the chat call fails.
- The archive gate SHALL check `.md` archive files (fixes B4), degrading to a file scan without 500 when the DB is unavailable.

#### Scenario: Free archive without API key
- Given a free-tier user with no API Key and a chapter with ≥100 chars prose
- When the chapter is archived
- Then the request returns 200, the summary is the first 200 chars, and no 500 is raised

#### Scenario: Archive list readable for free
- Given a free-tier user
- When GET /archives and GET /archives/{filename} are called
- Then both return 200

### Requirement: AI settings field generation gated

- `POST /settings/ai/{stype}/{field}` SHALL be gated by `require_ai_access` (fixes D5).
- Calling it without an API Key under free/expired tier SHALL return 403/503 (gate), not 500 or bypass.

#### Scenario: Free field generation rejected
- Given a free-tier user with no API Key
- When POST /settings/ai/world/tech_level is called
- Then the response is 403 (or 503), not 500 and not a generated value

#### Scenario: PRO field generation unaffected
- Given a user with an active API Key and paid entitlement
- When POST /settings/ai/{stype}/{field} is called with valid premise
- Then it proceeds as before
