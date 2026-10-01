## Context

「AI 帮写剧情」＝右栏章纲页签的三版抽卡行（chapter-plot-items 5.4 落地）。名字被两条 capability 的 requirement 逐字钉住（workbench「右栏动作」、chapter-plot-items「三版抽卡」「发起门槛」）；行序无 spec 钉、只存在于 `AiAssistPanel` 的 rows 数组与 `book.html` 原型 DOM 顺序。弹层（PlotDrawModal）与 e2e 定位器（`og-plot-draw` testid）均不含旧文案。

## Goals / Non-Goals

**Goals:**
- 可见文案「AI 帮写剧情」→「剧情抽卡」（行名；行描述/testid/链路/门槛判据零变化）。
- 章纲页签动作行重排：剧情抽卡第 1、盘点出场人物第 2，其余（剧情推演/补全缺失字段/与卷纲冲突检测）排后。
- spec 三条 requirement 同批更名，动作行排序首次入 spec（workbench 增排序 bullet＋场景）。

**Non-Goals:**
- 不改 PlotDrawModal 弹层内文案（本就无旧名）；不改后端（动作无独立端点，走 `chapter_plot_fill` 族）；不动盘点行命名（「盘点出场人物」维持既有）。

## Decisions

- **行描述不改**：「一次给 3 版剧情挑一版；要求概要、挑战、章末落点已填（手写剧情全免费）」与「抽卡」词义自洽，不动。
- **排序入 spec**：用户拍板的行序是持续有效的产品决策，workbench requirement 补排序 bullet＋场景钉住（此前无 spec 钉，属新增约束而非改约束）。
- **testid `og-plot-draw` 不改**：内部锚点与视觉文案解耦，改 testid 会连坐 e2e/打点，零收益。

## Risks / Trade-offs

- 按名断言的两处单测（castReviewRail 免费/PRO 两用例）需同批改名，避免存量红。
- `railChapter` 在 parity 页集：行序与文案两侧同批，像素基线自然对齐（workbench 屏现存通知横幅漂移存量红与本改无关）。
