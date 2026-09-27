# c-og-rail-declutter — 章工作台收敛：章纲统计上移头部＋排版 seg 退役＋版本历史/归档迁位

## Why

用户 2026-09-27 拍板四条（对运行中的产品直接下口径）：章纲的门槛数据是「这一章能不能归档」的事，
不该藏在右栏 AI 助手里；写作时真正高频看的统计应该贴着章标题；字号/行距切换占着头部一行却极少用
（账号菜单「本书偏好」早有同套设置）；版本历史和归档是低频操作，收在头部右侧让头部右侧常年挂着
三个用不到的按钮。四条合起来＝把「看的信息」上移到视线起点、把「用的操作」收进对应页签。

## What Changes

- 右栏「AI 辅助」**章纲页签统计卡退役**：归档门槛／计划字数／剧情／出场角色四项上移中栏头部
  `.e-meta` 徽章行（与既有「状态＋字数」同排）；右栏章纲页签只剩引导语＋「还缺」清单＋动作清单
  ＋「AI 帮写剧情」。`OgStats` 数据通道保留（reqOk→操作页签统计卡、planWords→正文页签统计卡、
  missingLabels→还缺清单与「补全缺失字段」禁用态）。
- 头部**字号/行距 seg 退役**（小/中/大、紧凑/舒适/宽松）：改值唯一入口＝账号菜单「本书偏好」
  （`pref.book.{pid}.*` 数据层不动）；工作台对既有偏好只读回显（`ProsePane` 排版不变）。
- **版本历史迁位**：头部右侧 → 页签条右端（`.ch-history`，`margin-left:auto`；`HistoryModal` 弹窗不变）。
- **归档迁位**：头部右侧「归档本章」→「操作」页签首卡（`ArchiveModal` 与守卫不变：已归档/空章
  置灰并带说明 title）；旧稿支线章 SHALL NOT 渲染归档卡（与重写/回退卡同口径——支线无归档语义）。
- **e2e 适配（同批）**：四处按名字点「归档本章」的用例加「点操作页签」一步；四处 `S_API` 硬编码
  改吃 `E2E_S_API` env（沿用 ai-assist/chapter-plan 既有约定，隔离栈端口可注入）。
- `ADJUSTMENTS.md` 登记与 `book.html` 原型的偏差；workbench parity 基线待原型同批更新后重录
  （design:check 为本地门禁，不在 CI）。

**非目标**：原型 `book.html` 头部的同步改版（待下次原型同批更新）；其余页签右栏统计卡（正文/
提示词/设定/文风/关系/伏笔/操作维持现状）；`VolumeWorkspace` 头部。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 右栏「AI 辅助」面板章纲页签统计卡退役（还缺清单与头部「归档门槛」徽章同源）；头部
  e-head 徽章行扩为状态＋章纲统计六枚；排版 seg 退役（偏好只读回显）；版本历史移页签条右端；
  归档移「操作」页签首卡（守卫不变，旧稿支线不渲染）。

## Impact

- **前端**：`components/novel/workbench/AiAssistPanel.tsx`（og 页签撤 raStats）、`ChapterWorkspace.tsx`
  （e-meta 四徽章、seg 退役、`typo` 单一 state 只读回显、ch-tabs 右端版本历史钮、操作页签归档卡）、
  `design/book.css`（`.ch-tabs .ch-history` 两条）。
- **测试**：vitest（`AiAssistPanel.test.tsx` og 用例改断言无统计卡、`chapterWorkspace.plotFlow.test.tsx`
  新增头部 meta 行用例）；e2e（`settings-forms` / `free-writing-flow` / `chapter-rewrite` / `modals-pr5`
  归档路径加页签一步＋`S_API` env 化）。
- **门禁**：tsc、vitest 871、build、design:lint、隔离栈目标 e2e 27 条、工作台双截图目检——全绿
  （PR #506，squash=98f4cff8）。
- **数据**：零数据面改动（无 API/存储/提示词变化），纯界面重组。
