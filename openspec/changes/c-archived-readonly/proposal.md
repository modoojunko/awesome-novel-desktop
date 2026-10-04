# Proposal: c-archived-readonly

## Why

已归档章仍有多条进编辑态的旁路，与「归档＝定稿只读」的产品语义冲突（用户 2026-10-04 拍板：归档章除「重写本章」外不应再有编辑入口）：

1. **章纲页签动作区不看归档态**：撤回确认／去写正文／确认章纲／编辑章纲照常渲染。后端自 #639 起对归档章 confirm/unconfirm 恒 409（状态机守卫：归档章被确认会把 status 翻成 confirmed 而 archived_at 残留），按钮点了只会吃 409——真机截图（2026-10-04）里归档章章纲仍是「草稿」徽＋可点的「确认章纲」。
2. **「解除只读」页面级解锁链**：归档章点右栏任意 AI 写入工具（生成正文/段落加工等；续写建议原同链、已随 #669 c-retire-continue-writing 退役）先弹「解除只读」，确认即 unarchive 并续跑写入——归档态被一条确认弹窗绕过。
3. **只读横幅自带「恢复编辑」按钮**：正文页签横幅（本 change 起章纲页签同挂）一键 unarchive，不走重写的旧稿转存与下游角标安全网。

「重写本章」是规格化的整体重写通道（旧稿自动转支线 `ghost_of` ＋下游「基于旧设定」角标）。拍板演化（同日三轮）：先收敛为「唯一路径＝重写本章」，随后补定**小改场景**——归档章应有显式解锁入口放开正文/章纲修改。最终规则：**归档章全面只读，修改呈两条路径——小改＝横幅「恢复编辑」（confirm 确认后 unarchive 直改，不转存旧稿）；整体重写＝「重写本章」（旧稿转支线＋下游角标）**；「解除只读」AI 写入旁路（点工具弹窗即解锁）不复保留。

## What Changes

- `OgPane.tsx`：新增 `archived` prop——归档章恒走查看态（归档前残留的编辑态也不渲染表单），查看态动作区整排不提供；一页纸本体与章纲状态徽照旧如实呈现。
- `ChapterWorkspace.tsx`：归档只读横幅（`.readonly-banner`）提取为正文/章纲两页签共用，承载两条修改路径——**「恢复编辑」按钮（小改：confirm 确认 → `store.unarchive()`，直改不转存旧稿）**＋整体重写指路「请在『操作』页签使用『重写本章』」；`startOgEdit`／`editAndFlash` 对归档章短路（缺口 chip／剧情抽卡「去补填」等编辑入口不得把归档章带进编辑态）；railData 的 `unarchive` 上抛随 AI 旁路退役删除（横幅直接用 `store.unarchive()`）。
- **「解除只读」解锁链退役**：`NovelWorkspace` 的 `requestAi` 归档分支从「弹 UnlockModal → unarchive → 续跑」改为兜底 toast「已归档 · 恢复编辑后可用」；`UnlockModal` 组件删除；`AiAssistPanel` 正文页签「生成正文」行归档章 `disabled`＋hint「已归档 · 恢复编辑后可用」（续写建议行已随 #669 退役，不在本 change 范围）。
- 测试：vitest 单测（OgPane 归档两态、AiAssistPanel 归档禁用行）＋集成（ChapterWorkspace 归档横幅两路径、动作区不在场、chip 哑火）＋e2e（free-writing-flow ⑥ 归档流搭车断言；modals-pr5 ② 由「解锁链」改写为「写入锁死＋恢复编辑解锁全链」）。
- spec delta：workbench 三处 MODIFIED——「章纲页签查看/编辑两态」（归档恒只读条款＋场景）、「右栏『AI 辅助』面板」（正文动作清单的解锁链表述改归档禁用＋hint）、「正文页签查看/编辑两态」（两路径条款＋「恢复编辑后落查看态」回归本义＋归档锁死场景）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 「章纲页签查看/编辑两态」补归档章恒只读条款（动作区不提供＋归档横幅两路径＋编辑入口哑火），为「查看态提供编辑章纲入口／保留确认与去写正文」两款的归档例外；「右栏『AI 辅助』面板」的正文动作清单首项语义由「走页面级解锁链」改为「归档禁用＋hint『恢复编辑后可用』、其余状态打开 AiModal」；「正文页签查看/编辑两态」的归档修改语义定为两路径（恢复编辑＝小改、重写本章＝整体重写）。「解除只读」AI 旁路退役。其余 SHALL 与既有场景零改动。

## Impact

- **代码**（全部 C端 前端，无后端改动、无 CSS 改动——横幅复用既有 `.readonly-banner` 类）：
  - `OgPane.tsx`／`ChapterWorkspace.tsx`：归档只读收敛＋横幅共用。
  - `NovelWorkspace.tsx`／`modals.tsx`：解锁链与 UnlockModal 退役。
  - `AiAssistPanel.tsx`：「生成正文」行归档禁用＋hint。
  - `Rail.tsx`：`RailChapterData.unarchive` 字段随 AI 旁路退役删除；`useChapterData.ts`：`unarchive` 方法保留（横幅「恢复编辑」出口专用）。
- **测试**：`ogPane.plotEdit.test.tsx`／`chapterWorkspace.plotFlow.test.tsx`／`AiAssistPanel.test.tsx`／`e2e/free-writing-flow.spec.ts`／`e2e/modals-pr5.spec.ts`。
- **不改动**：后端（#639 守卫已在；`/unarchive` 端点保留——「重写这一章」事务与历史数据仍合法）；「重写这一章」流程本身；归档确认弹窗明文承诺的**版本历史查看与恢复**（内容找回通道，非编辑态入口，如需收紧另立）；设定/角色关系/伏笔页签的归档提取确认流（归档管道本体）；文风页签既有影子编辑禁用；顶栏「续写」对已归档会话章落只读态的既有口径。

## Design Impact

- **受影响端**：仅 C端。
- **受影响屏/弹层**：写作视图章工作台——章纲/正文页签（横幅＋动作收敛）、右栏 AI 面板（写入行禁用）；「解除只读」弹层退役。
- **对象状态**：复用既有「已归档」只读态语言，不新增状态档位；处置取「不在场/禁用＋指路」二型——动作区整排不在场（随正文页签口径），右栏行禁用＋hint（随 AI 面板既有 hint 口径）。
- **文案口径（§13）**：横幅与 hint 均带可执行出口（「重写本章」＋所在页签）；零新按钮词、无内部术语。
- **两端共享段**：不触碰（无 CSS/令牌改动，不需要 design-cross）。
