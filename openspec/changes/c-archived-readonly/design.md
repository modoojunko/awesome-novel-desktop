# Design: c-archived-readonly

## 决策 1：章纲动作区「不在场」而非「禁用」

归档章章纲动作区四个按钮（撤回确认/去写正文/确认章纲/编辑章纲）全属变更类动作。两个既有先例分流：

- AI 面板动作（AiAssistPanel）：**禁用＋「本章已归档」hint**——那些动作是「章纲内容加工」，卡片行自带 hint 位。
- 正文页签：**只读＋横幅指路**——归档语义下没有可点的动作，横幅（`.readonly-banner`）承担解释与出口。

章纲动作区与正文同性质（归档后无可为之事），且四个按钮全禁用＝一排死按钮挤在 ol-top。取正文口径：整排不提供＋横幅。右栏写入行（生成正文/续写建议）则反之取「禁用＋hint」——它们本就是能力行布局，hint 位现成。

## 决策 2：横幅在工作台层共用；「恢复编辑」按钮退役

`.readonly-banner` 原挂在 ChapterWorkspace 的 prose 分支（ProsePane 之上、工作台主列内，全宽横贯），提取为 `archivedBanner` 常量两页签同挂。原款横幅带「恢复编辑」按钮（直接 `store.unarchive()`）——按新规则（唯一路径＝重写本章）按钮退役：绕开重写的旧稿转存与下游「基于旧设定」安全网。横幅文案改指路「请在『操作』页签使用『重写本章』（旧稿自动转存支线）」，`handleUnarchive` 与 railData 的 `unarchive` 上抛随删。OgPane 内部不感知横幅，只按 `archived` 收敛自身。

## 决策 3：编辑入口双层哑火（表现层兜底＋状态层短路）

- 表现层：OgPane 门改 `if (!editing || archived)`——归档前正停在编辑态（ogEditing=true 残留）也不渲染表单。
- 状态层：`startOgEdit`／`editAndFlash` 对归档章短路——缺口 chip／剧情抽卡「去补填」/右栏补全回填等入口不再把 ogEditing 立起来。只做表现层的话，ogEditing 残留会在重写解锁后突然弹出一份额知之外的表单；双层保持状态与所见一致。

## 决策 4：「解除只读」解锁链整体退役

解锁链（NovelWorkspace `requestAi` 归档分支 → UnlockModal → `unarchive()` → 续跑写入）的设计前提是「归档章可经确认解锁」。新规则下该前提不成立：AiAssistPanel 的写入行归档即禁用＋hint，链路没有触发点；`requestAi` 归档分支降级为兜底 toast 指路重写。`UnlockModal` 组件、`pendingAiRef`/`showUnlock` 状态、`useChapterData.unarchive`（零消费者）一并删除。后端 `/unarchive` 端点保留：重写事务在服务端内部完成解锁，历史数据合法。

## 决策 5：版本历史恢复保留（明确不在本 change 范围）

归档确认弹窗明文承诺「仍可在版本历史中查看与恢复」——版本恢复是内容找回通道（恢复旧版后可重新归档），不是进编辑态的入口，与「重写本章」互补。如需把它也收进「仅重写」，另立 change（会连带改归档确认弹窗文案与 HistoryModal 守卫）。

## 决策 6：徽标不动

页签条「草稿/已确认」徽与 panel-head 徽继续如实反映章纲 status（#639 修的就是徽标把归档章计入确认数——徽标是信息，动作区是入口；信息照给，入口按归档态收敛）。
