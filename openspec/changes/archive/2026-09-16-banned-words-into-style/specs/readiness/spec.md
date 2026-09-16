# readiness 变更（增量）

## MODIFIED Requirements

### Requirement: Unified readiness endpoint

- GET /api/novels/{project_id}/readiness SHALL return {complete, missing:[{key,label,jump}], warning}.
- complete SHALL be true when all 7 content-based checks pass (synopsis, genre, world, story-arc, style, hooks, characters).
- ai-model SHALL NOT be part of the readiness check.
- missing items SHALL use Chinese labels; jump SHALL map to the frontend settings tree node id (genre/world/characters/story-arc/style/hooks) or "synopsis" for the global synopsis card.
- warning SHALL be a human-readable Chinese message.

#### Scenario: Readiness reflects content state on demand
- Given a novel whose settings files carry template defaults (not user-filled)
- When readiness is fetched
- Then the result reflects actual content state (defaults count as content; user-filled content counts; both judged uniformly)

#### Scenario: All filled becomes complete
- Given a novel where synopsis, genre, world(details), style.role, story-arc, hooks and characters are all filled
- When readiness is fetched
- Then complete is true and warning is empty

#### Scenario: ai-model does not affect readiness
- Given a novel with all 7 content checks passing
- When the author selects or clears the AI model
- Then readiness stays complete

#### Scenario: anti-ai 不再是独立检查项
- Given a novel whose banned words live in the style KV (post-migration) with everything else filled
- When readiness is fetched
- Then complete is true and the missing list contains no anti-ai entry

### Requirement: Content-based checkers (single source of truth)

- Each of the 7 items SHALL have a pure-function checker registered in one READINESS_CHECKERS table.
- synopsis SHALL pass when story.yaml.synopsis is non-empty.
- genre SHALL pass when settings/genre.yaml.genre_id is non-empty.
- world SHALL pass when any of stage/power/cost is non-empty OR any entry in history/factions/constraints/extra carries a non-empty value (v2 shape; legacy v1 shapes SHALL be normalized at the read boundary before judging).
- story-arc SHALL pass per the「arc 内容判据」requirement (fullstory or ending 三问任一非空；legacy premise 归一后判)——本 delta 不改其判据，仅随 anti-ai 退役并入清单计数。
- style SHALL pass when role is non-empty (judged on the normalized style KV: legacy narrator_role/tone.pov SHALL be merged into role at the read boundary first, so legacy-filled books stay filled).
- hooks SHALL pass when the foreshadow ledger (novel_hooks) has at least one row whose description is non-empty after trimming, regardless of status (active/resolved/abandoned all count —「任意状态」). The checker reads the ledger table, not settings KV; the judge threshold itself is unchanged by this change.
- characters SHALL pass when the book has at least one character card whose 名称 is non-empty (unnamed placeholder cards count as empty). Readiness only judges 内容非空：确认门禁的两档要求（主角六项等）归 character-settings 的确认端点，readiness SHALL NOT 重复裁决，也 SHALL NOT 读确认记录。
- 禁用词内容 SHALL NOT 单独参与 readiness（收编后归文风面板，词表有无不影响门禁——禁用词面板原 canDefer 语义由文风面板继承）。

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

#### Scenario: 旧键老书文风不降级
- **WHEN** 存量书 style KV 无 role、有 narrator_role「第三人称限知」
- **THEN** 归一边界把其并入 role，style 判「已填」

#### Scenario: 量化层不参与 readiness
- **WHEN** 某书有 style-quant（已蒸馏）或没有
- **THEN** readiness 的 style 判定与 style-quant 无关（蒸馏是 PRO 功能不入门禁）

#### Scenario: 清空禁用词不退回未填
- **WHEN** 作者清空文风面板禁用词与句式规则后重新拉 readiness
- **THEN** style 判定不变（只看 role 非空），不因词表为空报缺失
