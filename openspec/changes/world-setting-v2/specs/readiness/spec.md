# readiness Specification（delta）

## MODIFIED Requirements

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
