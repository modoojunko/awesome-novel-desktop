# workbench-ai-check-refine

## Why

右栏「AI 辅助」面板的占位动作（ADJUSTMENTS #27 ⑧）此前只剩「检测族/精修族/章纲补缺」未落地，
用户在「章纲」页签还得手动补必填项、在「文风/关系/伏笔」页签只能拿 reconcile 收尾看设定写回，
缺一类「只读、不落库、就地看结论」的案头检查；提示词也只能整篇手工改，缺「按目标修订」的半自动入口。

## What Changes

- **六类案头检查（ai-check）**：新增 `POST /api/novels/{pid}/chapters/{ref}/ai-check {kind}`——
  `volume_conflict`（与卷纲冲突）/`relations_conflict`（关系冲突）/`hooks_conflict`（伏笔冲突）/
  `style_consistency`（文风一致性）/`style_deviations`（标记偏离段落）/`relation_suggest`（建议补边）。
  素材按类别取自章纲/正文/卷纲/关系真表/伏笔台账/文风基线；产出 findings（{title, detail}，≤8 条、空数组合法）；
  PRO＋本书模型双门控；**产物不落库**（就地弹窗消费）；记账 `ai_check_{kind}`（失败留 `_fail`）。
- **章纲缺项补全**：新增 `POST …/outline/fill-gaps {missing[]}`——按缺口清单产出 `fills`（白名单键，
  含结构化 `segments`）；产物**不落库**，由章纲表单承接后走既有保存链；右栏面板补「还缺」清单（原型 aiList 口径）。
- **提示词精修**：新增 `POST …/write/prompt/refine {mode: negative|concise}`——按「补全负向约束/精简」
  修订整章提示词，产出只读展示；作者在弹窗确认后由前端 `PUT …/prompts/write` 走既有保存链写回（提案制）。
- **右栏面板接线＋撤三个重复动作（ADJUSTMENTS #27 ⑫）**：检测族/精修族/补缺动作全部变为真按钮；
  撤「重新组装提示词」（＝提示词页签内 AI 润色同动作，且粗组稿每次重算）、「本章关系变化检测」
  （＝操作页签 reconcile 关系收尾）、「建议本章回收」（＝reconcile 伏笔收尾的收束提案）。
- **原型词表对齐（伏笔标签换词收尾）**：`docs/design-c/prototypes/book.html` 的 `HOOK_TYPES`
  由草拟期旧词（谜团/关系/力量/情感/选择/欲望）改为与后端单源一致的标准标签
  （悬念/威胁/承诺/线索/关系伏笔/能力伏笔/情绪钩/选择钩/渴望钩）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `workbench`：「右栏「AI 辅助」面板（随页签切换）」——占位动作口径收窄（补缺/检测/精修三类改为已实现，
  各页签动作清单更新，撤销的三个动作不再出现）；新增「六类案头检查（ai-check）」「章纲缺项补全」
  「提示词精修（提案制）」三条需求。
- `outline-ai-draft`：章纲 AI 族新增缺项补全端点（白名单/结构化 segments/表单承接口径）。
- `prompt-crafting`：提示词链路新增精修端点（两模式、不落库、确认后走既有保存链）。

## Design Impact

- 受影响端：C端（client/frontend）。
- 受影响屏/弹层：章工作台右栏「AI 辅助」面板（各页签动作清单＋章纲「还缺」清单）；
  新增两个弹窗 `AiCheckModal`（检测结果）与 `RefinePromptModal`（精修预览＋采纳）。
- 对象状态：沿用既有状态语言（`.ck-note.ok` 空态=中性文案、`.ck-note.err` 失败=err 语气、
  `rail-locked` 免费档禁点）；不新增语气词、不新增胶囊形态。
- 是否触碰两端共享段：否（仅 C端 书工作台域；S端 无对应屏）。
- 原型先行：**不需要改原型**——本批全部按 `docs/design-c/drafts/storyline.html` 既有 aiActs 文案实现
  （原型未动，仅 `prototypes/book.html` 的伏笔类型词表按后端单源校正）；三处撤销动作按 ADJUSTMENTS #27 ⑫ 登记。
- 设计工件产出：实现侧自查（design:lint + 既有 parity 基线不涉及 storyline 屏；无新增像素基线）。

## Impact

- 后端：`write/ai_check.py`（新）、`chapters/ai_draft.py`（+fill-gaps）、`write/router.py`（+refine）、
  `main.py`（挂路由）、`prompts/ai_check.prompt`·`outline_fill_gaps.prompt`·`prompt_refine.prompt`（新）。
- 前端：`lib/aiCheck.ts`（新）、`workbench/AiCheckModal.tsx`·`RefinePromptModal.tsx`（新）、
  `AiAssistPanel.tsx`·`ChapterWorkspace.tsx`·`Rail.tsx`·`chapterForm.ts`（接线）、`design/book.css`（面板/弹窗小样式）。
- 测试：后端 `tests/test_ai_assist_checks.py`（18 例）、前端 `aiCheck.test.ts`／`aiAssistModals.test.tsx`／
  `AiAssistPanel.test.tsx`（更新）、e2e `ai-assist.spec.ts`（PRO 全链＋免费档锁定）。
- 无破坏性变更；不复用既有端点、不改既有响应形状（新增字段 `fills`/`findings`/`prompt` 均新端点内）。
