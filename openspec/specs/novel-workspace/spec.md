# novel-workspace Specification

## Purpose
TBD - created by archiving change 004-free-workspace. Update Purpose after archive.

## Requirements

### Requirement: Four-state workspace view machine

- The system SHALL provide `components/novel/NovelWorkspace.tsx` as the single workspace replacing `pages/NovelPage.tsx`.
- The workspace SHALL expose exactly four views: `workbench | advanced-settings | advanced-outline | archives`.
- **The default landing view SHALL be derived from the book's stage, not fixed to `workbench`**（2026-09-10 用户拍板，取代原「writing is always the primary surface / C5 / P0-5」口径）：
  - 阶段判据 SHALL 只看**章节**（`stageFromChapters(totalChapters, archivedChapters)`，单源 `lib/novelStage.ts`），**SHALL NOT** 用 `current_phase`——phase 只是「最近一次操作」的记账，归档过一章即停在 `archive`，不代表整本写完。
  - **无章节 → `advanced-settings`（设定）**；**全部章节已归档 → `archives`（预览）**；**其余（有章节未全归档）→ `workbench`（写作）**。
  - 落点 SHALL 只在**首次书树加载后应用一次**；用户/深链已显式选择视图时 SHALL NOT 覆盖（`setView` 标记主动导航；自动聚焦第一章不算主动导航）。
  - **书架列表的阶段标签与判据 SHALL 复用同一单源**（`stageFromChapters` + `STAGE_LABEL`，均取自 `lib/novelStage.ts`）——**SHALL NOT** 再按 `current_phase` 派生（2026-09-10 用户拍板「卡片状态应该落在写作」）。卡片与落点必须同结论：归档过几章但整本未完＝卡片「写作中」、点开落写作，不出现「卡片已归档 / 落点写作」的自相矛盾。
  - 卡片判据依赖的 `total_archives` SHALL 语义为**已归档章节数**：归档 SHALL 幂等（重复归档同一章不重复计数）、取消归档 SHALL 对称回减且不为负。
- The `workbench` view SHALL remain mounted at all times; switching to another view SHALL hide it via a `hidden` class (display:none) rather than unmounting, so un-saved prose input and cursor position within the 1.5s autosave debounce window are preserved.
- The `advanced-settings`, `advanced-outline`, and `archives` views SHALL lazy-mount on first visit and unmount when leaving (FE P1-1); they SHALL NOT stay mounted hidden after leaving.
- The workspace SHALL provide `setView(view, payload)` that accepts an optional navigation payload (e.g. which chapter to focus) for descendants.
- `DeleteConfirmModal` SHALL remain at the NovelWorkspace layer (available from any view).

#### Scenario: Default landing is workbench
- Given a mounted NovelWorkspace for a project **whose chapters are not all archived**（有章节未全归档）
- When the workspace initializes
- Then the active view is `workbench` and the writing workbench is visible

#### Scenario: 空书默认落设定（建书后先写简介与题材）
- Given 一本刚创建、尚无任何章节的书
- When 从书架点开这本书
- Then 默认落在「设定」视图（简介面板）
- And SHALL NOT 叠加「开始设定」引导卡（卡片唯一作用是把人送到设定，此时已在设定）

#### Scenario: 有章节未全归档默认落写作
- Given 该书已建卷建章、且并非全部章节已归档
- When 打开这本书
- Then 默认落在「写作」视图

#### Scenario: 全部章节已归档默认落预览
- Given 该书全部章节均已归档（写完）
- When 打开这本书
- Then 默认落在「预览」视图

#### Scenario: 卡片阶段与落点同结论
- Given 该书已建卷建章、其中部分章节已归档但并非全部
- When 查看书架卡片
- Then 卡片阶段标签为「写作中」（SHALL NOT 因 `current_phase=archive` 显示「已归档」）
- And 点开这本书默认落「写作」视图，与卡片标签一致

