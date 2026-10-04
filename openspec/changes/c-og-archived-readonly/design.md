# Design: c-og-archived-readonly

## 决策 1：动作区「不在场」而非「禁用」

归档章章纲动作区四个按钮（撤回确认/去写正文/确认章纲/编辑章纲）全属变更类动作。两个既有先例分流：

- AI 面板动作（AiAssistPanel）：**禁用＋「本章已归档」hint**——那些动作是「章纲内容加工」，卡片行自带 hint 位。
- 正文页签：**只读＋横幅指路**——归档语义下没有可点的动作，横幅（`.readonly-banner`）承担解释与出口。

章纲动作区与正文同性质（归档后无可为之事），且四个按钮全禁用＝一排死按钮挤在 ol-top。取正文口径：整排不提供＋横幅。

## 决策 2：横幅在工作台层共用，OgPane 只管收敛

`.readonly-banner` 原挂在 ChapterWorkspace 的 prose 分支（在 ProsePane 之上、工作台主列内，全宽横贯）。提取为 `archivedBanner` JSX 常量（含「恢复编辑」按钮，走既有 `handleUnarchive`——自带 confirm 弹窗），`chTab === "og"` 同挂。OgPane 内部不感知横幅，只按 `archived` 收敛自身（恒查看态＋动作区不提供）——横幅样式/文案若将来调整只动一处。

## 决策 3：编辑入口双层哑火（表现层兜底＋状态层短路）

- 表现层：OgPane 门改 `if (!editing || archived)`——归档前正停在编辑态（ogEditing=true 残留）也不渲染表单。
- 状态层：`startOgEdit`／`editAndFlash` 对归档章短路——缺口 chip／剧情抽卡「去补填」/右栏补全回填等入口不再把 ogEditing 立起来。只做表现层的话，ogEditing 残留会在「恢复编辑」后突然弹出一份额知之外的表单；双层保持状态与所见一致。

## 决策 4：徽标不动

页签条「草稿/已确认」徽与 panel-head 徽继续如实反映章纲 status（#639 修的就是徽标把归档章计入确认数——徽标是信息，动作区是入口；信息照给，入口按归档态收敛）。
