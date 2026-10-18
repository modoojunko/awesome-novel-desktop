## MODIFIED Requirements

### Requirement: Shared status language and tone words

- Progress-bearing objects SHALL express state through the three-state dot classes (`dot-empty`, `dot-warn`, `dot-ok`) plus a title attribute wherever progress semantics exist.
- Evidence-bearing chapter rows in the reading preview (目录行) SHALL NOT use the three-state dot; they SHALL express 成稿状态 through the `.pill` status family with the labels 拟定 / 草稿 / 原文（导入的历史章） / 已归档, plus a word-count number in the mono/tabular style. 章纲 gap detail stays in the writing view.
- Badges SHALL use the `.pill` family (roles tag/status/count x tones); callout bars SHALL use the `.notice` family with explicit modifiers; toast severity may add `warn`.
- **待确认（AI 产出等作者裁决）为新增对象状态行**：页签行待确认计数 SHALL 以 count role × accent tone 软底泡泡表达（清零自消，非恒显警示），台账节奏类计数（如「该收 N」）SHALL 用 count role × warn tone；实底填充与新胶囊形态 SHALL NOT 引入（含微信式实底红——红色按 N6 保留给不可逆/即时生效，阻断缺项沿用既有 err 表达）。
- The cross-end tone vocabulary is fixed at info / ok / warn / err. Retired synonyms (success/danger as notice or badge tones, the `.b` badge names, `.strip`) MUST NOT reappear. The save-state ladder remains autosaving, unsaved, failed-with-retry, saved.
- Streaming/AI activity SHALL be expressed by a breathing accent dot; prose layout MUST NOT animate during streaming.

#### Scenario: Same object viewed twice
- Given a chapter with a fixed 成稿状态 (无正文 / 有正文未归档 / 导入未归档 / 已归档)
- When the preview view lists that chapter
- Then the 目录行 shows the matching `.pill` status label (拟定 / 草稿 / 原文 / 已归档) derived from the same chapter data, with the word count in mono/tabular style — never a three-state dot

#### Scenario: 导入章使用同一状态家族
- Given a chapter imported from the author's own manuscript (`origin=import`, not archived)
- When the preview or chapter tree lists that chapter
- Then it uses the existing `.pill` status family with the label 「原文」, not a new capsule shape, solid fill, or red treatment

#### Scenario: S端 console uses unified badge and notice vocabulary
- Given any S端 console, auth or landing screen needs a badge or a callout bar
- When the page renders
- Then badges use `.pill` role × tone classes and callout bars use `.notice` with an explicit tone, and no `.b` or `.strip` class remains in S端 source or rendered DOM

#### Scenario: 页签待确认泡泡用既有词汇组合
- Given the chapter workbench needs a pending-confirmation count on a tab
- When the bubble is rendered
- Then it composes existing `.pill` count role with an existing tone (accent for 待确认 / warn for 台账节奏), shows a number with a title attribute, and disappears at zero — no solid fill, no red, no fourth capsule form

## ADDED Requirements

### Requirement: 导入向导与原文状态词汇

- 导入向导 SHALL 复用既有弹窗壳、`.notice`（格式/风险/配额）、`.field`/`.textarea`（卷名/书名）、`.btn`（主次动作）、`.pill`（原文/任务状态/来源）、列表行与 chevron 折叠词汇；SHALL NOT 新增胶囊形态、实底填充、emoji 图形或未登记字号。
- 用户可见词 SHALL 冻结为：「导入」「导入我的书」「直接导入（只带正文）」「AI 拆书」「开书」「原文」「每章摘要」「补齐本章」「10 项拆书产物」「手动拆书」「回到上次写作」「写下一章」「已完成·待开书」「已开书」「导入 / 拆书」；`imported/frontier/baseline/pipeline/dossier` 等内部词 SHALL NOT 上屏。
- 新增词 SHALL 在 `docs/ux/design-language.html` §5/§6/§13 与 C端 `client/frontend/scripts/design-vocab.mjs` 登记；若词汇被 S端 复用，再双端同批。
- 第 2 步切分编辑器 SHALL 用列表行＋chevron 折叠表达卷/章；只提供「分卷/少一章/多一章/合并/改名/不导入此章」，SHALL NOT 出现拖拽单章跨卷、复选框任意归卷等暗示非法结构的控件。
- 格式风险、书名/卷名校验与配额阻断 SHALL 使用 info/warn/err 三种既有 notice 语气；不可逆动作（不导入章节、删除本书重新导入）SHALL 走应用内确认并列出影响范围。
- 原型 SHALL 先落到 `docs/design-c/prototypes/` 并在 `ADJUSTMENTS.md` 登记偏差，再改实现。

#### Scenario: 新增标签只用既有词汇
- **WHEN** 原文章目录行、导入任务行、开书完成态渲染
- **THEN** 它们分别使用既有 `.pill` 的 tag/status/count 组合，标签为「原文」「导入」「已完成·待开书」「已开书」，没有新胶囊形态或实底红

#### Scenario: 切分编辑器不提供非法动作
- **WHEN** 作者在第 2 步调整卷边界
- **THEN** 只能看到「分卷/少一章/多一章/合并/改名/不导入此章」，看不到拖拽单章或复选框任意归卷

#### Scenario: 阻断与风险走既有 notice
- **WHEN** 书架已满或格式风险出现
- **THEN** 分别以 warn/err 的 `.notice` 呈现并提供动作出口；不使用 toast 代替阻断说明

#### Scenario: 原型与门禁先行
- **WHEN** 导入向导进入实现
- **THEN** `docs/design-c/prototypes/` 下的对应屏与 `ADJUSTMENTS.md` 已更新，`npm run design:lint` 与 `npm run design:check` 有通过记录；否则实现不合并
