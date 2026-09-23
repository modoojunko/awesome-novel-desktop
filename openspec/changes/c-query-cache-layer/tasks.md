## 1. 双端影响判定

- [x] 1.1 双端影响判定：纯 C端 前端实现层换轨，无静态视觉改动、不触共享段；行为契约由既有 capability 场景＋e2e 预算守卫钉住——skip_specs: true，无需原型先行
- [x] 1.2 盘点手工失效面：事件广播点 / registerRefetch 注册点 / 手写缓存三处——清单贴进 change 目录

## 2. 基建

- [x] 2.1 引入 `@tanstack/react-query`，QueryClientProvider 挂应用壳（恒挂载口径对齐 c-session-flip-stability）——diff 贴进 change 目录
- [x] 2.2 新增 `lib/queryKeys.ts`：key 工厂＋失效映射表单源——diff 贴进 change 目录

## 3. 试点域：书架 novels

- [x] 3.1 NovelListPage 数据获取迁 useQuery；写操作（建/删/归档/完本）改 invalidateQueries——diff 贴进 change 目录
- [x] 3.2 `novels:changed` 事件双轨并存→试点绿后撤除——vitest＋定向 e2e 绿后记录撤除 diff
- [x] 3.3 预算守卫验证：书架空闲期 ≤8 请求/3 秒 e2e 用例绿——结论贴进 change 目录

## 4. 分域推进

- [ ] 4.1 工作台卷/章树：useOutline.refresh / useWorkbench.refresh 迁失效语义——diff 与测试结论贴进 change 目录
- [ ] 4.2 用量/版本/portal 缓存并入（staleTime 对齐既有节流：60s/5min）——diff 贴进 change 目录

## 5. 退役与收口

- [ ] 5.1 撤 `registerRefetch` 注册表与残留事件广播（确认零消费方后删）——codegraph callers 截图/diff 贴进 change 目录
- [ ] 5.2 `lib/version.ts`、`lib/portal.ts` 手写缓存删除——diff 贴进 change 目录

## 6. 回归

- [ ] 6.1 `npm run design:lint`、`npm run design:check`（C端）输出结论贴进 change 目录
- [ ] 6.2 `tsc --noEmit`（C端）与 `npx vitest run`（全量）输出结论贴进 change 目录
- [ ] 6.3 全量 e2e（隔离 docker 栈）通过，重点：书架/工作台/预览/预算守卫——结论与截图路径贴进 change 目录
