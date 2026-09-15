# readiness Specification

## Purpose
TBD - created by archiving change settings-readiness. Update Purpose after archive.

## Requirements

### Requirement: Unified readiness endpoint
- GET /api/novels/{project_id}/readiness SHALL return {complete, missing:[{key,label,jump}], warning}.
- complete SHALL be true when all 7 content-based checks pass (synopsis, genre, world, style, anti-ai, hooks, characters).
- ai-model SHALL NOT be part of the readiness check.
- missing items SHALL use Chinese labels; jump SHALL map to the frontend settings tree node id (genre/world/style/anti-ai/hooks/characters) or "synopsis" for the global synopsis card.
- warning SHALL be a human-readable Chinese message.

#### Scenario: Readiness reflects content state on demand
- Given a novel whose settings files carry template defaults (not user-filled)
- When readiness is fetched
- Then the result reflects actual content state (defaults count as content; user-filled content counts; both judged uniformly)

#### Scenario: All filled becomes complete
- Given a novel where synopsis, genre, world(details), style.role, anti-ai, hooks and characters are all filled
- When readiness is fetched
- Then complete is true and warning is empty

#### Scenario: ai-model does not affect readiness
- Given a novel with all 7 content checks passing
- When the author selects or clears the AI model
- Then readiness stays complete

### Requirement: Judge on "complete setting" action (product decision)
- The system SHALL NOT judge settings completion at novel creation time.
- Completion SHALL be judged when the author clicks the per-item "完成设定" (ConfirmToggle) action.
- On click, the system SHALL check that item's content against the readiness rule (non-empty / threshold).
- If the content is sufficient, the item SHALL be marked complete.
- If insufficient, the system SHALL return which items are missing and NOT mark complete.

#### Scenario: Create does not judge
- Given an author creates a novel with only a name
- Then no settings-completion judgment or "incomplete" prompt is shown

#### Scenario: Click complete on unfilled item
- Given a novel where world details are all empty
- When the author clicks "完成设定" on the world item
- Then the item is NOT marked complete and the missing detail is reported in Chinese

#### Scenario: Click complete on filled item
- Given a novel where style.role carries the template default (non-empty)
- When the author clicks "完成设定" on the style item
- Then the item IS marked complete (defaults count as content)

### Requirement: Content-based checkers (single source of truth)

- Each of the 7 items SHALL have a pure-function checker registered in one READINESS_CHECKERS table.
- synopsis SHALL pass when story.yaml.synopsis is non-empty.
- genre SHALL pass when settings/genre.yaml.genre_id is non-empty.
- world SHALL pass when any of stage/power/cost is non-empty OR any entry in history/factions/constraints/extra carries a non-empty value (v2 shape; legacy v1 shapes SHALL be normalized at the read boundary before judging).
- style SHALL pass when role is non-empty.
- anti-ai SHALL pass when settings/anti-ai.yaml has content.
- hooks SHALL pass when the foreshadow ledger (novel_hooks) has at least one row whose description is non-empty after trimming, regardless of status (active/resolved/abandoned all count —「任意状态」). The checker reads the ledger table, not settings KV; the judge threshold itself is unchanged by this change.
- characters SHALL pass when the book has at least one character card whose 名称 is non-empty (unnamed placeholder cards count as empty). Readiness only judges 内容非空：确认门禁的两档要求（主角六项等）归 character-settings 的确认端点，readiness SHALL NOT 重复裁决，也 SHALL NOT 读确认记录。

#### Scenario: World v2 stage-only counts as filled
- Given a world setting where only stage is non-empty
- When readiness is fetched
- Then world is not reported missing

#### Scenario: World entries-only counts as filled
- Given a world setting where only one extra entry has a non-empty value
- When readiness is fetched
- Then world is not reported missing

#### Scenario: World legacy v1 normalizes before judging
- Given a world setting still in the legacy ten-field shape with geography.scenes non-empty
- When readiness is fetched
- Then world is not reported missing (legacy normalized to stage before the check)

