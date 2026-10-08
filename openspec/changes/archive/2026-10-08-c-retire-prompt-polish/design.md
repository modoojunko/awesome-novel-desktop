## Context

生成正文弹窗的「AI 润色」是两段式提示词管线（ai-prompt-crafting）的第二段：确定性素材包 → 大模型润色成成品提示词 → 轻校验（`validate_polished_prompt` 条件锚）→ 覆盖写 `write-prompt` 行。产品实况（2026-10-08 用户拍板）：程序组装稿已达标（真机朱雀 100%），同一次生成里先让大模型改写提示词再写正文属多余的添油加醋，且多付一份 token；改写的产物还要靠锚词校验兜底，是质量风险的来源而非保险。

退役面（实现侧清单）：
- 后端：`POST /write/{chapter_ref}/prompt/polish`（write/router.py）→ 模板 `prompts/prompt_crafting.prompt` → 校验 `validate_polished_prompt`（write/chapter_writer.py，含 `_PLACEHOLDER_RE`）。
- 前端：`AiModal` 的「AI 润色」按钮＋`polishing`/`polishError` 状态＋「重试润色」块＋两段式引导文案 → `lib/ai.ts` `polishWritePrompt` → 剧情改动软提示出口（原打开弹窗让用户点润色）。
- specs：7 个 capability（prompt-crafting / chapter-plot-items / workbench / workbench-3-label / prose-writing / intro-genre-settings / chapter-data）。

## Goal / Non-Goals

- Goal：「AI 润色」全链退役——提示词只由「确定性组装 ＋ 作家编辑/存稿」产生；弹窗与右栏不再出现润色入口；规格与文案不再描述该能力。
- Non-Goals：不撤销素材包组装（`material_markdown`/`to_user_material` 与两路同源）、不撤销存量稿优先与代际守卫（`should_refresh_stored_prompt`）、不动选区加工（去AI味 `/write/polish`、文风/简介润色是别的能力）、不动阶段机（`outline→prompt→write` 由 `POST /write` 承载）。

## Decisions

### D1. 全链退役而不是只藏按钮

按钮是能力的唯一入口，删掉即能力不可达；留端点＋校验＋模板＝把不可达的 AI 计费面与「spec 说 UI 该有润色入口」的假话一起留在仓里。按 c-retire-continue-writing 先例全链退役。BREAKING 影响面＝零（桌面应用前后端同包发布，无外部 API 消费者）。

### D2. 删校验函数，但保留 `_POLISH_ANCHORS` 与 `strip_code_fences`

`validate_polished_prompt` 的唯一消费方是被删的端点，随链删除；`_POLISH_ANCHORS`（三锚）仍有消费方——`legacy_prompt_kind`/`should_refresh_stored_prompt` 用它判**存量历史润色行**（旧数据判型，与是否还能发起润色无关）→ 保留并改注释口径；`strip_code_fences` 由 plot_sim/ai_check/ai_draft 共用 → 保留。

### D3. 徽标改口径：`未润色/已润色` → `本次组装/本章已存稿`

`polished` 字段（后端契约）语义不变（true＝存在 `write-prompt` 行），仅用户可见文案去掉「润色」词（能力已退役）；testid（`ai-raw-tag`/`ai-polished-tag`）保留不动，e2e 钉子不受扰动。

### D4. 剧情软提示改出口（死路修复）

「提示词还是旧版…可以重新润色／去重新润色」打开的正是本弹窗，弹窗内已无润色按钮 → 改「可以刷新提示词／去刷新提示词」（出口功能不变：打开弹窗，用户点「刷新提示词」按新剧情重组预览）。不自动重算、不阻断保存口径不变。标识符 `polishHint*`/`maybeHintPolish` → `promptHint*`/`maybeHintPromptRefresh`（避免退役名残留误导）。

### D5. 只删润色链，不顺手删 `material_markdown`

`material_markdown()` 的生产消费方随本 change 消失（现仅测试在用），但它是「两路同源」不变量的半壁——该不变量由 4 处 spec 条款＋golden 对拍维护。删除它＝独立退役（含 spec 重写），不在本 change 顺手做，proposal 登记为待拍板项。

### D6. 评审轮：补第五个 capability，并更正「生成不回写存稿」的既有矛盾

- 漏面：`prose-writing`「基于确认提示词生成」是弹窗取稿口径的规格主源（原 delta 只覆盖四个 capability），且其 Scenario 引用「润色校验锚（见 prompt-crafting）仅在**新发起润色**时生效」——被引用的 requirement 已被本 change REMOVED，属悬空引用 → 补 delta 并删句。
- 既有矛盾（本 change **只改文本、零行为变更**）：`prose-writing` 场景与 `workbench` 存稿条款、弹窗引导句均称「不点存稿的编辑仅用于本次生成／不回写持久化提示词」，与实现相悖——`POST /write` 历来把本次所用稿落库为本章提示词行（回归钉 `tests/test_write_regressions.py::test_override_still_wins` 断言 `_read_stored_prompt == "作家手动编辑版"`）。判据：有回归钉的一侧即当前事实；三处按实现口径更正。**若产品口径应反过来（生成不回写），属行为变更，须另立 change 同批改实现＋钉＋文案**——本 change 不擅自翻实现。
- `intro-genre-settings` 两处调用点/模型粒度清单去「提示词润色」；`chapter-data` 两处「润色素材包」正名「全量素材包（`material_markdown`）」（对应 D5 的保留决定）。

## Risks

- **归档并行竞态**：`workbench`「右栏「AI 辅助」面板…」被 `c-retire-selection-transforms` 与 `c-retire-continue-writing`（均未归档）同 requirement 修改；`intro-genre-settings`「模型选择的三层粒度与绑定」被 `c-retire-continue-writing` 同 requirement 修改。其 delta 是旧快照，若在本 change 之后归档且同步不做智能合并，会把本 change 的措辞回退。归档前重取 main 复核（本 change 的 proposal Impact 已登记）。
- **代际守卫的暴露面变化**：`should_refresh_stored_prompt` 的「作者资产」保护（三锚）只覆盖历史润色行；润色退役后新存量稿（作家存稿）若删掉「上章结尾」块，预览会被重组稿顶替——既有守卫与新现实的口径差，未改行为，proposal 登记观察。
