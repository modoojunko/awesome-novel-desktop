## Why

章纲页右栏「AI 助手 · 章纲」的「AI 起草」与其他功能重复：卷纲「拆章」已按卷纲＋设定产出章纲四段（挑战/阶段/概要/落点）直接排上，「补全缺失字段」又能按缺口清单补齐其余格子——整份起草的产出物被这两条链路覆盖，单独维护一套素材包（主线卡/世界观全量/全人物/伏笔块）与提示词模板只为一条重复入口，成本大于价值。2026-10-01 用户拍板撤掉。

## What Changes

- 撤掉右栏「AI 助手 · 章纲」的「AI 起草」能力行（`og-ai-draft`）——章纲页签动作区从六行变五行（剧情推演/补全缺失字段/AI 帮写剧情/盘点出场人物/与卷纲冲突检测）。
- **BREAKING**（本地单用户应用、无存量 API 消费方）：撤掉后端 `POST /novels/{id}/chapters/{ref}/outline/ai-draft` 端点与起草专属代码（素材组装、草稿清洗、`outline_draft` 提示词模板）；`outline/ai-draft` 家族里的 `fill-gaps` 端点原样保留。
- 撤掉「AI 起草覆盖确认判定」`ogHasDraftContent`（唯一消费方是起草入口；「有现有章纲」的后端判定只服务起草素材包，一并退役）。
- 章纲「确认/撤回确认」「保存草稿不自动确认」链路不受影响（c-og-draft-no-autconfirm 的成果是通用保存链语义，不随起草退役）。
- 「补全缺失字段」「AI 帮写剧情」「剧情推演」「盘点出场人物」「与卷纲冲突检测」五行零改动。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `outline-ai-draft`：REMOVED——「章纲 AI 起草端点」「草稿不落库」「素材汇集」「输出校验与兜底」「用量计量」五条 requirement 随功能退役；「章纲缺项补全端点（fill-gaps）」保留（能力延续，capability 名不变）。
- `workbench`：REMOVED「章纲面板 AI 起草入口」requirement；MODIFIED「章纲页签查看/编辑两态」——「AI 起草」成功回填进编辑态的半句与场景退役，「补全缺失字段」回填进编辑态保留。
- `chapter-data`：MODIFIED「章档案新增列的持久化与导出（加键兼容）」——两列消费链路第 ① 项（「有现有章纲」判定，见 outline-ai-draft 素材汇集）随判定退役删除；第 ② 项（写正文素材含挑战/阶段两块）保留。
- 其余 spec 中的「AI 起草」字样为退役后残句，不动 requirement 语义、不加 delta，归档 sync 时顺手扫净：`chapter-cast-review`（「SHALL NOT 随保存或 AI 起草自动跑」——「随保存不自动跑」约束仍成立）、`volume-plan-ai`（「与章纲 AI 起草的主线空门同口径」——主线空门行为不变，仅 cross-ref 失效）。

## Impact

- 前端（`client/frontend`）：`AiAssistPanel.tsx`（撤行＋撤 props）、`Rail.tsx`（撤透传）、`ChapterWorkspace.tsx`（撤 handler/state/railData 字段）、`chapterForm.ts`（撤 `ogHasDraftContent`）、`lib/ai.ts`（撤 `draftOutline`）；单测四文件更新＋`e2e/outline-ai-draft.spec.ts` 整删。
- 后端（`client/backend`）：`chapters/ai_draft.py` 撤 `/ai-draft` 端点与 `_sanitize_draft`/`_arc_markdown`/`_existing_outline_markdown`/`_clamp_word_target`/`_str_list`（模块保留服务 fill-gaps）；`prompts/outline_draft.prompt` 删除；`tests/test_outline_ai_draft.py` 整删；`tests/test_story_arc.py` 撤 `_arc_markdown` 镜像回归（premise 镜像本身另有存储层回归钉着）。
- 原型（`docs/design-c/prototypes/book.html`）：右栏章选卡撤「AI 起草」行，ADJUSTMENTS.md 登记。
- 门禁：C端 `tsc --noEmit`／vitest 相关文件／`design:lint`／后端 pytest 相关文件；不触两端共享段（无样式新增，只撤一个 DOM 行）。

## Design Impact

- 受影响端：仅 C端。
- 受影响屏/弹层清单：写作工作台 book 屏右栏「AI 助手 · 章纲」卡（章选态）——撤一行能力行；其余页签右栏卡、中栏、弹层零改动。
- 用到/新增的对象状态：无新增——纯撤一个能力行（ra-step），不新增/不改变任何状态档位、胶囊形态、提示语气；running 态撤掉 `draft` 键（「生成中…」行标随行退役）。
- 是否触碰两端共享段：否（无样式改动，`ra-step` 行为既有词汇复用）。
- 是否需要原型先行：需要——`book.html` 右栏章选卡同批撤行＋ADJUSTMENTS.md 登记偏差原因；`railChapter` 在 parity 页集内，原型与实现同批撤行后像素基线自然对齐。
- 设计工件由谁产出：实现侧自查（撤行无新视觉词汇）。
