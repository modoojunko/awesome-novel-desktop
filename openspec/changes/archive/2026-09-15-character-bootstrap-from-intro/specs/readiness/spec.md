## Purpose

修正 readiness 中 characters 判定：从「存在任意一张卡」收紧为「存在至少一张名字非空的卡」，并钉死 readiness 只判内容非空、两档确认门禁归 character-settings 的分工（消除与 character-settings-v2 实现的口径漂移）。

## MODIFIED Requirements

### Requirement: Content-based checkers (single source of truth)

- Each of the 7 items SHALL have a pure-function checker registered in one READINESS_CHECKERS table.
- synopsis SHALL pass when story.yaml.synopsis is non-empty.
- genre SHALL pass when settings/genre.yaml.genre_id is non-empty.
- world SHALL pass when any of stage/power/cost is non-empty OR any entry in history/factions/constraints/extra carries a non-empty value (v2 shape; legacy v1 shapes SHALL be normalized at the read boundary before judging).
- style SHALL pass when role is non-empty.
- anti-ai SHALL pass when settings/anti-ai.yaml has content.
- hooks SHALL pass when the hooks list has at least one valid hook.
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
