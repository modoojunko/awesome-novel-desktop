# project-shell 变更（Delta）

## MODIFIED Requirements

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
