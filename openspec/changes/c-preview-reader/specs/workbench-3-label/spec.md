## MODIFIED Requirements

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
