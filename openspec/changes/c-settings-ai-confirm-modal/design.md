# 设计：设定域右栏 AI 交互统一弹窗确认制

## Context

设定域 7 面板 × 29 条右栏 AI 能力行，结果呈现现状三套：格下内嵌结果区（`AiSink.tsx`＋各表单 `sinks` state，简介/题材/世界/主线/伏笔共用）、卡内预览块（`CharacterManager` 的 `sink`/`bootstrapSink`，aiz-head 词汇）、无预览直写（`StyleSettingForm.runAiByKey` 的 polish/fewshot 分支，仅回执撤销）。另有**非右栏出稿口**两类：主线第三问行内「AI 帮我填」（tone，走同一 `runAi` 与 AiSink）、世界格头快捷钮（与右栏共用 `runAi` 入口）、世界体检报告内「AI 补」快捷链——本设计全部收编。写作域已有成熟弹窗族（`design/Modal.tsx` 壳＋`AiCheckModal`/`CastReviewModal`/`PickCardsModal`）；设定域还有零引用死代码 `settings/AISuggestionModal.tsx`（内容＋换一个＋接受这个）。后端生成/体检端点形状不动，本设计纯前端呈现层。

## Goals / Non-Goals

**Goals**
- 29 行＋行内/格头/体检快捷链出稿口的结果统一进弹窗：生成类确认才写回、关闭即弃（在途保护见 D9）；体检类只读报告。
- 复用写作域弹窗元素与设定域既有行词汇；不新增视觉词汇定义（既有词汇作用域重挂，见 D2）。
- 各域既有采纳副作用链（recordChange 回执一步撤销、伏笔精确逆操作、角色只补空格复查）原样保留——只换呈现面。

**Non-Goals**
- 不改后端端点、提示词、数据契约。
- 不动右栏卡片布局（`.rail-assist`/`.ra-*`）与免费锁定门控。
- 不动文风蒸馏三步流（画像确认卡保持面板内视图）。
- 不做多弹窗堆叠/弹窗内再抽屉——一时刻一弹窗；**实现约束：AiCardModal 与 StylePasteModal 互斥**（任一 open 时另一个入口禁开；现有调用面天然串行——StylePasteModal 仅由蒸馏流内按钮打开，但钉住约束防未来回归）。

## Decisions

### D1 弹窗状态所有权放各表单，公共件只出「壳与卡形容器」

**选择**：不建全局 modal store / context。每面板自持 `{open, kind, payload, version}` 的弹窗 state，`runAi` 填 payload；公共层新建薄组件（暂名 `AiCardModal`，落 `settings/` 目录），包 `design/Modal` 壳并按卡形分发渲染（children 为主，卡形只管 footer 按钮组与 loading 骨架）。各表单既有 `clearAi`（确认成功后由 SettingsView 调用）**扩为同时关闭弹窗并清缓存**。
**理由**：各域采纳逻辑强耦合本地 state（sinks→表单 patch 的闭包、伏笔 createRows、角色 cardId 复查），抽到全局会把采纳回调全部提升成 props 地狱；AiWriterAssistant 的 `guard`（在途互斥/门控）也留在行点击处不动。
**替代否决**：全局 context 统一管理——改写量大、回归面广，且各域副作用链无法通用化。

### D2 四卡形＋CSS 词汇作用域重挂（评审 P1-1 处置）

卡形与 footer 骨架统一＝次级「关闭」＋主行动键（按域文案）＋可选「换一个」；生成中 footer 隐藏主行动、占位常显；loading 态不裸奔（AISuggestionModal 原底座 loading 时 footer 整个消失，复活时补「关闭」常驻）。

**域 × 卡形 × 确认键 × 关窗行为总表**：

