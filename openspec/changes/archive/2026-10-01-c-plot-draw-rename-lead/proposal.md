## Why

右栏章纲页签的动作行信息架构需要两句拍板（2026-10-01 用户）：①「AI 帮写剧情」改名「剧情抽卡」——「抽卡」是这套三选一交互在拆章/人物方向上已建立的统一词汇，剧情行沿用后右栏动词词汇归一；②行序调整——作者进章纲页签最高频的动作是给剧情出候选（抽卡）与盘人，「剧情抽卡」提到第 1、「盘点出场人物」提到第 2，推演/补全/冲突检测次之。

## What Changes

- 右栏章纲页签「AI 帮写剧情」行改名「剧情抽卡」（行描述、testid `og-plot-draw`、链路与门槛三要素判据全部不变）。
- 章纲页签动作行重排：①剧情抽卡 → ②盘点出场人物 → ③剧情推演 → ④补全缺失字段 → ⑤与卷纲冲突检测（仅顺序，行内容零变化）。
- spec 逐字钉名的三条 requirement 同批改写（workbench「右栏动作」、chapter-plot-items「三版抽卡」「发起门槛」）；行序无 spec 钉，不加 delta。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-plot-items`：MODIFIED「PRO「AI 帮写剧情」三版抽卡」→ 更名「PRO「剧情抽卡」三版抽卡」并替换 requirement 内四处动作名；MODIFIED「发起门槛与已润色章提示」→ 门槛主句与拦截场景的动作名同步。
- `workbench`：MODIFIED「右栏「AI 帮写剧情」动作」→ 更名「右栏「剧情抽卡」动作」，正文与场景的动作名同步。

## Impact

- 前端：`AiAssistPanel.tsx`（行名＋rows 数组顺序）、注释同步三处（Rail/ChapterWorkspace/plotTool 测试头）；`castReviewRail.test.tsx` 两处按名断言改名。
- 原型：`book.html` 右栏章选卡行改名＋重排（`railChapter` 在 parity 页集，原型与实现同批）。
- e2e：`plot.spec.ts` 定位器全走 `og-plot-draw` testid，不受力；仅头注释措辞顺带更新。
- 门禁：C端 `tsc --noEmit`／vitest 相关文件／`design:lint`／`openspec validate --strict`；零样式改动。

## Design Impact

- 受影响端：仅 C端。
- 受影响屏/弹层清单：写作工作台 book 屏右栏「AI 助手 · 章纲」卡（章选态）——一行改名＋行序调整；弹层零改动（PlotDrawModal 无旧文案）。
- 用到/新增的对象状态：无新增——纯文案与排序，不新增/不改变状态档位、胶囊形态、提示语气。
- 是否触碰两端共享段：否。
- 是否需要原型先行：需要——`book.html` 同批改名＋重排＋ADJUSTMENTS.md 登记。
- 设计工件由谁产出：实现侧自查（复用既有 ra-step 词汇，零新视觉词汇）。
