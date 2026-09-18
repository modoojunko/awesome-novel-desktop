# topbar-nav-merge Specification

## Purpose
TBD - created by archiving change 012-topbar-nav-merge. Update Purpose after archive.

## Requirements

### Requirement: 3 label 导航并入顶栏（单行）

- The novel top bar SHALL be a single row containing: book title (inline-rename + type badge) on the left, followed by the three navigation labels 编辑设定 / 编辑正文 / 预览, and the tier badge + delete on the far right.
- The book title SHALL shrink and truncate (`flex-1 min-w-0`, ≤30vw) to make room; the three labels SHALL never truncate and remain clickable at any window width.
- The `WorkspaceView` navigation state SHALL flow from `NovelWorkspace` into `NovelBar` via `view` and `onNavigate` props.
- The former standalone 3-label navigation row in `NovelWorkspace` SHALL be removed.

#### Scenario: Top bar is a single merged row
- Given a free or PRO session viewing a novel
- Then the top bar renders 书名 + 编辑设定 + 编辑正文 + 预览 + tier badge + delete in one row
- And no second navigation row exists below it

### Requirement: TabProgressButton 纯导航样式（active 中性药丸 / inactive 可点）

- For pure-navigation `TabProgressButton` (no `status`), the active state SHALL use a neutral pill (`bg-base-300 text-base-content font-medium`) and the inactive state SHALL use `text-base-content/60` with hover feedback (`hover:text-base-content hover:bg-base-300/40`).

#### Scenario: Active label reads as current view, not promo
- Given a novel in workbench view
- Then the 编辑正文 label renders as the active neutral pill
- And the primary color is reserved for the PRO badge / primary CTAs

### Requirement: Workbench 上下文行合并（面包屑 + 章子 label + 专注）

- The breadcrumb row in the workbench SHALL also hold the chapter sub-labels (正文 / 章纲 / 提示词, 提示词 PRO-only) and the focus toggle when a chapter is selected.
- The standalone chapter sub-label row SHALL be removed.

#### Scenario: Selecting a chapter shows one context row
- Given a chapter selected in the workbench
- Then a single context row renders: breadcrumb + 正文/章纲/提示词 sub-labels + 专注 toggle
- And no second sub-label row is present

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
