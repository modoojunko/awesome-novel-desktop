## MODIFIED Requirements

### Requirement: Shared status language and tone words
- Progress-bearing objects SHALL express state through the three-state dot classes (`dot-empty`, `dot-warn`, `dot-ok`) plus a title attribute wherever progress semantics exist.
- Evidence-bearing chapter rows in the reading preview (目录行) SHALL NOT use the three-state dot; they SHALL express 成稿状态 through the `.pill` status family with the labels 拟定 / 草稿 / 已归档, plus a word-count number in the mono/tabular style. 章纲 gap detail stays in the writing view.
- Badges SHALL use the `.pill` family (roles tag/status/count x tones); callout bars SHALL use the `.notice` family with explicit modifiers; toast severity may add `warn`.
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
