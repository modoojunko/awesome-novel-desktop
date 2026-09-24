## 1. 双端影响判定

- [x] 1.1 双端影响判定：本 change 只统一失败语义与跳转口径，无静态视觉增量、不触共享段——无需原型先行；判定依据登记在 change 目录（对照 openspec/config.yaml tasks 规则）

## 2. 认证失效统一出口

- [x] 2.1 导出 `handleAuthExpiry()`（清凭据 + 写 `sessionStorage.last_auth_kick_at` + 导航回登录页 + 至多一次防循环），主栈 401 分支改为调用它（行为等价重构）——diff 贴进 change 目录
- [x] 2.2 `lib/api.ts` importParse 的 401 分支改调统一出口（补熔断时间戳）——diff 贴进 change 目录
- [x] 2.3 单测：统一出口被调用时写时间戳、清凭据、导航；重复调用不产生第二次导航——vitest 绿

## 3. /api/v1 手写族迁回中心栈

- [x] 3.1 `request()` 加 `apiBase` 选项（默认空）——diff 贴进 change 目录
- [x] 3.2 `useApiConfigs.ts`（9 处）、`useModelStatus.ts`（3 处）、`useChangeHistory.ts`（2 处）、`useUsageStats.ts`（1 处）、`ApiKeyConfigPage.tsx`（1 处，含补 `r.ok` 检查）、`useDeviceActivation.ts`（2 处）全部改走 `request()`，删除各自的 `API_BASE` 常量与 `authHeaders()` 副本——`grep -rn "fetch(" client/frontend/src/hooks client/frontend/src/pages` 零命中（`lib/api.ts`/`lib/ai.ts` 除外）
- [x] 3.3 迁移调用点补返回类型（`request<T>`）——`tsc --noEmit` 绿

## 4. AI 路径接入统一出口

- [x] 4.1 `lib/ai.ts` doJsonPost 改调 `request()`（删除复制的 member_required/5xx 文案）——diff 贴进 change 目录
- [x] 4.2 SSE 路径补 401 分支调用统一出口（保留独立流式实现）——diff 贴进 change 目录
- [x] 4.3 单测：AI 非流式 401 → 回登录页；SSE 401 → 统一出口——vitest 绿

## 5. 探测类失败显式化

- [x] 5.1 `useModelStatus` 候选/就绪探测失败呈现失败态（不再静默停留旧值）——diff + 截图路径贴进 change 目录
- [x] 5.2 `useDeviceActivation`/`AcctMenu`/`lib/portal` 的探测失败保持静默降级但不再吞异常类型（可诊断）——diff 贴进 change 目录

## 6. 回归

- [x] 6.1 `npm run design:lint`、`npm run design:check`（C端）输出结论贴进 change 目录
- [x] 6.2 `tsc --noEmit`（C端）输出结论贴进 change 目录
- [x] 6.3 `npx vitest run`（全量）输出结论贴进 change 目录
- [x] 6.4 定向 e2e（会话过期踢出、配置页失败态、AI 请求 401）在隔离 docker 栈通过——结论与截图路径贴进 change 目录
