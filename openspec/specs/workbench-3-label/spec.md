# workbench-3-label Specification

## Purpose
TBD - created by archiving change 011-workbench-3-label. Update Purpose after archive.

## Requirements

### Requirement: 工作台 3 label 导航（两态共用，纯导航无徽标）

- The system SHALL render exactly three navigation labels on the novel workbench, shared by both free and PRO tiers: 编辑设定 / 编辑正文 / 预览.
- The labels SHALL be pure navigation with no phase-status badge (`status` undefined on `TabProgressButton`).
- 编辑设定 SHALL open the settings view (`advanced-settings`); 编辑正文 SHALL open the prose workbench (`workbench`); 预览 SHALL open the reading preview (`archives` view id, `preview-reader` 语义).
- 预览 SHALL present the reading preview with in-view reading configuration (字号/字体/行距/主题) and the whole-book catalog; it SHALL remain a read-only view.
- The `WorkspaceView` union SHALL be reduced from four to three values (removing `advanced-outline`).
- The top-bar NovelBar「高级配置 ▾」dropdown SHALL be removed entirely (both tiers), and the EmptyState「高级配置」button SHALL be removed.

#### Scenario: Both tiers render the 3 labels
- Given a free session viewing a novel
- And a PRO session viewing a novel
- Then both render the labels 编辑设定 / 编辑正文 / 预览
- And neither renders a top-bar「高级配置」dropdown

#### Scenario: 预览打开阅读器
- Given a novel with chapters
- When the user opens 预览
- Then the reading preview renders with the catalog column, the reading column, and the reading-configuration column

### Requirement: 卷节点点击打开中栏卷视图（卷 · 分卷计划）

- Clicking a volume node in the left tree SHALL open that volume's 卷视图 in the 中栏（头部＋「卷纲｜本卷章节｜角色关系｜伏笔」四页签；行为细节见 volume-outline 能力）；右侧抽屉形态（backdrop/400px 面板/Escape 关闭）与 `VolumeEditor` 复用口径 SHALL 退役。
- Selecting a chapter from within the 卷视图（「本卷章节」页签点行）SHALL switch the 中栏 to that chapter's workspace and sync the left-tree selection.
- Creating a volume (`创建第一卷` / tree「新建卷」) SHALL select the new volume and open its 卷视图 in the 中栏（离开后对同一选中不重复自动打开）。

#### Scenario: Click volume opens middle-column volume view
- Given a novel with a volume and a chapter
- When the user clicks the volume node in the tree
- Then the 中栏 renders the volume view with the four tabs and no right-side drawer appears

#### Scenario: 卷视图内进入章节
- Given 卷视图「本卷章节」页签可见
- When 点击其中一章
- Then 中栏切换为该章工作台，左树选中同步到该章

### Requirement: 章节点点击 → 中部子 label 切换 正文 / 章纲 / 提示词

- Selecting a chapter node SHALL render a sub-label bar in the main area: 正文 / 章纲 / 提示词.
- 正文 SHALL render the existing `ChapterEditor` + `RightToolbar`; `ChapterEditor`'s internal 正文/提示词 view tabs SHALL be removed.
- 章纲 SHALL render `OutlineEditor` fed by `useOutline` (chapter data loaded on demand via `loadChapterData`), including the prompt-crafting fields (场景卡权重/焦点、读者获得、章末落点).
- 提示词 SHALL render the chapter's single whole-chapter prompt view: 当前整章提示词内容（查看/编辑保存）、「AI 润色」入口、润色状态说明；分段提示词文件列表 SHALL NOT 渲染.
- With no chapter selected, the sub-label bar SHALL NOT render.

#### Scenario: Selecting a chapter shows sub-labels

- Given a novel with a chapter
- When the user clicks the chapter node
- Then the sub-label bar renders 正文 / 章纲 / 提示词 (提示词 PRO-only)
- And the default sub-label is 正文 (prose editor)

#### Scenario: 提示词子 label 呈现整章提示词

- **WHEN** PRO 用户打开某章的「提示词」子 label
- **THEN** 呈现该章唯一整章提示词的查看/编辑视图与「AI 润色」入口
- **AND** 不呈现分段提示词列表或分段生成按钮

### Requirement: 提示词子 label PRO-only

- The 提示词 sub-label button and its content SHALL be gated by `TierGate feature="prompt-panel"` (PRO-only).
- In free tier, the 提示词 sub-label SHALL be hidden; the sub-label bar SHALL show only 正文 / 章纲.
- The prompt view SHALL be scoped to the currently selected chapter (`chapterRef`), loading and saving that chapter's whole-chapter prompt only.

#### Scenario: Free hides the prompt sub-label

- Given a free session with a chapter selected
- Then the sub-label bar renders 正文 and 章纲
- And no 提示词 sub-label is rendered

#### Scenario: PRO shows the prompt sub-label filtered by chapter

- Given a PRO session with a chapter selected
- When the user opens 提示词
- Then the view shows only the selected chapter's whole-chapter prompt, with an AI-polish entry and editable content