#### Scenario: World fully filled is never incomplete
- Given a world setting with all v2 fields filled (stage/power/cost plus history/factions/constraints/extra entries)
- When readiness is fetched
- Then world is not reported missing (regression for the old ≥5-top-level-fields bug)

#### Scenario: World fully empty is incomplete
- Given a world setting where stage/power/cost are empty and all entry lists are empty
- When the author clicks "完成设定" on the world item
- Then world is reported missing in Chinese

#### Scenario: Characters first confirmation
- Given a book whose 角色 item has never been confirmed
- And its protagonist card carries a name and a one-line persona
- When the author confirms the 角色 item
- Then the item is marked complete

#### Scenario: Characters later confirmation names the gaps
- Given the 角色 item has been confirmed before
- And one supporting character is missing 能力代价
- When the author confirms the 角色 item again
- Then the item is not marked complete and the missing fields are reported in Chinese with the character name

#### Scenario: Content change sends the item back
- Given the 角色 item is confirmed
- When the protagonist is deleted, the protagonist is switched, or one of the six required fields is cleared
- Then readiness reports characters as missing again
- And the stale state (「内容有变 · 待重新确认」, without the word 已确认) is derived by `GET /settings/status` from the confirmation record, NOT by readiness (readiness stays a pure content predicate and SHALL NOT read or write the confirmation record)

#### Scenario: 空名卡不算已填
- **WHEN** 书中只有一张未命名（或名字全空白）的空卡
- **THEN** readiness 把 characters 报为未填

#### Scenario: 一张有名卡即已填
- **WHEN** 书中有一张名字非空的角色卡（哪怕只填了名字）
- **THEN** readiness 不把 characters 报为未填

#### Scenario: hooks judge reads the ledger in any status
- Given a book whose only non-empty hooks are all in resolved or abandoned status
- When readiness is fetched
- Then hooks is not reported missing

#### Scenario: hooks empty ledger still counts as missing
- Given a book with zero hook rows (or all descriptions whitespace-only)
- When readiness is fetched
- Then hooks is reported missing
### Requirement: Gate convergence
- gate_settings_complete SHALL be refactored to call the same READINESS_CHECKERS subset for settings.
- Settings gate warnings SHALL be Chinese and SHALL carry a jump target.
- get_phase_status SHALL consume the readiness result for the settings phase.
- settings-status.yaml SHALL NOT be an input to readiness (kept deprecated, not deleted).

#### Scenario: Phase status matches readiness
- Given a novel whose readiness is complete
- When phase status is fetched
- Then the settings phase is not reported with warnings

### Requirement: Soft gate preserved
- Readiness SHALL NOT hard-block transitions; complete=false SHALL only produce guidance.
- The frontend SHALL offer both "先去补设定" and "仍然继续" when incomplete.

#### Scenario: Proceed while incomplete
- Given a novel with incomplete settings
- When the author tries to start outlining
- Then the transition is allowed and the UI shows both "先去补设定" and "仍然继续" options

### Requirement: arc 内容判据（第 05 项主线）

- arc SHALL 进 readiness 内容判据（与既有 7 项同表注册）：`story_arc.fullstory` 或 `ending{scene, hero, tone}` 任一非空即已填
- legacy 形状 SHALL 在读取边界归一后再判：legacy `premise` 非空即视为已填（迁移由存储层双写承载，判据只看归一后的形状）
- arc 全空 SHALL 报未填（中文），且空内容确认被后端 400 拒绝（沿「完成设定」判据，defaults 不适用于本项——主线无默认内容）

#### Scenario: 只有全景即已填
- **WHEN** 主线只填了 fullstory，三问全空
- **THEN** arc 不报缺失

#### Scenario: 只有基调即已填
- **WHEN** 主线只填了 ending.tone
- **THEN** arc 不报缺失

#### Scenario: legacy premise 书归一为已填
- **WHEN** 旧书 story_arc 只有 legacy premise 非空
- **THEN** arc 不报缺失

#### Scenario: 全空报未填
- **WHEN** 主线没有任何内容时点击「确认完成」
- **THEN** arc 报缺失（中文），确认被 400 拒绝
