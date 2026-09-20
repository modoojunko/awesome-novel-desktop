# Design: c-workbench-outline-fixes

## Context

写作工作台有两份并行的树数据源：左树吃 `useWorkbench`（`GET /novels/:id/volumes`），顶栏「写作 N/M 章纲」计数吃 `useOutline`（`GET /novels/:id/tree`，后端与 `/volumes` 同源 `list_volumes`）。两份 state 各自刷新：树变更动作里，批量确认（`OutlineTree.handleBatchConfirm`）双刷、加卷弹窗经 `onCreated` 刷 outline，但 `useWorkbench.deleteNode` 与行内加章（`commitInlineAdd`）只刷 `useWorkbench` 自己 —— 顶栏计数停留在旧值（2026-09-19 实勘：DB 0 章而顶栏 0/10）。「章数目标」字段被 `book.css` 的 `.field.chtarget { flex: 0 0 160px }` 固定窄列，label＋行内长提示挤成三行折行（该缺陷的修复已移交 c-volume-view-storyline）。「确认全部已填章节」按钮无空态守卫。逐章确认走 `useOutline.confirmChapter` 的乐观更新（`chapterStatuses` 置 confirmed → `confirmedCount` 重算）。

## Goals / Non-Goals

- Goals：树变更后顶栏计数与左树一致；批量确认空态禁用（workbench 规格两条新增需求的落地；原「章数目标」布局随 2026-09-19 收窄移交 c-volume-view-storyline）。
- Non-Goals：不合并两 hook 的数据源（后续演进，见 D1 备选）；不动卷纲右栏「规划中」卡（proposal 已排除）；不改删除确认弹层与批量确认的既有交互；不触 base.css 共享段。

## Decisions

### D1. 计数一致性：变更调用点补刷，不合 hook

在漏刷的两个调用点补 `outline.refetchTree()`：删除确认回调（`OutlineTree` 中 `wb.deleteNode(...)` 之后）与行内加章（`commitInlineAdd` 成功后）。加卷弹窗与批量确认已有双刷，不动。修改一处调用形态：删除回调由 `void wb.deleteNode(ref)` 改为串行 `await wb.deleteNode(ref); await outline.refetchTree()`（或 Promise.allSettled 双刷，与 handleBatchConfirm 同款写法）。

- 备选（否决）：把 `useOutline`/`useWorkbench` 合一数据源或引入统一刷新总线 —— 触及 ChapterWorkspace、ProseTab、恢复会话等多处数据流，bug 修复的合理半径内不做；两接口后端同源，双刷代价可忽略（全量树轻接口）。
- Bug8 复验口径：qa-night 观察到「逐章确认后计数全程 0/6」，而当前代码 `confirmChapter` 有乐观更新，理论上计数应涨。实现期必须复验该场景；若复现，优先怀疑 `refetchTree` 后 `buildStatuses` 用树元数据重建 `chapterStatuses` 把乐观值冲掉（`deriveOutlineStatus` 是否能从 `/tree` 章级 status 判出 confirmed——核对后端 `list_volumes` 是否回填 `outline_status`/`confirmed_at` 语义）。修复口径：任何重建不得把已确认章降级。此条计入验收场景「逐章确认后计数增长」。

### D2. 「章数目标」：提示下移成独立小字行，列宽不动

结构改为：label 单行「章数目标」→ 输入框 → 提示行「1-9999，留空为不设」（沿用 `.opt` 小字语气、起独立一行，不新增字号/词汇档位）。两列各为「label＋input」等高栈，输入控件顶边自然对齐。

- 备选 A（否决）：加宽列到能容纳行内提示 —— 需要 ≈230px+，挤压「结构模板」下拉，且提示文案长度不受控，将来改文案又会折行。
- 备选 B（否决）：缩短提示为「≤9999」类 —— 丢「留空为不设」语义，该语义决定作者是否必填。
- 落点：原型 `book.html` 卷纲表单（约 :1476）与实现 `VolumePanel.tsx`（:176-189）同构改；`book.css` `.field.chtarget` 保持 160px，新增提示行样式复用既有小字档位。原型另两处 `tpl-row`（地点/时间、角色名/故事角色）非本字段，不动。

### D3. 批量确认禁用：与批量确认循环同口径判定

禁用条件 = 「不存在未确认且未归档的章」，与 `handleBatchConfirm` 跳过条件（`status === "confirmed" || archived`）严格同口径，数据源用 `OutlineTree` 已有的 `outline.volumes` + `outline.chapterStatuses`。禁用时按钮置 `disabled` + `title="没有可确认的章节"`；样式沿用 btn-ghost 既有禁用语言。0 章、全部已确认两种空态天然被同一条件覆盖。

- 备选（否决）：隐藏按钮 —— 位置跳动，且作者失去「这里能批量确认」的功能感知；禁用＋悬停提示保留可发现性。

## Risks / Trade-offs

- [补刷多发一次 /tree 请求] → 与既有批量确认双刷同模式；接口为轻量全量树，无性能顾虑。
- [乐观更新被树重建覆盖（Bug8 候选根因）] → 实现期第一项复验；若确认后端树缺 confirmed 语义，以后端回填为正解、前端重建守卫为兜底，不做双份状态硬拼。
- [e2e 存量断言受禁用态影响] → 现有 e2e 无此按钮断言（已核对）；新增断言按最小覆盖补。本机全量 e2e 按 c-client-e2e-runbook 配方跑。
- [原型与实现漂移] → D2 结构改动两端同批落笔（book.html 与 VolumePanel/book.css 同一 PR），ADJUSTMENTS.md 登记，防「原型先行」沦为一次性文档。

## Migration Plan

纯 C端前端改动，无数据迁移、无接口变更；随常规 PR 合入 main、随下版发布。回滚 = revert 该 PR（无状态残留）。

## Open Questions

无。卷级右栏 AI 的实装与文案视角改写已明确排除在本次范围外（需产品拍板后另行 propose）。
