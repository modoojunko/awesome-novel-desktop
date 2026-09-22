# Design: c-write-home-rail-anchor

## Context

三处改动都落在同一张屏（写作页 three-col，`NovelWorkspace.tsx`）与一个弹窗（规划台 `VolumePlanModal.tsx`）。当前实现事实（实勘）：

- **视图与选中解耦**：`view`（workbench／advanced-settings／archives）与「选中哪个节点」（`selectedId/selectedRef`）是两套状态，都在 `useWorkbench` 的 `useState` 里。`setView("workbench")` 只换 `view`，不碰选中（`useWorkbench.ts:328-337` 注释即「切到 workbench 时若无选中，保留现状」）。中栏由**选中态**分派：`chapterRef ? ChapterWorkspace : volumeSelId ? VolumeWorkspace : 默认页`（`NovelWorkspace.tsx:742-831`）。
- **默认页三态已存在**：零卷零章＝起手卡；有卷且 `totalChapters===0 && !everPlanned`＝落点卡；其余＝一句选章引导。`everPlanned` 由 `localStorage pref.book.{id}.ever_planned` 与章节总数双判（`NovelWorkspace.tsx:546-549`）。
- **三个写作入口**：导航点「写作」（`NovelWorkspace.tsx:697`）、设定页「去写作」（`SettingsView onGoWrite`，第 874 行）、预览页「去写作」（第 885 行）。三者都不清选中。
- **设定与预览的挂载方式**：`SettingsView` 与 `PreviewView` 都是条件挂载（`{view === "advanced-settings" && …}` / `{view === "archives" && …}`），所以**从别处进入**它们本来就从默认态开始（设定默认面板＝`normalizePanel(undefined)` → 第一项「简介」；预览无人为定档时回落首章）——真正缺「回默认主页」的只有**已在页内时重复点同一个页签**这两条路径。预览另有一条**跨屏继承**：`initialRef={chapterRef}` 把写作页当前章带进预览（源码注释即「初始定档章（写作视图当前章；缺省/失效回退首章）」）。
- **three-col 常驻挂载**：正文编辑器与卷纲表单都在同一棵树里靠 `.view.on` 显隐（第 721-722 行注释：「正文脏状态/流式现场不丢」）。清选中会让 `ChapterWorkspace` 真正卸载——这是本次改动唯一需要设防的地方。
- **右栏分派**：`Rail mode={chapterRef ? "chapter" : "volume"}`；章模式再按 `tab` 走 `AiAssistPanel` 八分支；卷模式一律 `VolumeAssistPanel` → `VolumeVerifyPanel`（`VolumeAssistPanel.tsx:222-232`），**完全忽略 `VolumeRailData.tab`**（卷页签已经在数据通路里，只是没人用）。
- **锚点单源**：`plan-anchor` 端点返回本卷进场 `{prev_ending:{text,source}}`（事实优先：有归档章取实际收尾，否则取上一卷卷纲的预期结局；首卷取全景起步）；前端由 `useAnchor` 取一次，只渲染在弹窗顶部 `plan-anchor` 块（`VolumePlanModal.tsx:118-147、198-226`）。
- **设计源**：`drafts/storyline.html` 的 `aiVolHTML` 原本就为卷选中态写了四套页签右栏；`volume-plan-ai` 把其中的「统计卡＋卷域动作清单」退役成单一验证面板（`openspec/specs/volume-plan-ai/spec.md`、`workbench/spec.md:442`）。本 change 沿验证面板收窄，**不复活**退役件。
- **既有 e2e 依赖**：20 余处 `.mtab 写作` 点击把「写作」当作**回到写作视图**的手段（`settings-forms.spec.ts:735` 依赖回写作后原章仍在选中、`reconcile.spec.ts:259` 之后自己点章）。

## Goals / Non-Goals

**Goals**

