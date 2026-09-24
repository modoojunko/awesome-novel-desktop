## Why

C端 前端的跨视图数据一致性目前靠三件手工机制拼装：window 自定义事件广播（`novels:changed` 等）、`registerRefetch` 注册表（`NovelWorkspace.tsx:1324-1338`）、各自手写的模块级去重缓存（`lib/version.ts`、`lib/portal.ts`）。每个「写操作后哪些视图要刷新」的决策都靠开发者记得广播/注册，漏一处即「改了 A 视图 B 视图旧数据」——本轮复审再度确认：新代码继续在注册表上加注册，欠账持续累积。

引入查询缓存层（React Query）：以「写操作 → 按 key 失效」的单源机制替代手工广播/注册，跨视图一致性由框架承载。

## What Changes

- 引入 `@tanstack/react-query`：QueryClientProvider 挂应用壳，数据获取逐步迁 `useQuery`，写操作以 `invalidateQueries` 失效相关 key。
- 迁移顺序（分域灰度）：① 书架 novels 域（试点）→ ② 工作台卷/章树（useOutline/useWorkbench 的 refresh）→ ③ 用量/版本/portal 等零散缓存。
- 退役路径：试点稳定后撤 `registerRefetch` 注册表与 `novels:changed` 类事件广播；`lib/version.ts`、`lib/portal.ts` 的手写缓存并入查询缓存。
- 查询 key 规范：`[域, 资源id, 参数]` 三段；失效映射表单源（每个写操作声明其失效 key 集合）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——本 change 为实现层换轨：跨视图一致性与刷新语义的**行为契约**已由既有各 capability 场景钉住（书架刷新/工作台树同步/用量面板等），本 change 不改变任何对外可观察行为，故 `skip_specs: true`，以全量 vitest＋e2e 作门禁。）

## Design Impact

- 不适用：无静态视觉改动，不触共享段；请求时序变化由既有 e2e 的请求预算守卫（书架空闲期 ≤8 请求/3 秒）兜底。

## Impact

- `client/frontend/src`：shell（Provider）、NovelListPage、useOutline、useWorkbench、useUsageStats、lib/version.ts、lib/portal.ts 等。
- 依赖：新增 `@tanstack/react-query`。
- 门禁：全量 vitest＋全量 e2e（含请求预算守卫）。
