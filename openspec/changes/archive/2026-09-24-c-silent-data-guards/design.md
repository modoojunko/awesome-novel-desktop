## Context

见 proposal.md 的 Why。落地相关现状（实勘）：

- 主线卡：`useStoryArc.ts:67` 加载失败 `.catch(() => snapshotLoaded(EMPTY_ARC))`，hook 无 error 态；保存走 `lib/api.ts:222` 的 whole-card PUT。
- 完本弹窗：`FinishModal.tsx:62` 伏笔 `.catch(() => setHooks([]))`、`:71` 卷章树 `.catch(() => {})`。
- 建卷建章：`useWorkbench.ts:343-401` 的 `createVolume`/`createChapter` 无 in-flight 保护；入口 6 处（`NovelWorkspace.tsx:834,1061,1068,1100,1143,1150`）；同仓已带闸范式三处（`VolumeWorkspace.tsx:920-936` busy 闸、`modals.tsx:634` submitting+locked、`OutlineTree.tsx:150-151` inlineDoneRef）。
- 权益缓存：`LicenseProvider.tsx:46` 模块级 `cachedVerify`，仅 `refetch()` 置空；`lib/auth.ts:20-25` 的 logout 不清它；`:131` 的 `path === lastRefreshPath` + 60s 节流叠加。
- 提示词总览：`PromptManagementPage.tsx:164-200` for 循环逐章 `await`；`:142` volumes 失败全吞；`:213-215` openViewer 失败显示空内容。

## Goals / Non-Goals

**Goals:**

- 五个失败点在 UI 上有可感知信号，且任何「假状态」都不能触发写入或不可逆动作。
- 双发闸与既有三处范式同款，入口覆盖全部 6 处。

**Non-Goals:**

- 不加服务端幂等（`client_token` 机制的建卷版本）——前端 in-flight 闸已覆盖真实双击路径，服务端幂等登记为后续候选。
- 不引入 React Query/查询层重构（属独立 change `c-query-cache-layer`）。
- 不改后端接口语义（提示词总览新增批量只读端点除外）。

## Decisions

**D1：主线卡失败态＝禁用保存 + 重试，而非「保留上次内容」。**
失败时前端无法区分「真的空」与「未加载成功」，唯一安全形态是不让提交发生；备选（已弃）「保存前回读服务端比对」需要额外请求且仍有时序窗口。

**D2：双发闸放前端 in-flight（对齐既有三处范式），不加服务端幂等。**
`createVolume`/`createChapter` 内部加 `creatingRef`（同 `OutlineTree.inlineDoneRef` 范式），入口按钮同步置忙；`UNIQUE(novel_id, volume_no)` 仍作最后防线。残余风险（多标签/多窗口并发）登记见 Risks。

**D3：权益缓存清理挂在登出这一动作上（单一出口）。**
把模块级 `cachedVerify` 收进带 `reset()` 的缓存单例，`lib/auth.ts` 的 logout 调用之；同时 Provider 在登录态下降沿兜底重置。SHALL NOT 依赖组件重挂（恒挂载口径下不会重挂）。

**D4：提示词总览改批量只读端点（后端一处 SQL 聚合），不是前端并行轰击。**
页面只需「每章是否已有提示词」；新增按书/卷返回存在性列表的只读端点（`GROUP BY chapter_id` 聚合），前端一次取回。备选（已弃）：前端 `Promise.all` 并行——请求数仍随章数增长，SQLite 单库并发写路径也会被压。

**D5：原型先行范围。**
受影响屏：设定·主线卡、完本确认弹窗、空书架卡/空书落点卡（建卷建章入口）、提示词总览页。有对应原型的补失败态/置忙态并在 `ADJUSTMENTS.md` 登记；无原型基线的屏登记「无原型基线，实现侧按既有 notice/按钮态词汇自查」。

## Risks / Trade-offs

- [失败态/置忙态改变像素，parity 门禁可能红] → 原型与 ADJUSTMENTS 同批更新，design:check 重跑。
- [in-flight 闸影响 e2e 点击时序（stableClick 等）] → 相关 e2e 同批更新并本地全量重跑。
- [多标签/多窗口并发建卷仍可能撞 UNIQUE] → 本次不覆盖；错误提示已可读（既有 500 文案），服务端幂等登记后续。
- [新增批量端点扩大后端面] → 只读、单聚合查询、复用既有鉴权与路由前缀；随 C端 后端测试覆盖。

## Migration Plan

1. 原型与 ADJUSTMENTS 先行 → 实现 → 门禁（design:lint / design:check / tsc / vitest / 定向 e2e）。
2. 无数据迁移；回滚 = revert 提交。
