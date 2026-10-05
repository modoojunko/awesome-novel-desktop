# Design: 章工作台密度重排

## Context

三方评审（PM/UX/前端实勘）收敛的三刀方案，演示页 /tmp/workbench-proposal.html 为像素与交互基准。前端实勘落点：

- 徽章行 `ChapterWorkspace.tsx:1091-1102`（.e-meta）：计划字数/完成度/本书总字数三枚 pill 的数据源 planWords/progressPct/bookWords 保留（页签行与续写块要复用）。
- 完工横幅 `ProsePane.tsx:688-746`（qc-banner，两态都渲染）；编辑工具行 `ProsePane.tsx:764-806`（.ol-top.edit-bar，仅编辑态）。
- 三张置灰卡 `AiAssistPanel.tsx:421-446`（cap() 构造，hasSelection 来自 ProsePane 选区链上抛）。
- 列宽 `book.css:69`（1fr 236px）；916-918 的 236px 是设定域 char-list，不动。
- 续写链 `ProsePane` continueWriting→startStream(true)；常驻达标判定不能复用 qcReport（仅生成后有值），前端以 words < target*0.9 现算。

## Goals / Non-Goals

**Goals:** 正文首行上移约 90-110px；右栏卡片单行化；字数信息三处收敛为两处（页签行＋工具行胶囊）；续写动线落到视线终点。

**Non-Goals:** 不动 680 版心；不动 #506-519 的统计上移决策本体（只挤水分）；不做沉浸模式开关；不做 ≥1600px 边注轨；不动设定域 char-list 的 236px；章纲/操作等其它页签的头部结构不动（徽章行收敛天然全页签生效，属同一信息源收敛）。

## Decisions

1. **完工检查的语义收缩登记为有意行为**：横幅从两态常显收缩为编辑态胶囊。理由：qc 数据服务「写作中的人」（补字数、改自查），查看态读者不是受众；根治其「知道了」不记忆状态的噪音问题。qc-word/qc-self testid 迁到胶囊展开区保留，e2e 同批改定位。
2. **叙事自查明细用胶囊就地展开，不用弹窗**：明细是低频参考信息，弹窗打断写作流；展开区渲染在工具行下方（详情条），再点收起。
3. **文末续写块判定走纯前端**：`words < target*0.9`（target=章纲 wt→store.targetWords 兜底），不依赖 qcReport；流式进行中隐藏（生成本身在文末写入，块会挡视线），生成结束重算。续写块点「续写」调 continueWriting()（无选区=文末），与右栏同链。
4. **段落加工分组只折正文页签的行集合**：AiAssistPanel 按 rows 数组渲染，分组逻辑放 rows 构造处（cap() 三行未选中时替换为分组头单行），其它页签行集合不含这三行、天然不受影响。分组头也带 testid（ai-para-group），展开后三卡 testid 不变（ai-polish 等由 key 派生）。
5. **列宽只动 grid 一处＋.col-ai 内部无硬编码**：236px 仅出现在 book.css:69 的 grid 定义（916 的属设定域），改 300px 无连带。窄屏 <1024px 的 media query 隐藏整栏，无需改。

## Risks / Trade-offs

- [e2e prompt-pipeline 190/195 点 ai-polish 前无选区] → 该用例流在点击前本就先选中段落（润色稿链路）；实跑确认，若折叠导致定位失败则同批补选中步骤。
- [折叠态下三张置灰卡的 PRO 曝光减弱] → 分组头常显（含「先在正文选中一段」提示），曝光从 3 卡降为 1 行；演示页已按此呈现且用户拍板。
- [查看态丢失完工横幅] → 登记为有意收缩（见决策 1）；归档门槛等静态信息仍在徽章行。
- [.ol-top 是 flex、hidden 属性会被压掉的存量坑] → 新增警示胶囊与详情条一律条件渲染，不用 hidden 属性。

## Migration Plan

纯前端，随下版发布；回滚 revert 单批提交。

## Open Questions

（无）