- 三个页签（写作／设定／预览）点下去都回各自默认主页，且**任何入口**（含从别处切回、含重复点当前页签）一致；书主页恒有建卷建章入口 + 续写入口。
- 卷选中态右栏随卷页签变化，全部用既有数据与既有动作（体检报告重排、规划台入口），**不新增端点、不改后端**。
- 规划台 3 套卡片各自带上卷末进场信息，取数单源、零新增请求。

**Non-Goals**

- 不改「打开书」的默认落点（无章→设定／待完本→写作／已完结→预览；写作落点仍自动聚焦主线首章）——「打开书」与「点页签」是两件事。
- 不给卷页签新增 AI 能力（拆章、卷级关系/伏笔检测需新端点；另立 change）。
- 不给预览加 AI、不改预览三栏结构与阅读配置；不改章页右栏八页签行为。
- 不动后端、不动数据模型、不新增 localStorage 标记。

## Decisions

### D1 三个页签各回默认主页：一个导航入口规则，三种页内机制

三个页签的「回默认」是同一件事，但落到各页的机制不同——**都不塞进 `setView`**，而是在 `NovelWorkspace` 里显式分流：

| 页签 | 回默认动作 | 机制 | 现状对照 |
|---|---|---|---|
| 写作 | 清选中 → 中栏默认页 | 新增 `goWorkbenchHome()`：守卫 → `clearSelection()` → `setView("workbench")` | 现在只换 view，选中留着 |
| 设定 | 面板拨回默认项（简介） | 壳层持 `settingsHomeSeq`，点「设定」时递增并透给 `SettingsView`；组件内 effect 收到新 seq 就 `setPanel(默认面板)`（回执由既有 `[panel]` effect 一并清） | 已在设定时点「设定」是无操作 |
| 预览 | 定档回首章 | 壳层持 `previewHomeSeq`，点「预览」时递增并透给 `PreviewView`；组件内 effect 收到新 seq 就 `setSelRef(null)`（既有回落链→首章） | 已在预览时点「预览」是无操作 |

- 写作的三个入口（modnav 写作 / 设定左栏完成卡「去写作」/ 预览空书出口「去写作」）都改走 `goWorkbenchHome()`；**不动** `focusNode`、`onSelectNode`、`selectVolume`、`createVolume/createChapter`——它们走「点节点」语义，本就该带选中。
- 预览的跨屏继承同时下线：`initialRef={chapterRef}` 不再传（定档一律落首章）。这样「从写作页进预览」与「重复点预览」是同一条规则，不再有两套落点。
- 备选：把清选中塞进 `setView("workbench")`。否决——`setView` 也会被非导航路径调用，会把「点章跳转」一并清掉；而且守卫要有 UI 出口，塞不进纯状态函数。
- 备选：用 `key={seq}` 重挂载 `SettingsView`／`PreviewView` 来复位。否决——重挂载会丢滚动位置并多一轮取数，而设定面板表单本来就是随面板切换重挂载的，一个信号足够。
- 备选：设定/预览不做（只做写作）。否决——用户口径是三个页签都要有默认主页，且「重复点是操作」这条规则三者必须一致。

### D2 守卫只拦真会丢东西的两件（按页签各自复用既有守卫）

- **卷纲表单脏**：复用既有 `guardedLeave()`（`NovelWorkspace.tsx:118-123`，文案与出口不变）。
- **设定表单脏**：复用既有设定脏守卫（`settingsDirtyRef` + `go()` 里的确认），回默认面板同样先确认。
- **正文 AI 流式生成中**：清选中会卸载 `ChapterWorkspace` → 流式现场丢失，故先 `window.confirm`（「AI 正在生成正文，回主页会中断这次生成」）。判据用页面级 `aiState.streaming`（壳层已持有，第 172 行）。
- 预览只读，无未保存态，不拦。
- 章纲表单与正文走既有自动保存（3s 自动保存／编辑即存），**不拦**——拦了会与「写作＝随时可回主页」的口径打架。

### D3 默认页第三态升级为「书主页卡」，不新增第四态

