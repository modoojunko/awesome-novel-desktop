## MODIFIED Requirements

### Requirement: 3 label 导航并入顶栏（单行）

- The novel top bar SHALL be a single row containing: book title (inline-rename + type badge) on the left, followed by the three navigation labels 编辑设定 / 编辑正文 / 预览, and the tier badge + delete on the far right.
- The book title SHALL shrink and truncate (`flex-1 min-w-0`, ≤30vw) to make room; the three labels SHALL never truncate and remain clickable at any window width.
- The `WorkspaceView` navigation state SHALL flow from `NovelWorkspace` into `NovelBar` via `view` and `onNavigate` props.
- The former standalone 3-label navigation row in `NovelWorkspace` SHALL be removed.

#### Scenario: Top bar is a single merged row
- Given a free or PRO session viewing a novel
- Then the top bar renders 书名 + 编辑设定 + 编辑正文 + 预览 + tier badge + delete in one row
- And no second navigation row exists below it

### Requirement: 设定 / 归档 视图头部行移除

- The `AdvancedSettingsView` header row（「设定」标题 + 「返回正文」按钮）SHALL be removed; returning to the workbench SHALL use the top-bar 编辑正文 label.
- The legacy `ArchivePage` browser（归档 (N章) 内容标题 + 搜索栏 + 返回项目头部行）SHALL be retired entirely——归档浏览器已随「预览=全书只读通读」语义退役（ADJUSTMENTS #12），预览视图的呈现由 `preview-reader` 能力（三栏阅读器）定义，SHALL NOT 复活搜索栏或归档计数标题。
- Content-level navigation in the preview（空书去写作视图建卷建章的出口）SHALL be preserved by `preview-reader`。

#### Scenario: Settings view has no redundant header
- Given the user clicks 编辑设定 in the top bar
- Then the settings tree + form render directly below the top bar
- And no「设定 / 返回正文」header row is present

#### Scenario: Archive view shows count as content title
- Given the user clicks 预览 in the top bar
- Then the preview renders the three-column reading view defined by `preview-reader`
- And no「归档 (N章)」content title, search bar, or「返回项目」header row is present