| 域 · 行 | 卡形 | 确认键 | 确认后 | 关闭即弃 |
|---|---|---|---|---|
| 简介 · 补缺失/润色 | 文本卡（润色带前后对照） | 接受这个 | 写回＋回执＋自动关 | ✓ |
| 简介 · 体检 | 报告卡 | —（关闭/重新检查） | — | ✓（缓存 findings，重开免重跑见 D9） |
| 题材 · m1 多看点 | 候选勾选卡 | 采纳 | 写回该格＋回执＋关 | ✓ |
| 题材 · m2/m3/m4 | 文本/结构化卡 | 采纳 · 覆盖 | 同上 | ✓ |
| 世界 · 舞台/力量/代价 | 文本卡 | 采纳 · 覆盖 | 覆盖格＋回执＋关 | ✓ |
| 世界 · 铁律/势力 | 结构化卡（**新增渲染**：kv/势力行由 `entry.value` 结构化数据拼装，现状 sink 只渲染 join 文本） | 采纳 · 合并 | 合并＋回执＋关 | ✓ |
| 世界 · 体检 | 报告卡（含 AI 补链/跳转出口，见 D6） | — | — | ✓ |
| 主线 · 起草/校准 | 结构化卡（全景＋三问逐格） | 采纳 · 覆盖 | 写回＋回执＋关 | ✓ |
| 主线 · 体检 | 报告卡 | — | — | ✓ |
| 主线 · 行内 tone「AI 帮我填」 | 文本卡 | 采纳 · 覆盖 | 写回＋回执＋关 | ✓ |
| 角色 · persona/dossier/cog | 结构化卡（逐格 diff，只标将写入的空格） | 采纳 · 写入 | 单格写入＋回执＋关 | ✓ |
| 角色 · bootstrap | 结构化卡（同上；空态引导卡内出稿同走弹窗） | 采纳 · 写入 | 建卡/补写＋回执＋关 | ✓ |
| 角色 · 体检 | 报告卡（chk-row 行） | — | — | ✓ |
| 伏笔 · 起草 | 候选勾选卡（3 条勾选） | 采纳 | 建行＋精确撤销回执＋关 | ✓ |
| 伏笔 · 收束 | 结构化卡（章位＋收束记录；已有收束明示「覆盖并收束」） | 采纳/覆盖并收束 | PATCH＋移入已收束＋关 | ✓ |
| 伏笔 · 埋坑/一致性 | 报告卡（行可点跳转，见 D6） | — | — | ✓ |
| 文风 · 润色 | 结构化卡（**新增渲染**：三区前后对照，现状直写无预览节点） | 采纳 · 覆盖 | 三区写回＋回执＋关 | ✓ |
| 文风 · 例句提炼 | 结构化卡（例句列表） | 采纳 | 写回例句区＋回执＋关 | ✓ |
| 文风 · 锚定体检 | 报告卡 | — | — | ✓ |
| 文风 · 蒸馏 | （不进本弹窗体系——保持面板内画像确认卡） | — | — | — |

**CSS 作用域重挂**：`.chk-line/.chk-grid/.cand/.c-tag/.aa-note/.title-check/.tc-*/.mpt-*` 等现存于 `.settings-v .ai-sink` 后代选择器下（book.css:639-655、817-823 等），Modal portal 到 `document.body` 后全部不命中。处置＝新建弹窗卡体容器类（如 `.ai-card-body`，C端 局部），把这批词汇**原样改挂**到该容器下（词汇定义不变、只换选择器前缀）；`ck-list` 是 AiCheckModal 的两列 findings 卡片形态、无三态色行与可点行，不搬——设定域检查行沿自家 `chk-*` 词汇。写作域弹窗不复用 `.ai-sink` 家族（已 grep 验证），退役连带面干净。

### D3 历史切条退役，「换一个」承担重生成；补偿＝版数计数＋旧版保留

`AiSink` 的 5 次历史（`h.list.slice(-5)`＋`ah-chip` 切换）不进弹窗；「换一个」就地重生成并**替换**当前卡内容。补偿（评审 P1 处置）：
- 文本卡显示已生成版数「第 N 版」（从 1 起、「换一个」递增）——计费透明；
- 「换一个」在途期间旧版保持可读可采纳，新版到达后替换——比对成本降一档。
**代价**：连续抽卡并排比对多稿的能力仍丢失（用户拍板接受，见 proposal）。

### D4 在途互斥沿用 `AiWriterAssistant.guard`＋各面板 busyRef 双层

行点击仍经 `guard`（ref 同步判定连点窗口归零）；弹窗内「换一个/重试/重新检查」经各表单既有 `busyRef`。两层都在，不需要新机制。已知差异（保留现状）：世界 `checkFixAi` 直调面板内 `runAi`、不经 SettingsView 的 `aiRunningKey`，右栏行无 running 视觉——弹窗化后生成卡自带 loading，可接受，不改。

### D5 非右栏出稿口全部收编（评审 P0-1 处置）

- 主线第三问行内「AI 帮我填」（tone）：结果进文本卡（`StoryArcForm` 的 tone 分支改推弹窗），行内不再渲染输入框下方结果区；运行占位同步进弹窗。
- 世界格头快捷钮：与右栏共用 `runAi`，结果自然同走弹窗，无单独工作。
- 世界体检「AI 补」快捷链：见 D6。
- `AiSink.tsx` 与 `.ai-sink`/`.aiz-*`/`.ah-chip`/`.ans-act` CSS 家族退役（先 grep 确认消费者清零，口径含 D2 重挂清单）。
- `SettingsView` 各 `footNote` 与 `AiWriterAssistant` 行 `desc` 里「落在格下方/结果区/卡底/最近 5 次/切回」口径全部改「弹窗确认才写入」。

