# Proposal: c-og-archived-readonly

## Why

已归档章的章纲页签仍渲染整套动作区（撤回确认／去写正文／确认章纲／编辑章纲）。后端自 #639（c-og-badge-archived-confirm）起对归档章 confirm/unconfirm 恒 409——状态机守卫：归档章被确认会把 status 翻成 confirmed 而 archived_at 残留，章静默掉出归档态。于是这些按钮在归档章上点了只会吃 409 报错：真机截图（2026-10-04）里归档章章纲仍是「草稿」徽＋可点的「确认章纲」。正文页签（readonly-banner＋编辑器只读）与文风页签（影子编辑禁用）都有归档只读口径，章纲页签是唯一漏网。

## What Changes

- `client/frontend/src/components/novel/workbench/OgPane.tsx`：新增 `archived` prop——归档章恒走查看态（归档前残留的编辑态也不渲染表单），查看态动作区（撤回确认／去写正文／确认章纲／编辑章纲）整排不提供；一页纸本体与徽标照旧只读呈现。
- `client/frontend/src/components/novel/workbench/ChapterWorkspace.tsx`：归档只读横幅（`.readonly-banner`，正文页签原款：锁图标＋「本章已归档 · 只读」文案＋「恢复编辑」出口）提取为两页签共用，章纲页签同挂；`startOgEdit`／`editAndFlash` 对归档章短路（查看态缺口 chip／剧情抽卡「去补填」等编辑入口不得把归档章带进编辑态）。
- 测试：vitest 单测（OgPane 归档恒查看态＋动作区不在场）＋集成（ChapterWorkspace 归档章横幅在场、四入口不在场、chip 哑火）＋e2e 搭车 free-writing-flow ⑥ 归档流（章纲页签横幅＋恢复编辑在场、确认章纲/编辑章纲不在场）。
- spec delta：workbench「章纲页签查看/编辑两态」MODIFIED——补归档章恒只读条款与场景，其余 SHALL 与既有 7 个场景零改动。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 「章纲页签查看/编辑两态」补归档章条款：恒查看态＋动作区不提供＋归档只读横幅（含「恢复编辑」出口）＋编辑入口哑火。本条是「查看态 SHALL 提供『编辑章纲』入口」与「查看态 SHALL 保留确认章纲/去写正文」两款的归档例外；既有场景零改动，新增归档场景一条。

## Impact

- **代码**（全部 C端 前端，无后端改动、无 CSS 改动——横幅复用既有 `.readonly-banner` 类）：
  - `OgPane.tsx`：`archived` prop＋恒查看态门＋动作区条件渲染。
  - `ChapterWorkspace.tsx`：`archivedBanner` 提取共用＋OgPane 接线＋`startOgEdit`/`editAndFlash` 归档短路。
- **测试**：`ogPane.plotEdit.test.tsx`／`chapterWorkspace.plotFlow.test.tsx`／`e2e/free-writing-flow.spec.ts`。
- **不改动**：后端 confirm/unconfirm（#639 守卫已在，前端收敛纯表现层）；文风/正文页签的既有归档只读语义；页签条与 panel-head 的章纲状态徽（草稿/已确认继续如实反映章纲状态——信息不撒谎，只撤不存在的动作入口）。

## Design Impact

- **受影响端**：仅 C端。
- **受影响屏/弹层**：写作视图章工作台——章纲页签（横幅＋动作区收敛）；不涉弹层（「恢复编辑」沿用 handleUnarchive 既有 confirm 弹窗）。
- **对象状态**：复用既有「已归档」只读态语言（正文页签横幅同款），不新增状态档位、不新增胶囊；动作区处置取「不在场」而非「禁用」，与正文页签归档口径一致（归档＝只读＋横幅指路，不留一排禁用死按钮）。
- **文案口径（§13）**：横幅文案逐字复用正文页签原款（含恢复路径指路），零新按钮词；无内部术语。
- **两端共享段**：不触碰（无 CSS/令牌改动，不需要 design-cross）。
