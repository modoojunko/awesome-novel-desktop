# project-shell Specification

## Purpose

书工作台路由壳：`/novel/:id` 进入后按 id 拉一次作品详情，经 Context 下发给工作台与书栏；
加载中给骨架、失败不崩、作品已删除或不存在时回书架并说明，保证工作台只消费有效作品的上下文。

## Requirements

### Requirement: NovelLayout mounts tier context and project shell

- 权益上下文 SHALL 上移至应用 shell 层：应用在认证后的路由根部渲染 `AuthGuard → LicenseProvider → routes`，使书列表（/novels）与工作台（/novel/:id）**全部认证后路由**的 descendants 都能读取 license tier/entitlement 上下文——权益异常提示条（书列表）与路由切换刷新触发（书列表↔工作台）依赖此挂载点。
- `pages/NovelLayout.tsx` SHALL 渲染 `ProjectShell → Outlet`（不再自带 LicenseProvider），保证 `/novel/:id` descendants 同时持有 project 上下文。
- AuthGuard SHALL remain the outermost gate (redirects to `/login` when unauthenticated).

#### Scenario: Novel route descendants have context

- Given a logged-in user navigating to `/novel/:id`
- When the NovelLayout renders
- Then descendants can read the license tier and the project from context

#### Scenario: Book list route has license context

- Given a logged-in user navigating to `/novels`
- When the book list page renders
- Then it can read the license tier/entitlement context（含 entitlementDegraded）and the route change into/out of it triggers the debounced silent refresh

### Requirement: useProject hook

- The system SHALL provide a `useProject()` hook backed by a `ProjectShell` context.
- The `ProjectShell` SHALL call `GET /novels/{id}` once on route id change and expose `{ project, loading, error }` via context.
- While fetching, `loading` SHALL be true (consumers — e.g. NovelPage — render the existing skeleton).
- On failure, `project` SHALL be null and `error` set (no crash).
- On `404` (作品已删除或不存在), the shell SHALL toast「作品不存在或已删除」and replace-navigate to the shelf `/`; other failures SHALL keep the current route with `error` set (no redirect).
- The hook SHALL return safe defaults `{ project: null, loading: false, error: null }` when called outside the `ProjectShell` provider.

#### Scenario: Descendant reads project
- Given a mounted ProjectShell for a valid novel id
- When a descendant calls `useProject()`
- Then it receives the fetched `project` object

#### Scenario: Loading flag while fetching
- Given a ProjectShell that has not yet resolved the project
- When a descendant reads `useProject()`
- Then `loading` is true

#### Scenario: Fetch failure degrades gracefully
- Given `GET /novels/{id}` rejects
- When the shell finishes loading
- Then `project` is null, `error` is set, and no exception escapes

#### Scenario: Deleted or missing novel returns to shelf
- Given `GET /novels/{id}` rejects with status 404 (作品已删除或不存在)
- When the shell handles the failure
- Then it toasts「作品不存在或已删除」and replace-navigates to `/`; the workbench SHALL NOT render that novel's content