```
                打开书（落点不变：无章→设定／待完本→写作／已完结→预览）
                      │
     ┌────────────────┼─────────────────────┐
     │                │                     │
 点「写作」        点「设定」            点「预览」
     │                │                     │
     ▼                ▼                     ▼
 清选中→书主页    拨回默认面板(简介)      定档回首章
     │
     ├── 零卷零章 ──────────► 起手卡（＋新增一卷 / ＋新增一章）
     ├── 有卷 && 0 章 && 从未排章 ──► 落点卡（＋在本卷排第一章 / 看卷纲 / ＋新增一卷）
     └── 其余（含删空后曾排章） ───► 书主页卡（进度眉标 / 续写 / ＋新增一卷 / ＋新增一章 / 选章引导）

 不进「默认」的路径（各归其位）：点左树章/点卷 · 右栏体检点行 · 续写 · 卡上动作 · 预览内目录与上一章/下一章
```

书主页卡的「续写」直接复用顶栏 `hereTarget` 与 `onResume()`（草稿回上次位置、拟定开章纲、待写先建再写），保证与顶栏同文案、同判据、同行为；进度眉标（卷数 · 章数 · 已归档 · 全书总字数）取 `wb.volumes` 现成派生值。`everPlanned` 判据不改（既有 e2e 依赖它区分落点卡与主页卡）。

### D4 卷选态右栏：同一条验证链路，按页签换视角与顺序

`Rail` 把 `volumeData.tab` 透给 `VolumeAssistPanel`（数据已在 `VolumeRailData` 里，零新增取数）：

| 卷页签 | 「当前页签」 | 引导语焦点 | 报告组顺序 | 额外动作 |
|---|---|---|---|---|
| 卷纲 | 卷纲 | 走向与结构 | 对主线 → 对设定 → 对已写内容 | 「重新规划这一卷（AI）」（PRO；`openPlanVolume(本卷卷号)`） |
| 本卷章节 | 本卷章节 | 已写内容与卷纲的出入 | 对已写内容 → 对主线 → 对设定 | 无 |
| 角色关系 | 角色关系 | 本卷人物在全书口径下成立 | 对设定 → 对主线 → 对已写内容 | 无 |
| 伏笔 | 伏笔 | 本卷伏笔在全书口径下成立 | 对设定 → 对主线 → 对已写内容 | 无 |

- 报告只**重排**既有三组，不重跑、不改写、不裁剪结论；未体检时只呈现引导语与动作（不预置空报告）。
- 「重新规划这一卷」的语义＝打开规划台且卷号＝本卷；采纳后仍走既有 `backfill → 逐段落进卷纲表单 → 作者保存`（不落库）；已有卷的 `vol-N` 存在，`startBackfill` 不建卷、只 `focusNode`。
- 备选：按 storyline 原型复活四页签统计卡与动作清单。否决——`volume-plan-ai` 刚把它们退役（含未落地的动作），复活等于开倒车；也违背「动作必须有真实链路」。

### D5 卡片「上接」沿用锚点单源，只做呈现

抽卡弹窗（`PickCardsModal`，c-volume-antagonist 后的新卡面）每张 `.pick-card` 在卡首插一行
`.pk-row.pk-in`：`<b>{first ? "起点" : "上接"}</b><span title={anchor.text}>{anchor.text}</span>`；
锚点由组件内 `useAnchor`（`GET /volumes/plan-anchor`，事实优先）取，样式用 `-webkit-line-clamp: 2`
截断、全文挂 `title`。testid 用 `pick-enter-{n}`（避开既有 `pick-card-` 前缀正则）。

- 取数复用 `useAnchor(projectId, state.volNo, state.open)`——不新增请求、不与锚点块分叉。
- 该行**不进提示词、不参与相似度去重、不要求模型申报**（`_sanitize_plans` 与 difflib 复核零改动），所以后端零改动。

### D6 基线漂移（2026-09-22 重做）

