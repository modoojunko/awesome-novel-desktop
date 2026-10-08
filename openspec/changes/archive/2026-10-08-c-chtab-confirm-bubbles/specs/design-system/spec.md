## MODIFIED Requirements

### Requirement: Shared status language and tone words

- Progress-bearing objects SHALL express state through the three-state dot classes (`dot-empty`, `dot-warn`, `dot-ok`) plus a title attribute wherever progress semantics exist.
- Evidence-bearing chapter rows in the reading preview (目录行) SHALL NOT use the three-state dot; they SHALL express 成稿状态 through the `.pill` status family with the labels 拟定 / 草稿 / 已归档, plus a word-count number in the mono/tabular style. 章纲 gap detail stays in the writing view.
- Badges SHALL use the `.pill` family (roles tag/status/count x tones); callout bars SHALL use the `.notice` family with explicit modifiers; toast severity may add `warn`.
- **待确认（AI 产出等作者裁决）为新增对象状态行**（design-language §5.1 同批加行）：页签行待确认计数 SHALL 以 count role × accent tone 软底泡泡表达（清零自消，非恒显警示），台账节奏类计数（如「该收 N」）SHALL 用 count role × warn tone；实底填充与新胶囊形态 SHALL NOT 引入（含微信式实底红——红色按 N6 保留给不可逆/即时生效，阻断缺项沿用既有 err 表达）。
- The cross-end tone vocabulary is fixed at info / ok / warn / err. Retired synonyms (success/danger as notice or badge tones, the `.b` badge names, `.strip`) MUST NOT reappear. The save-state ladder remains autosaving, unsaved, failed-with-retry, saved.
- Streaming/AI activity SHALL be expressed by a breathing accent dot; prose layout MUST NOT animate during streaming.

#### Scenario: Same object viewed twice
- Given a chapter with a fixed 成稿状态 (无正文 / 有正文未归档 / 已归档)
- When the preview view lists that chapter
- Then the 目录行 shows the matching `.pill` status label (拟定 / 草稿 / 已归档) derived from the same chapter data, with the word count in mono/tabular style — never a three-state dot

#### Scenario: S端 console uses unified badge and notice vocabulary
- Given any S端 console, auth or landing screen needs a badge or a callout bar
- When the page renders
- Then badges use `.pill` role × tone classes and callout bars use `.notice` with an explicit tone, and no `.b` or `.strip` class remains in S端 source or rendered DOM

#### Scenario: 页签待确认泡泡用既有词汇组合
- Given the chapter workbench needs a pending-confirmation count on a tab
- When the bubble is rendered
- Then it composes existing `.pill` count role with an existing tone (accent for 待确认 / warn for 台账节奏), shows a number with a title attribute, and disappears at zero — no solid fill, no red, no fourth capsule form
