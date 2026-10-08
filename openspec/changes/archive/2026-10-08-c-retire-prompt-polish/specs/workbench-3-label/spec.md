## MODIFIED Requirements

### Requirement: 章节点点击 → 中部子 label 切换 正文 / 章纲 / 提示词

- Selecting a chapter node SHALL render a sub-label bar in the main area: 正文 / 章纲 / 提示词.
- 正文 SHALL render the existing `ChapterEditor` + `RightToolbar`; `ChapterEditor`'s internal 正文/提示词 view tabs SHALL be removed.
- 章纲 SHALL render `OutlineEditor` fed by `useOutline` (chapter data loaded on demand via `loadChapterData`), including the prompt-crafting fields (读者获得、章末落点——c-og-slim-v2 后场景卡与其权重/焦点退役).
- 提示词 SHALL render the chapter's single whole-chapter prompt view: 当前整章提示词内容（查看/编辑保存）；分段提示词文件列表 SHALL NOT 渲染。**「AI 润色」入口与润色状态说明随 c-retire-prompt-polish 退役**（提示词只由确定性组装＋作家编辑/存稿产生）。
- With no chapter selected, the sub-label bar SHALL NOT render.

#### Scenario: Selecting a chapter shows sub-labels

- Given a novel with a chapter
- When the user clicks the chapter node
- Then the sub-label bar renders 正文 / 章纲 / 提示词 (提示词 PRO-only)
- And the default sub-label is 正文 (prose editor)

#### Scenario: 提示词子 label 呈现整章提示词

- **WHEN** PRO 用户打开某章的「提示词」子 label
- **THEN** 呈现该章唯一整章提示词的查看/编辑视图（不再有「AI 润色」入口，c-retire-prompt-polish）
- **AND** 不呈现分段提示词列表或分段生成按钮