本 change 的首版分支切自 `dfceb17d`（c-volume-antagonist #458 之前）。#458 把规划台整体重写
（新增 `PickCardsModal` 三选一抽卡、`VolumePlanModal` 转四问手写页、建卷统一走规划流、
「添加卷」独立弹窗退役）——直接合入会把弹窗改回旧版。故 2026-09-22 把三件事**重新落到 origin/main**：
`goTab`/书主页卡重贴在 #458 后的 `NovelWorkspace`；卷页签右栏重贴（保留 main 的 `nextVolNo` 单源）；
卡片「上接」改落在 `PickCardsModal`；spec/design 增量按 main 现文本重抄（新增需求改 ADDED 式）。

### D7 原型先行与 parity

`prototypes/book.html` 不动（其 parity case 是「默认章工作台」，本次不改该屏版式；默认页不在 book.html 基线内）。先改 `drafts/storyline.html`（卷右栏段：验证面板随页签收窄）与 `drafts/ai-novel-c端-整书拆纲.html`（默认页④、cand 卡「上接」），并在 `ADJUSTMENTS.md` 登记三处偏差与「drafts 不进 parity 扫描」依据；设定/预览的回默认只改落点，按一条行为口径登记、不动原型。

## Risks / Trade-offs

- **清选中卸载章工作台** → 流式生成丢失、滚动位置丢失。缓解：D2 流式确认；`onWriteProgress` 已把上次写作会话（ref＋scroll）落 localStorage，书主页卡与顶栏的「续写」都能一键回到那里。
- **预览不再继承写作页当前章** → 「写到第 5 章顺手看一眼预览」会落在首章，多几步。缓解：预览自己的选择在页内保留（切页签才复位），且目录点章／上一章／下一章都在；e2e 里两条注释与断言（`workbench-features.spec.ts:766`「初始章 = 写作视图当前章」、`design-parity-preview.spec.ts:104` 的 stub 说明）随口径更新。
- **设定重复点即拨回默认面板** → 停在世界面板改了半截再点「设定」会回简介。缓解：D2 设定脏守卫先确认（与离开设定同一套确认），确认才拨回。
- **e2e 大面积依赖「点写作」不重置选中**（20 余处） → 缓解：任务里逐处审计，凡「点写作后直接断言原章内容」的用例补一步选章或改用「续写」；其余（建书后切写作、点写作后自己点章）不受影响。这是本 change 最大的回归面，全量 e2e 必须跑。
- **「上接」三张卡重复同一段文本** → 版面变重。缓解：两行截断＋`title` 全文；若评审后仍嫌重，退路是改成卡片区吸顶条（spec 只要求「卡片区可判断衔接」，末句已写成可查看全文而非必须逐字全显）。
- **卷纲页签新增「重新规划这一卷」可能被用来覆盖已有卷纲** → 缓解：回填只进表单、不落库，保存前作者可取消；`plan_line`/字段级 `touchedRef` 保护回填期间的手改。
- **两处 spec 术语（写作默认页／书主页卡）** → 缓解：volume-plan-ai delta 首次出现处标注「（书主页卡）」指向 workbench 的同一物。

## Migration Plan

无数据与契约变更，无需迁移。落地顺序：原型与 ADJUSTMENTS 登记 → 实现 → vitest／tsc → 设计门禁（design:lint；book 屏无像素基线改动，design:check 应与 main 一致）→ 本机隔离栈全量 e2e。回滚＝revert 前端提交（后端、数据库、localStorage 标记均未动）。

## Open Questions

- 「打开书」是否也落「写作书主页」（现在仍按阶段落点并在写作落点自动聚焦主线首章）：本次按「只改点页签」处理，若评审后要改，是一行落点改动 + 落点 e2e 调整，不动任何 spec 结构。
- 卡片「上接」是否同时要一条吸顶条：本次只做卡内行；若实际用起来仍要滚回顶部看全文，再加吸顶条（前端小改，spec 末句已留口）。
