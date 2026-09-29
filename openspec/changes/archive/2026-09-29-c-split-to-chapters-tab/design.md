## Context

卷视图（`VolumeWorkspace.tsx`）四页签中，卷纲页签查看态 `ol-top` 挂「拆下一章」手写按钮（`volume-split-manual`，全档）；右栏 `VolumeAssistPanel` 的卷验证面板在 `tab === "outline"` 时渲染「拆下一章（AI）」行（`volume-split-ai`，PRO）与免费锁定/末端拦截两个状态段。两条链路汇入同一 `openChapterPlan(mode)` → ChapterPlanModal。末端门禁数据 `frontierVol` 已在 `VolumeRailData` 上抛，中栏与右栏各自判 `splitBlocked`。规格钉法分散在 volume-outline（本卷章节页签）、chapter-plan-ai（三入口归属）、volume-plan-ai（右栏语境＋入口收口）。e2e 钉法：`chapter-plan.spec.ts` 约 20 处（含 `volume-split-blocked` 段）、`plot.spec.ts`、`cast-review.spec.ts` 各 1 处；页签切换既有惯例 `getByRole("tab")`。

## Goals / Non-Goals

**Goals:**
- 拆章族入口（中栏手写＋右栏 AI）唯一页签＝本卷章节；卷纲页签动作区收窄为「编辑卷纲＋重拆本卷」。
- 门禁、档位、弹窗链路、testid 语义全部保持；改的只有入口所在页签与到达路径。

**Non-Goals:**
- 不动 ChapterPlanModal 本体、落点卡「继续拆下一章」、左树「＋添加章节」。
- 不合并「在本卷新增一章」（仅标题建章）与「拆下一章」（四段结构化拆章）——语义不同，并存。
- 不动「重拆本卷」位置（它配套卷纲页签的「剧情推进（派生）」派生清单，属整卷级重排）。
- 零后端改动。

## Decisions

- **D1 手写按钮落在页签标题行（book.css 增作用域变体）**：本卷章节页签中栏把「拆下一章」放「本卷章节」标题行右侧，台账列表与「在本卷新增一章」不动。**前端评审实勘：既有类做不出这个布局**——`.seg-h` 无 flex（book.css 仅 margin/字体），`.push` 的 `margin-left:auto` 只在 `.ol-top .push` 作用域生效——故 book.css 增一条**修饰类作用域规则**（`.seg-h.push-row{display:flex;align-items:baseline;gap:8px}`＋`.seg-h.push-row .push{margin-left:auto}`），不动全局 `.seg-h`（同页「本卷进度」等标题不受影响）；不新增词汇档位，design:lint 不扫 book.css。备选：改用 `.ol-top` 形制被否（标题从 display 字退化为 mono note，用户可见退化）；借 `.ds-domain-head .btn` 被否（跨组件家族借选择器＝漂移）；「与新增按钮同入底部 edit-bar」被否（主动作沉底降可达性、与新增输入流挤一行易误触）。
- **D2 testid 全部保留原语义**：`volume-split-manual`／`volume-split-blocked`／`volume-split-ai`／`volume-split-ai-locked`／`volume-split-ai-blocked` 不改名不换位（只是所在页签变）——e2e 适配量收敛为「入口点击与右栏 split 行/状态段**断言前**先 `getByRole("tab", { name: "本卷章节" })`」（后端评审补充：断言型前提同样要切页签）。**例外**：免费锁定句与卷纲空态文案随本 change 改口（D3/D8），钉了全文的断言同批更新——testid 与门禁语义仍零改动。
- **D3 右栏随页签条件整体迁移**：`VolumeAssistPanel` 中 split 行与两个状态段的 `tab === "outline"` 判据改 `tab === "chapters"`；`VOL_TAB_LEAD`／`VOL_TAB_ORDER`（体检语境）不动。免费锁定文案按 PM 评审定稿改口：「AI 三方向需 PRO——手写拆章免费：用中栏「拆下一章」」——指**按钮名**而非页面名（迁移后锁定段与按钮同屏，指页面＝自指），并消除「自己写这一章」（弹窗出口词）与按钮名「拆下一章」的用词漂移。
- **D4 `volume-split-blocked` 提示段随迁**：该段解释「为什么不能拆」，跟入口走（钉在 chapter-plan.spec.ts:468），不留在卷纲页签。
- **D5 门禁判据零改动**：拆章两入口维持松判据（`本卷 < frontier.vol` 置灰）、「在本卷新增一章」维持严格等值——存量差异是 spec 明文（chapter-plan-ai 三入口归属），本 change 不碰。
- **D6 页签落点不变**：换卷/进卷默认页签仍是「卷纲」；从右栏「卷的验证」点行进卷后也落卷纲页签——作者要看卷纲再手动切本卷章节拆章。备选「AI 拆章入口点击时自动切页签」被否：隐式导航会打脏 e2e 前提且违反「页签切换只改视图」的简单性。

- **D7 卷纲空门槛改为右栏前置拦截段（含可点击出口）**：本卷章节页签下，卷纲关键项（主旨/冲突/卷末）任一为空时，右栏 split 行上方呈前置拦截段（testid `volume-split-ai-outline-gate`：「卷纲关键项还没填——先补卷纲」＋「去补卷纲」按钮 `setTab("outline")`），点击 split 行不发起请求；后端 422 兜底文案口径不变（其「先去卷纲补齐」指引仍正确——补纲地「编辑卷纲」不迁），ChapterPlanModal 本体不动（proposal「不变」声明保持成立）。数据零新增：`VolumeRailData.detail` 已含卷纲字段。备选「弹窗 error 态加第四出口」被否：事后补救不如事前拦截，且动弹窗违反不变声明。
- **D8 卷纲页签空态死指针翻案（PM 评审 P0）**：「还没有排章——拆下一章后这里会按章列出推进」指向的入口已迁走，且该句钉在主 spec（volume-outline 卷纲字段集 L30＋空态呈现 Scenario）。改为「还没有排章——去「本卷章节」拆下一章，这里会按章列出推进」，其中「本卷章节」为内联可点击出口（`setTab("chapters")`——纯视图动作，不构成拆章入口，不违反「唯一页签」口径，§13 补救带出口达标）；volume-outline delta 相应 MODIFIED「卷纲字段集（查看/编辑两态）」。

## Risks / Trade-offs

- [e2e 前提遗漏：某处点击入口或断言右栏状态段前没切页签] → 适配按「每处 testid 点击/断言前」机械插入切页签（前端评审：重拆用例同例内有两处点击，L409 与回卷视图后的 L432），适配后全量重跑 chapter-plan/plot/cast-review 三文件；条件渲染元素不 attach，漏切只会红不会假绿。
- [卷纲页签空态文案指向已迁走的入口（死指针）] → 已按 PM 评审翻案为 D8（改口＋内联切页签出口）。
- [非 frontier 卷的本卷章节页签同屏两条「还没轮到」提示（随迁的 `volume-split-blocked` 段＋既有「新增章节排在主线末端」行）] → 实现时对拍视觉，必要时合并措辞（前端评审 P2，不拦实现）。
- [右栏本卷章节页签新增生成类入口后，页签语境（体检＝对已写内容）与拆章动作并置显突兀] → 该页签引导语本就是「已写内容与卷纲的出入」，拆章正是补「还没写的下一章」，语义相邻；不加分隔结构，沿用既有 rows 列表形。

## Migration Plan

纯前端单批改动，随版本发布即生效；无数据迁移、无回滚特殊路径（revert 即回原状）。

## Open Questions

（无）
