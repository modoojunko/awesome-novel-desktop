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
- hooks SHALL pass when the hooks list has at least one valid hook.
- characters SHALL pass when settings/character-setting/ contains at least one yaml.

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
