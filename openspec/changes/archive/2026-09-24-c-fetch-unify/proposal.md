## Why

C端 前端的 HTTP 请求面至今是三分格局：主栈 `lib/api.ts` 的 `request()`（51 个文件引用，语义最全：401 清凭据踢出、503 结构化提示、403 member_required 广播）、`lib/ai.ts` 的手写 POST/SSE、以及 `/api/v1` 手写 fetch 族（7 文件 19 处，各自复制 `authHeaders()` 五份、错误降级为 `HTTP <status>`）。

后果是同一件事在不同路径上表现不同：token 过期后，走主栈的请求会回登录页，而设置页的 API Key 列表只显示「HTTP 401」、模型就绪态静默停在旧值；`importParse` 的 401 踢出不写登录页的反弹熔断时间戳，恰好绕过防循环机制；AI 润色全族在会话过期时报一条文案后原地停留。

## What Changes

- `lib/api.ts` 提供 `API_BASE` 前缀能力，`/api/v1` 手写族 7 文件 19 处迁回 `request()`，五份 `authHeaders()` 副本删除。
- 认证失效收敛为**统一出口**（清凭据 + 写反弹熔断时间戳 + 导航）：主栈、导入解析、AI 请求、配置域全部经它，不再各自实现。
- `lib/ai.ts`：非流式 `doJsonPost` 改调 `request()`；SSE 路径保留独立实现但补 401 分支调用统一出口。
- 探测类请求（设备激活、模型候选、迁移状态、portal）失败语义对齐中心栈的静默降级口径，不再各自 `return null` 到无人知晓。
- `request()` 补泛型签名（渐进收口，默认 `any` 不破坏既有调用）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend-auth-heal`: 新增「认证失效处理必须经统一出口」要求（任意用户动作请求路径的 401 行为一致，含熔断时间戳写入）。
- `model-api-config`: 新增「配置域请求失败语义统一」要求（401 回登录页、服务不可用给统一提示，不暴露原始状态码）。

## Design Impact

- **受影响端**：C端（不触 S端）。
- **受影响的屏/弹层**：AI 配置页（API Key 列表/添加弹窗）、模型就绪态展示位、用量与切换历史区、登录页（踢出落点）、导入解析入口。
- **用到或新增的对象状态**：err 语气提示与跳转（会话失效回登录页、服务不可用提示）——均为既有词汇与既有跳转语义，**无新增视觉形态**。
- **是否触碰两端共享段**：否。
- **是否需要原型先行**：不需要——本 change 只统一运行时的失败语义与跳转口径，不改任何屏的静态视觉；判定依据登记在 change 目录。
- **设计工件产出**：不涉及（无视觉增量）。

## Impact

- 前端：`lib/api.ts`、`lib/ai.ts`、`hooks/useApiConfigs.ts`、`hooks/useModelStatus.ts`、`hooks/useChangeHistory.ts`、`hooks/useUsageStats.ts`、`hooks/useDeviceActivation.ts`、`pages/ApiKeyConfigPage.tsx`、`lib/portal.ts`、`AcctMenu.tsx`（探测项）。
- 测试：相关 vitest 单测与 e2e（会话过期踢出、配置页失败态）更新。
- 无后端接口变更。
