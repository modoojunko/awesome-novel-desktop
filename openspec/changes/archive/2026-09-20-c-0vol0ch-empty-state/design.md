## Context

写作页的四个面（顶栏 bar-here／中栏／左栏树／右栏 AI 助手）各自独立演进，空书态从未被单独立卷：
`hereTarget === null` 时顶栏整块留空、中栏与「有卷未选中」共用一块通用面板、左栏只指路到卷、
右栏一句卷语境引导。设计稿 `docs/design-c/drafts/0vol0ch-empty-state.html` 是 storyline 原型族
的「空数据版」，因此它的空态语言与工作台其余部分同源（`.e-empty`／`.tree-add`／无语境 aiShell
均取自 storyline 既有类），实现只需落地、不需新造。

约束：①书树（左栏）当前按 `prototypes/book.html` 基线（`storyline` 的 `.tree-tools`/常驻
`.tree-add` 未采用），本批 SHALL NOT 顺手改造整列；②「名称即标题且必填」（#164）＝建卷必须
给名，不能像原型那样直建「第一卷 · 未命名」；③写作视图**常驻挂载**（切设定/预览只摘 `on`
class），任何新增类名都要考虑在其它屏的 DOM 可见性。

## Goals / Non-Goals

**Goals:**

- 零卷零章的写作页给出明确起点：起手动作处处可达（顶栏／中栏／左栏），且三处指向同一实体。
- 空书可直接排第一章（系统垫卷），不再出现「请先创建卷」的死路。
- 有卷未选中与零卷零章两种情形在文案与入口上区分开。
- 右栏未选中态与原型无语境 aiShell 一致（页签「未选」＋四格全书统计）。

**Non-Goals:**

- 不采用 storyline 左栏结构（搜索框／计数行／回到当前／常驻 `.tree-add`）——属另一批。
- 不改空书默认落点（仍落「设定」，2026-09-10 拍板）；本批只治用户切到「写作」后的呈现。
- 不改 modnav 右侧说明句与「设定 N/7」计数（壳层既有口径，跨全部书内视图）。
- 不引入新的数据请求面：悬置伏笔复用既有 `GET /hooks`。

## Decisions

**D1 起手卡用 `.e-empty` 而非沿用「开始创作」面板。** 原型 `bookEmptyHTML()` 就是
`.e-empty`＋`.be-k/.be-t/.be-acts`；沿用旧面板等于两套空态语言并存。旧面板的 `panel-head h2`
版式在中栏已由 storyline 皮肤接管，空态继续用它反而要打补丁。

**D2 空书态底部两入口替代「确认全部已填章节」，非空书态左栏零改动。** 批量确认在空书里没有
对象（0 章）；若改成「空书也常驻两入口」会与 book.html 基线（parity 场景）产生像素差，且属
左栏整列改造。折中：只在空书态渲染 `.tree-add`，并用 `.col-tree.empty-book` 修饰类把列改
flex 纵排让按钮贴列底——修饰类只在该态挂载，非空书态滚动容器行为不变。

**D3 「＋ 新增一章」在壳层实现垫卷，而非下沉到 `useWorkbench.createChapter`。** 原型
`addPlanned → firstVol` 是空书专属兜底；hook 层若自动建卷，会让「无卷建章」在任何调用点都
静默造卷（含未来批量场景），语义过宽。放在 `NovelWorkspace.addFirstChapter`：无卷时先
`createVolume('第一卷')`（默认序号形态，用户可改名）再 `createChapter('第一章', volRef)`。

**D4 「添加卷」弹窗上移壳层。** 空书态三处入口必须打开同一实例；弹窗原居 `OutlineTree`（树头
「＋」唯一入口）。移入 `modals.tsx`（工作台弹窗群既有归属），`OutlineTree` 改为接 `onAddVolume`
回调——零视觉变化，e2e 既有 `getByTitle("添加卷")` 链路不动。

**D5 右栏未选中态按原型返同级元素，不套 `.rail-assist`。** 原型 `aiShell` 没有这层包裹，
纵向节奏由 `.col-ai` 的 flex `gap:14px` 提供；而设定页右栏 `AiWriterAssistant` 也用
`.rail-assist`——写作视图常驻挂载，套上后 `.col-ai .rail-assist` 在设定页匹配到两个元素，
全量 e2e 挂 6 条（foreshadow-ai／genre-ai-settings×4／world-settings，strict mode violation）。
改为同级元素后 6 条转绿；vitest 钉「`.col-ai > .rail-stats` 在、`.col-ai .rail-assist` 空」。

## Risks / Trade-offs

- **类名跨屏污染（已实证并覆盖）**：见 D5。写作视图常驻挂载使任何新增类名在设定/预览页也
  存在于 DOM；本批新增 `.e-empty/.be-*`、`.tree-add/.add-btn`、`.empty-book` 均先 grep 过
  全局无同名，`.rail-assist` 的教训已写进测试。
- **左栏空书态与原型位置差异**：原型的 `.tree-add` 常驻列底（`.toc` flex 撑高），实现只在
  空书态贴底——非空书态左栏结构与 book.html parity 不受影响，偏差已在 ADJUSTMENTS 登记。
- **测试时序脆弱（既有，顺带修）**：`NovelWorkspace.test.tsx` 两条「渲染后即 three-col on」
  断言依赖「落点 effect 尚未应用」，空书落点恰是「设定」。改为显式 `goWriteView()` 后再断言；
  真实落点口径由 `e2e/landing-view.spec.ts` 覆盖，未改动落点逻辑。
- **不做双轨兼容**：本批直接替换旧面板文案，不留兼容分支（当前无真实用户，兼容包袱可丢）。