### D6 体检报告卡的三个交互链（评审 P1/P1-3 处置）

- **世界「AI 补」修补循环**：点「AI 补」＝关报告卡→开对应生成卡；生成卡采纳后**自动重开报告卡**（沿用上次 findings、该项标「已处理」；「重新检查」才整卡刷新重计费）——多缺口书循清单逐项补，不丢报告。伏笔埋坑体检的行跳转同构处理（跳转回来不自动重开，见下）。
- **伏笔报告行跳转 × Modal 焦点还原竞态**：Modal 关闭后 200ms 执行焦点还原（`Modal.tsx` lastFocus），会吃掉 `jumpToHook` 的 60ms 聚焦。处置＝AiCardModal 的跳转出口触发时**跳过焦点还原**（onClose 携带 skipRestore 语义，或 Modal 支持外部已移动焦点时不抢回）；e2e 的 `toBeFocused/toBeInViewport` 断言与该机制对齐。
- **世界报告卡跳转出口**（去补简介/去确认题材）：保留 `onGotoPanel` 出口（关弹窗→切面板；目标面板有脏编辑时走既有 dirty `window.confirm`）。
- 报告卡 findings 做面板 state 缓存（会话级）：重开体检报告卡先展示上次 findings（标「上次体检」），「重新检查」手动刷新——多缺口修补旅程不强迫重复计费。

### D7 文风 polish/fewshot 从直写改预览

`runAiByKey` 的 polish 分支：结果先进结构化卡（三区前后对照，新增渲染），确认才 `setRole/setRules/setCraft`＋回执；fewshot 同理（例句列表卡）。`style-quant` 蒸馏链零改动。

### D8 原型与 parity 口径

3 个 parity 原型（character-settings 19 处 / foreshadow-settings 18 处 / genre-signup 12 处）＋style-settings（8 处，未入 parity）里的 `.ai-sink` 演示块删除、改为右栏行触发态说明（**book.html 实测零命中，不在清单**）；ADJUSTMENTS.md 逐条登记（4 条）。弹窗本身不进 parity 截图（沿「应用侧扩展不进 parity」先例），验收走 e2e DOM 断言＋视觉走查截图。parity spec（ui-spec-parity）里量底色/几何的 evaluate 断言深绑 `.settings-v .ai-sink`，属**重写**而非改选择器。

### D9 生成中关闭的保护口径（评审 P0-2 处置）

生成中（running 态）允许关闭弹窗（Esc/遮罩/X 均不拦）；**最近一次已返回的结果缓存在面板 state**，重开同一能力行直接展示缓存（不再发请求、不重复计 usage），「换一个」才重新生成——沿 CastReviewModal「误关重开还是同一批，不会重复生成花钱」先例。生成**尚未返回**即关闭＝放弃该次结果（在途响应丢弃，不弹挽留、不写回）。缓存生命周期＝面板级（切面板即卸载清空，与 sinks state 现状同寿命）；确认写回或「换一个」成功后覆盖。

### D10 AiCardModal 组件边界

复活 `AISuggestionModal` 为文本卡底座（loading/换一个/接受这个骨架已有，补「关闭」常驻与版数位）；AiCardModal 只拥有：卡形 footer 分发、三态（空/载/错）骨架、skipRestore 出口、version 计数显示。内容渲染（结构化卡各域行）由调用方以 children 传入——各域私有渲染不上升公共层。

## Risks / Trade-offs

- **回归面大且三类异质**（评审 P1-4 口径修正）：单测约 8 个文件真命中（AiSink/GenreSettingForm/WorldSettingPanel/StoryArcForm/SettingsView.introHandle/CharacterManager.bootstrap/StyleSettingForm 相关/AiWriterAssistant；grep 命中的另 6+ 个写作域测试不受影响）；e2e 11 spec 分三类——**删除**历史切回用例（story-arc/genre-ai-settings/world-settings 的「最近 5 次」段）、**重写**弹窗断言、**重写** parity evaluate 断言。缓解：tasks 按类列清单，每批跑对应 spec；`data-aiact` 行锚点不动。
- **丢多稿并排比对**（D3）：版数计数＋旧版保留降一档损失；接受。
- **弹窗遮挡表单**：确认前看不到被覆盖的原值。缓解：文本卡带前后对照、结构化卡逐格 diff 标注将写值；「采纳 · 覆盖/合并」文案在卡内注明覆盖/合并语义。
- **AiCheckModal 形状是「打开即跑」**，设定域多为「点击行→出结果」。两者时序不同：设定域卡先 running 后 result，报告卡复用其 footer/列表渲染思想而非其自动 effect。
- **焦点还原竞态**（D6）：若 skipRestore 机制实现有偏差，伏笔跳转聚焦会间歇失效——e2e 有 focused 断言兜底。
