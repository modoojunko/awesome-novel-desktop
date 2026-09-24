## Context

见 proposal.md。现状三件套（实勘）：

- 事件广播：写操作 `window.dispatchEvent(new CustomEvent("novels:changed"))` 类；监听方 `NovelListPage.tsx:129` 等。
- 注册表：`NovelWorkspace.tsx` 的 `registerRefetch`（卸载时塞回空函数）。
- 手写缓存：`lib/version.ts`（cachedVersion＋inflight 去重＋listeners）、`lib/portal.ts`（portalUrlCache）、`lib/licenseCache.ts`（verify 快照＋节流）。

## Goals / Non-Goals

**Goals:**

- 单源查询缓存＋key 失效；写后相关视图自动一致。
- 分域迁移，每域落一个守卫（既有 e2e/预算守卫）。

**Non-Goals:**

- 不迁 AI 流式链路（SSE 语义不同，保留独立）。
- 不迁 LicenseProvider 的 verify 快照（有 60s 节流＋登出清缓存语义，已由 c-silent-data-guards 收口；强行并入得不偿失）。
- 不追求 100% 域覆盖——长尾零散手写缓存迁多少算多少，注册表与事件广播先退役。

## Decisions

**D1：试点域＝书架 novels。**
它已有事件广播的最完整用例（`novels:changed`）与 e2e 守卫，迁移后可直接对照行为。验证期保留事件广播双轨（新缓存失效＋旧事件并存），全绿后撤旧轨。

**D2：失效映射表单源。**
新建 `lib/queryKeys.ts`（key 工厂）＋每个写操作声明失效 key 集合（`invalidateOn` 映射）；杜绝「字符串 key 散落各处」重演手工失效的老路。

**D3：stale 时间窗对齐既有节流语义。**
默认 staleTime 0（写后即失效即重取），消费方显式声明（用量 60s、版本 5min 等），与既有节流口径一一对应，e2e 预算守卫不破。

## Risks / Trade-offs

- [refetch 时序变化触发 e2e 预算守卫/等待语义] → 试点域先行＋全量 e2e；预算守卫本身就是本 change 的验收器。
- [双轨过渡期两套失效并存] → 试点域内一次迁完、不留半态；按域推进不跨域混用。
- [React Query 学习/约定成本] → key 工厂＋失效映射集中在一个文件，约定面收敛。

## Migration Plan

1. 依赖＋Provider＋key 工厂 → novels 试点 → e2e 全量 → 逐域推进 → 撤注册表/事件 → 终验。
2. 每域一个 commit，可独立 revert；试点失败可整体放弃（无数据/契约面影响）。
