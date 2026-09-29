## Why

卷纲页「角色关系」页签只画开书设定边：卷态（`volumeScope`）下 RelationsGraphPane 从不加载剧情关系（无 `chapterRef` 时 dossier 恒空），章里采纳的关系变化一概不上图——只有走「收尾提案物化进设定」的边才带 `origin_chapter` 出现在卷页。该行为沿 c-volume-view-storyline 时的旧取舍（「卷选中态投影……不并入剧情边」，#434 立项即定，#576 做章关系图时沿袭未动），与用户期望冲突。用户 2026-09-29 拍板：**卷页角色关系应随时对齐本卷剧情最新的已确认关系**。

## What Changes

- 卷态并入剧情关系边（截至本卷末）：`GET /dossier/preview?up_to_ref={本卷末章 ref}` 的 relations 域（写章消费同一折叠单源：已采纳∧已归档∧非 stale，按 (owner,other) 后章覆盖）。
- 「随时对齐最新」补口：投影范围内**未归档章**（归档后回草稿重写的窗口）的已采纳关系行并入投影（章档端点逐章拉取，已采纳才入图）。
- 卷过滤语义不变：来源章卷号大于该卷的边不显示（`visibleEdges` 既有投影过滤，本 change 只是给它喂上数据）。
- 待确认提案行卷态 SHALL NOT 上图（只读投影，提案去章工作台确认）；无章高亮、无工作流区，页签保持只读。
- 加载门控对齐章态（剧情边就位前呈「加载中」，不闪开书设定半成品图）；树/preview 拉取失败静默退回开书设定边（不阻断图）。
- 文案同步：卷态图 aria-label 与图例标明「截至第 N 卷末剧情投影」；图例附剧情演变条数。
- spec 同步（MODIFIED）：`workbench`「角色关系页签」Requirement 的卷选中态条款（「不并入剧情边」→「并入截至卷末剧情边」）＋新增卷态投影 Scenario。
- 零后端改动（preview 与章档端点均现成）；VolumeWorkspace 零改动（props 不变）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 「角色关系页签（关系图为主表达）」Requirement 的卷选中态条款重写——卷态并入截至该卷末的剧情关系边（preview 截至本卷末章＋未归档章已采纳行并入），待确认不上图；新增「卷态剧情边投影」Scenario。

## Impact

- 前端：`client/frontend/src/components/novel/workbench/RelationsGraphPane.tsx`（卷态数据分支＋加载门控＋文案）；`ChapterMeta` 补 `archived` 字段。
- 测试：`src/__tests__/workbenchExtras.test.tsx`（卷态用例重写＋新增并入/跨卷过滤/未归档并入/失败静默/aria 断言）；e2e `chapter-dossier.spec.ts` 在 ③″ 后插卷态投影断言。
- 后端：零改动。
- Design Impact（用户可见界面改动，规则必填）：
  - 受影响端：**C端**（S端 不涉及）。
  - 受影响屏/弹层：写作工作台·卷视图「角色关系」页签——图的内容（剧情边并入）与图例/aria 文案，无布局与组件结构变化，无新弹层。
  - 对象状态：沿用既有边状态词汇（开书设定淡／往章演变中／本章加重／待确认虚线），卷态新增的剧情边复用「往章演变中」档，**不新增状态档位、不新增组件词汇**。
  - 共享段：**不触碰**（零 CSS 变更，design-cross 不适用）。
  - 原型先行：卷视图事实源 `drafts/storyline.html` 已随 2026-09-26 drafts 清理下线，该屏不入像素 parity 基线（ADJUSTMENTS「storyline.html 卷视图整页落地」条口径）；本 change 为数据投影语义变化、零样式改动，按近期卷域改动先例（c-ai-rail-shared、c-ops-archive-stages、c-split-to-chapters-tab）以 **ADJUSTMENTS.md 按 change 段登记**替代原型收编，设计工件由实现侧自查产出。
  - 文案口径：图例保持既有「截至第 N 卷末（只读投影）」句式；无按钮/补救语句新增。
