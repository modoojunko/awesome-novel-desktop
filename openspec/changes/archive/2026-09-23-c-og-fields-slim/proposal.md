# c-og-fields-slim — 章纲必填瘦身：核心任务／读者当前状态退役，归档门槛六项改四项

## Why

拆章五段（剧情/挑战/结尾/行动/阶段）已直接进正文提示词并各占专属提示块，而章纲六项必填里的「核心任务」在写正文链路中**没有任何消费点**（语义被「本章剧情（目标→阻碍→结果）」＋「必须完成的变化」完全覆盖），「读者当前状态」同样没有独立提示词块（其功能被上章衔接块：上章结尾情绪＋章末钩子＋读者期待缺口覆盖得更好）。两者却位列归档门槛必填，不填不让归档——对作者是纯负担。当前零用户，是干净拆除的窗口。

## What Changes

- **BREAKING**「核心任务」（`memo.current_task`，DB 列 `chapters.current_task`）退役：章纲表单删格、归档门槛不再查、AI 体检/推演/起草补缺链不再读写；**DB 列保留但停读写**（SQLite 无迁移链，列留存无害）。
- **BREAKING**「读者当前状态」（`memo.reader_expectation.state`，DB 列 `chapters.expectation_state`）退役：同上处理；「预期策略（strategy）＋读者预期补充（detail）」保留，期待缺口链路不变。
- 归档门槛**六项 → 四项**：预期策略、必须完成的变化、主情绪、段落规划（前端 OgForm 门槛与后端 `workflow/gates.py` 同步）。
- 落点卡文案同步：「还差 6 项才能开写：核心任务、读者当前状态、…」→「还差 4 项才能开写：预期策略、必须完成的变化、主情绪、段落规划」；「补这 6 项，开始写」→「补这 4 项，开始写」。
- AI 起草/补缺白名单（`_FILLABLE_KEYS` 与前端 `GAP_TO_FILL_KEY`）移除 `current_task`/`state`；起草响应骨架不再要求核心任务。
- plot_sim 推演素材与回落链移除核心任务（关键事件缺失直接回落固定句）。
- 原型 `book.html` 章纲折叠组同批删「核心任务／读者当前状态」两组，ADJUSTMENTS 登记；design:check 基线受影响时按管线重录。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 章纲表单折叠组删「核心任务／读者当前状态」；「已有内容二次确认」的格子枚举同步；归档门槛必填六项改四项。
- `chapter-plan-ai`: 落点卡「还差 6 项／补这 6 项」改 4 项并删两项名目；「六项必填」措辞改四项。
- `plot-sim`: 推演素材清单去核心任务；关键事件缺失的回落链改「直接回落固定句」。
- `outline-ai-draft`: 起草响应备忘骨架去核心任务；「缺必备骨架」判据改（段落规划为空即可 502）；补缺白名单去核心任务/读者当前状态；「章纲六项必填」措辞改四项。
- `chapter-data`: `current_task`/`expectation_state` 两列转「只留不读写」退役态（持久化 requirement 措辞收窄）。