#### Scenario: 用户显式切视图不被落点覆盖
- Given 已打开一本书且落点已生效
- When 用户手动切到另一视图（或由深链携带视图载荷进入）
- Then 视图保持用户所选，SHALL NOT 被默认落点拽回

#### Scenario: Workbench stays mounted while switching views
- Given the workbench has unsaved prose input within the debounce window
- When the user switches to advanced-settings and back to workbench
- Then the prose input value and cursor are preserved (the workbench was hidden, not unmounted)

#### Scenario: Advanced views lazy-mount and unmount on leave
- Given a workspace where advanced-settings was never visited
- When the user first switches to advanced-settings
- Then the view mounts; after switching back to workbench, the advanced-settings tree unmounts

### Requirement: PRO container (N14)

- The system SHALL provide `components/novel/ProContainer.tsx` that renders its children only when the user is on a paid tier.
- `ProContainer` SHALL use `useTier().isFree` to decide; when free, it SHALL render `null` and NOT render the subtree.
- The phase-driven UI — `OnboardingCard` and the `useNovelState` phase-status hook — SHALL be placed inside a ProContainer subtree so that free users render none of them and issue no phase-status request.
- The `GateBanner` phase-warning banner SHALL NOT be rendered anywhere in the novel workspace for any tier.
- The three navigation labels (编辑设定 / 编辑正文 / 预览小说) SHALL render for both tiers outside the ProContainer subtree.
- Hooks inside the ProContainer subtree SHALL NOT be called at the top level of NovelWorkspace (no conditional hook calls); they live inside a child component that only mounts for paid users.

#### Scenario: Free tier renders no phase UI
- Given a free-tier user viewing the workspace
- When the workspace renders
- Then no OnboardingCard or `GET .../workflow/phase-status` request is issued

#### Scenario: Paid tier renders phase UI
- Given a paid-tier user viewing the workspace
- When the workspace renders
- Then the OnboardingCard phase surface is present and a `GET .../workflow/phase-status` request is issued

#### Scenario: No gate banner on any tier
- Given a paid-tier user viewing the workspace with unconfirmed settings
- When the workspace renders
- Then no「以下阶段尚未就绪」gate banner is present in the DOM

### Requirement: Route convergence to single index

- The system SHALL collapse `/novel/:id` to a single index route rendering `NovelWorkspace`.
- The dead child routes `settings`, `settings/world`, `settings/style`, `settings/anti-ai`, `settings/hooks`, `outline`, `prompts`, `write`, `archives`, `threads` SHALL be removed from `App.tsx` (no more `Navigate to=".."` dead links).
- The redirect routes `/books → /novels` and `/project/:id → /novel/:id` SHALL remain unchanged.
- Unknown routes (`path="*"`) SHALL redirect to `/novels` with `replace`, so stale or mistyped deep links never render a blank page.
- The `/` route SHALL render a static welcome page for signed-out users, reachable without authentication; signed-in users opening `/` SHALL be redirected to `/novels` with `replace`. The welcome page SHALL be an entry card (sign-in / create account) and SHALL NOT contain marketing sections.

#### Scenario: Deep link reaches the workspace
- Given a URL `/novel/:id`
- When it is loaded
- Then `NovelWorkspace` renders as the index child of `NovelLayout`

#### Scenario: Old subroutes no longer resolve as dead links
- Given a URL such as `/novel/:id/settings`
- When it is loaded
- Then it does not render a `Navigate` dead-link component; it resolves to the workspace (or a 404) without a stale child redirect

#### Scenario: Unknown route lands on the bookshelf
- Given a URL that matches no route
- When it is loaded
- Then the app redirects to `/novels` and renders the bookshelf instead of a blank page

#### Scenario: Signed-out user sees the static welcome page
- Given no auth token is stored
- When `/` is loaded
- Then the static welcome page renders with sign-in entry points and no auth redirect

#### Scenario: Signed-in user skips the welcome page
- Given a valid auth token is stored
- When `/` is loaded
- Then the app redirects to `/novels` with `replace`
