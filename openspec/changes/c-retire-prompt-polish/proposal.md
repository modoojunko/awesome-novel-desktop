## Why

生成正文弹窗里的「AI 润色」是两段式提示词管线（ai-prompt-crafting）的第二段：确定性素材包 → 大模型润色成「成品提示词」→ 轻校验 → 覆盖写 write-prompt 行。产品实况（2026-10-08 用户拍板）：**程序组装的提示词已经达标，不需要再让大模型「添油加醋」**——同一次生成里先让大模型改写提示词、再让大模型写正文，既多烧一份 token，又可能把确定性素材改走形（润色产物还要靠条件锚校验兜底）。故整条「AI 润色」链退役：提示词只由「确定性组装 ＋ 作家编辑/存稿」产生。

## What Changes

- **后端**：退役 `POST /write/{chapter_ref}/prompt/polish` 端点、润色模板 `prompts/prompt_crafting.prompt`、润色产物轻校验 `validate_polished_prompt`（含 `_PLACEHOLDER_RE`）。保留：`_POLISH_ANCHORS`（三锚只剩存量行判型用途：`legacy_prompt_kind`/`should_refresh_stored_prompt`）、`strip_code_fences`（plot_sim/ai_check/ai_draft 共用，非润色专属）。
- **前端**：生成正文弹窗撤「AI 润色」按钮＋`polishing`/`polishError` 状态＋「重试润色」块＋两段式引导文案；徽标口径改「未润色/已润色」→「本次组装/本章已存稿」（存量行语义不变，`ai-raw-tag`/`ai-polished-tag` testid 保留）；`lib/ai.ts` 删 `polishWritePrompt`。
- **剧情改动软提示改出口**：章工作台原「提示词还是旧版、没带上新剧情——可以重新润色／去重新润色」→「可以刷新提示词／去刷新提示词」（原出口打开的就是本弹窗，弹窗内已无润色按钮，不改会成死路；刷新＝弹窗内「刷新提示词」按新剧情重组素材）。
- **明确不改**：素材包确定性组装与两路同源、存量稿优先（`GET /write/prompt` 与 `POST /write` 的存量行优先级）、「存为本章提示词」（`PUT prompts/write`）、「刷新提示词」（`GET ?fresh=1`）、阶段机推进（`outline→prompt→write` 由 `/write` 承载，润色端点原有的一次推进随之消失但路径不变）。
- **BREAKING**（对安装包 API 消费者）：`/api/novels/{pid}/chapters/{ref}/write/prompt/polish` 端点移除（无外部 API 消费者，桌面应用前后端同包发布）。
- **存量数据零迁移**：历史润色行原样只读，分级（`polished=true` / `legacy_kind="polished"`）不变，弹窗只做信息性提示；`operation=prompt_polish/prompt_polish_fail` 历史计量行留存。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prompt-crafting`：MODIFIED「一章一个提示词（单轨）」（整章单卡的「发起 AI 润色」入口退役）；REMOVED「AI 润色提示词（会员）」；REMOVED「提示词内容骨架」（润色指引与要素骨架随链退役）；MODIFIED「前情上下文来源升级」「故事状态（截至上章）块注入」（去「润色校验条件锚」条款，改记退役口径）。
- `chapter-plot-items`：MODIFIED「剧情抽卡发起门槛与已润色章提示」——软提示改为「可刷新提示词」，出口＝弹窗「刷新提示词」；不自动重算、不阻断保存口径不变。
- `workbench`：MODIFIED「右栏「AI 辅助」面板（随页签切换，动作全部落地）」（重复动作条款与「重复动作不出现」场景去「AI 润色是提示词唯一润色入口」表述）；MODIFIED「章提示词查看与存稿（生成正文弹窗承载）」（`promptSavedSignal` 行去润色触发方）。
- `workbench-3-label`：MODIFIED「章节点点击 → 中部子 label 切换 正文 / 章纲 / 提示词」（提示词单卡的「AI 润色」入口表述退役；该 requirement 所指「提示词页签」已随 c-prompt-tab-retire 退役，本次只动润色措辞，页签口径的历史陈旧留档不动）。

## Design Impact

- **受影响端**：C端（单端；不触两端共享段/令牌/语境档）。
- **受影响屏/弹层**：章工作台「AI 生成正文」弹窗（book.html `modalAi`）；正文页签右栏 AI 助手状态行（文案不变）；剧情编辑软提示 toast。
- **原型基线关系**：`book.html` 的 `modalAi` footer 本就只有「取消 / 生成正文」（无润色按钮）——本次是**实现向原型基线回归**（两段式润色是原型未登记的实现侧扩展）；弹窗内徽标/「刷新提示词」/「存为本章提示词」仍为已登记的实现侧偏差，本次只改徽标文案（「未润色/已润色」→「本次组装/本章已存稿」）。登记见 `docs/design-c/prototypes/ADJUSTMENTS.md`（新增 c-retire-prompt-polish 条）；无需原型先行（原型无此按钮，无像素面改动）。
- **状态语言**：无新语气档、无新组件形态；徽标仍用既有 `badge warn` / `badge ok` 两态。
- **两端共享段**：不涉及（C端 workbench 弹窗 + 注释级改动）。

## Impact

- 后端：`write/router.py`（端点＋`load_layers` import）、`write/chapter_writer.py`（`validate_polished_prompt`＋`_PLACEHOLDER_RE`）、`prompts/prompt_crafting.prompt`、`tests/test_write_prompt_polish.py`（整删）、`tests/test_write_routes_contract.py`（子路径清单去 /prompt/polish＋缺席反向钉 `test_prompt_polish_route_retired`）、`tests/test_write_regressions.py`（major 2 润色用例与 major 3 条件锚整块删）、`tests/test_chapter_writer_context.py`、`tests/test_plot_prompt.py`、`tests/test_story_state_consumption.py`（条件锚用例删）。
- 前端：`components/novel/workbench/modals.tsx`（AiModal）、`lib/ai.ts`（`polishWritePrompt`）、`components/novel/workbench/ChapterWorkspace.tsx`（软提示出口）、`NovelWorkspace.tsx`/`Rail.tsx`/`AiAssistPanel.tsx`（注释级）、`e2e/prompt-pipeline.spec.ts`（润色步→编辑透传钉）、`e2e/workbench-features.spec.ts`（存量稿徽标断言）、`__tests__/AiModal.test.tsx`（原 `AiModal.twoStage.test.tsx` 改名重写）。
- 提示词仓：`prompt_crafting.prompt` 自本仓删除；`awesome-novel-prompts` 镜像随其 sync 链跟进（本仓 `.prompt` 计数 58→57，零漂移锚随之下移一位）。
- 并行 change 提示：`c-retire-selection-transforms` 的 workbench delta 与本 change 改同一 requirement（其 delta 亦含「生成正文弹窗内的『AI 润色』是提示词唯一的润色入口」旧措辞）——其归档 sync 须重取 main 并落本 change 后的措辞（判例：openspec 归档并行竞态）。
- e2e：`prompt-pipeline.spec.ts` 首用例改为「组装 → 编辑 → 生成」并钉「弹窗内无润色入口/无两段式文案」；`workbench-features.spec.ts` 存量稿断言收紧为徽标文案。本机未跑（隔离栈未起，共享 demo 栈按约定不复用），随 e2e 排程/常规环境复跑。
- **登记不做的两项（待产品拍板，不在本 change 范围）**：
  1. `ChapterContext.material_markdown()` 的生产消费方只剩本 change 删掉的润色端点（现仅测试在用）——未随链删除：它与 `to_user_material` 的「两路同源」是 4 处 spec 条款＋golden 对拍共同维护的既有不变量，删除＝另一次独立退役（含 spec 重写），建议单独立项拍板。
  2. `should_refresh_stored_prompt` 的「非润色产物才回落重组」第三条件是给历史润色行的作者资产保护；润色退役后新存量稿（作家存稿＝新分层口径行）走的是「缺上章结尾块且素材有该块」判据——若作家把该块删掉，重开弹窗会看到重组稿（badge 本次组装）而非存稿。属既有守卫与新现实的口径差，未改行为，登记观察。
