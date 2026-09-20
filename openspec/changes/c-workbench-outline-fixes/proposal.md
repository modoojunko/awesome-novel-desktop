# Proposal: c-workbench-outline-fixes

## Why

写作工作台（book 屏）2026-09-19 GUI 走查（docs/qa-night-2026-09-19.md Bug8 同族）+ 本地实勘发现三处缺陷：顶栏「写作 N/M 章纲」计数在删章/删卷后停留在旧值，与左树自相矛盾（实勘：DB 0 章、`/tree` 实时返回 0 章，顶栏仍显示 0/10——`useWorkbench.deleteNode` 只刷新左树数据源，不刷新计数数据源）；卷纲表单「章数目标」字段在 160px 窄列内标签与提示双双折行（标签被折成「章数目／标」），输入框与左列「结构模板」下拉错位；左树底部「确认全部已填章节」在全书 0 章时仍可点击，点了空转一轮再弹「没有可确认的章节」。

> 2026-09-19 收窄：②（章数目标布局）移交 c-volume-view-storyline——其卷纲编辑表单按 storyline.html 重做并承载同款布局口径，本 change 仅保留 ①③。

## What Changes

- **顶栏章纲计数与树一致**：删章、删卷等树变更路径补刷新计数数据源（`useOutline.refetchTree`），保证顶栏「写作 N/M 章纲」在确认/删除/加卷/加章/归档后与左树、与 DB 一致（含 qa-night Bug8 场景：逐章确认后计数随之增长，而非全程 0/N）。
- **「确认全部已填章节」空态禁用**：全书无可确认章（0 章或全部已确认/已归档）时按钮禁用；禁用态文案提示不改（title 说明原因）。

~~「章数目标」字段排版修复~~（2026-09-19 移交 c-volume-view-storyline，见上）。不在本次范围：卷纲右栏「AI 辅助 · 大纲」三张「规划中」卡的实装与文案视角改写（产品立项另行 propose）。

## Capabilities

### Modified Capabilities

- **workbench** —— 新增两条行为需求：①写作 N/M 章纲计数一致性（树变更后同步）；③「确认全部已填章节」空态禁用。（原 ②「章数目标」字段布局已移交 c-volume-view-storyline，随其卷纲编辑表单落地。）

## Impact

- **代码（C端 client/frontend）**：
  - `src/hooks/useWorkbench.ts`（deleteNode 后的刷新联动）与 `src/components/novel/workbench/OutlineTree.tsx`（删除确认回调、批量确认按钮禁用态）
  - 顶栏计数渲染在 `src/components/novel/NovelWorkspace.tsx`（modnav），行为随数据源修复自动纠正，无结构改动
- **原型（设计事实源，先行）**：`docs/design-c/prototypes/book.html`（批量确认按钮禁用态演示）＋ `ADJUSTMENTS.md` 登记
- **测试**：C端 vitest 组件测试（计数联动、按钮禁用态）；e2e 现无这两处断言，补最小覆盖
- **不触碰**：两端共享段（base.css 令牌与基础组件类）——仅 book.css 业务层与 workbench 组件；S端 无涉及

## Design Impact

- 受影响端：**仅 C端**（client/frontend + book.html 原型）。S端 无涉及、不触两端共享段（不改 base.css 令牌/基础组件类，改动落在业务层 book.css 与 workbench 组件）。
- 受影响屏/弹层：book 屏（写作工作台）——左树（批量确认按钮禁用态）、顶栏 modnav（计数行为修复，无视觉改动）；删除确认弹层行为不变（仅回调补刷）。
- 对象状态（对照 design-language §5 状态语言总表）：按钮新增**禁用态**（btn-ghost + disabled，既有禁用语言，无新档位）；无新增组件词汇、无第四种胶囊形态、语气词仍限 info/ok/warn/err。
- 是否需要原型先行：**需要**（用户可见界面改动）——book.html 先改，ADJUSTMENTS.md 登记批量确认禁用态；顶栏计数为纯行为修复，无原型改动。
- 设计工件由谁产出：实现侧自查（无新视觉形态，均为既有语言的重排与状态启用）。
