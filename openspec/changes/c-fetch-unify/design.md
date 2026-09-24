## Context

见 proposal.md 的 Why。落地相关现状（实勘）：

- 中心栈：`lib/api.ts:72` `request(path, options)`，`RequestOptions` 只有 method/body/headers/quiet/soft503（`:35-43`），无 base 前缀能力；401 踢出在 `:99-114`（含写 `sessionStorage.last_auth_kick_at`，`:108`）、503 结构化解析 `:116-146`、403 member_required 广播 `:152-163`。
- 手写族：`useApiConfigs.ts`（9 处 fetch + 自建 `authHeaders`）、`useModelStatus.ts`（3 处）、`useChangeHistory.ts`（2 处）、`useUsageStats.ts`（1 处）、`pages/ApiKeyConfigPage.tsx:52-59`（不查 `r.ok`）、`useDeviceActivation.ts`（2 处）；`const API_BASE = "/api/v1"` 在多文件重复。
- AI：`lib/ai.ts:156-197` doJsonPost（复制了 member_required 广播与 5xx 文案，无 401 分支）、`:73-150` doStreamFetch（SSE）。
- `lib/api.ts:271-275` importParse 的 401 只清 token + 跳转，未写熔断时间戳。
- C端 后端 `/api/v1` 前缀是同进程另一 router，base 前缀能力可直接支持。

## Goals / Non-Goals

**Goals:**

- 一个请求出口、一套失败语义：401/403/503/网络错误在全部路径上同行为。
- 消灭 5 份 `authHeaders()` 与 7 处 `API_BASE` 常量副本。

**Non-Goals:**

- 不合并 SSE 流式实现（`doStreamFetch` 语义特殊，保留独立，只接统一出口的 401）。
- 不引入查询层/缓存（属 `c-query-cache-layer`）。
- 不做 `request<T>` 的全量类型收口（本次只加泛型签名，迁移调用点标类型）。

## Decisions

**D1：`request()` 加 `apiBase` 选项（默认空），不新建第二套封装。**
`/api/v1` 族迁回中心栈时传 `apiBase: "/api/v1"`；备选（已弃）为 `/api/v1` 单独封装——那正是本次要消灭的漂移源。

**D2：认证失效统一出口 = `handleAuthExpiry()`（导出函数）。**
职责：清凭据（config.json + localStorage 口径沿现状）、写 `sessionStorage.last_auth_kick_at`、导航回登录页，并保持至多一次踢出的防循环语义。主栈 401 分支、importParse、AI 非流式、SSE 401 分支全部调用它；SHALL NOT 各自实现。

**D3：`doJsonPost` 非流式路径改调 `request()`；SSE 保留独立实现。**
doJsonPost 复制出来的 member_required/5xx 文案删除，随 `request()` 走；SSE 因流式读取无法复用请求体，仅在 401 时调统一出口。

**D4：探测类静默降级口径保留，但显式化。**
quiet 探测仍不踢出、不弹全局错误（既有规格），但各自「失败→空值」的落点要能区分「空」与「失败」（模型候选、设备激活、迁移状态、portal），按各屏已有状态位呈现；无状态位的最小改动是保持静默但不再吞异常类型（日志/埋点可查）。

**D5：`request<T>` 泛型渐进收口。**
签名加 `request<T = any>`，本次迁移的 19 处调用点标注返回类型；全量收口不在本次范围。

## Risks / Trade-offs

- [迁移 19 处可能改变既有静默降级行为（如 503 soft503 语义）] → 逐文件对照原实现保留其降级口径，e2e 回归覆盖设置页与 AI 配置页。
- [统一出口引入循环踢出风险] → 沿用既有防循环（至多一次 + 熔断时间戳），e2e 有失效后不循环用例。
- [SSE 与主栈两套超时/重试口径] → 本次不动 SSE 超时（独立口径已在 ai-client 规格约束），只补 401。

## Migration Plan

1. 先落统一出口函数（行为等价于主栈现状）→ 迁 `/api/v1` 族 → 接 AI 与 importParse → 删副本常量。
2. 无数据迁移；回滚 = revert 提交。
