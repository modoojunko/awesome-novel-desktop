# c-og-slim-v2 — 章纲字段瘦身：11 格退役＋必填降到两项＋补两个漏信息的提示词洞

## Why

章纲页现有 24 个输入格子，但按「不填这一条，正文会不会写坏」这条判据切开，语义真正独立的只有 13 个。其余的是几代实现叠加出的同义堆积：**「这一章发生什么」有 6 种说法**（概要/关键事件/剧情条目/本章行动/段落规划/场景卡）、**「结尾怎么停」有 3 种**（章末落点/章末情绪钩子/场景卡钩子）、**「读者那边怎么设计」有 4 种**（主情绪/预期策略/预期细节/章内微弧线）、**「障碍是什么」有 2 种**（挑战/场景卡阻碍）。作者面对的是同一件事被问四遍。

更糟的是门槛与信息源脱钩：**必填四项里的「预期策略」与「段落规划」，AI 写正文时一个字都不读**——门槛卡的是作者，不是信息完整性。c-og-fields-slim 已退役「核心任务／读者当前状态」两格并留下先例，本次把同一判据推到底。

同时查证出两个既有的漏信息缺陷，删除会让它们更致命，本批一并补上：润色素材包（PRO 点「润色」时喂给模型的原料，产物直接用于生成正文）**不含「章纲概要」**；未润色直写走的粗组兜底提示词**不含「挑战／阶段」**——即拆章成果在这条路上完全不进正文。

## What Changes

- **BREAKING** 章纲页 11 格退役（UI 控件、API 读写、存储列/子表、提示词消费点一并撤）：关键事件 `key_points`、地点 `location`、时间 `story_time`、叙事视角 `narrative_pov`、视角指导 `perspective_guidance`、预期策略 `expectation_strategy`、预期细节 `expectation_detail`、可部分推进 `payoff_plan.partial_advance`、段落规划 `segments`、本章行动 `chapter_acts`、场景卡 `scene_cards`（含 `weight`/`focus`——权重不做迁移，整组退役）。
- **BREAKING** 随批退役不在页面上的隐藏字段：章内微弧线 `mood_progression`、章末情绪钩子 `emotional_hook`（语义分别并入主情绪与章末落点）、强度峰值 `intensity_peak`、强度等级 `intensity_level`（产品已裁定不做题材节奏自动控制）。
- **BREAKING** 存储退役口径＝**列/子表从模型摘除**：新代库不再建出，旧库经 `db-generation` 迁入走列交集（多的列不搬，源库只读留存），无 DDL 步骤；章档案导出不再输出这些键，**备份包格式升版 v4 → v5**（照 `backup/format.py`「删键＝升版」规则），旧包导入时这些键按忽略处理、SHALL NOT 报错。
- 章纲必填门槛**四项 → 两项**（必须完成的变化、主情绪）；同步修掉前端既存口径 bug：`ChapterWorkspace` 的 `reqOk: 6 - ogGaps()` 与右栏「归档门槛 N/6」是「六改四」时未同步的错值，本次一并改为按必填项数派生。
- **补两个漏信息的洞（同批）**：① 润色素材包新增【章纲概要】块（概要＋挑战＋阶段，与粗组同源）；② 粗组兜底提示词补「本章要撞的墙」「本章在卷剧情里的位置」两块；③ 读者获得的类型在提示词里由英文 key（`clue`/`relation`）改渲染中文标签。
- 场景卡退役后，提示词里的「按场景权重分配笔墨」措辞与润色骨架第 6 要素（场景原材料）一并退役；笔墨分配交给剧情条目顺序与 AI 自行判断。
- 剧情推演「按这条走法收进章纲」的落点由「预期策略」改为**追加一条剧情条目**（`plot_items`）；推演素材与兜底链换源（关键事件 → 剧情条目，缺失回落固定句）。
- 「AI 起草」「缺项补全」的字段骨架与白名单同步收缩：起草必备骨架由「概要＋段落规划」改为**概要一项**；补缺白名单收缩为概要/出场角色/必须变化/禁令/主情绪。
- 拆章卡面**五段 → 四段**（删「本章行动」）；「客观局面·谁在场」的写法约束由「本章行动」移至「本章剧情」与剧情条目。
- `plot_items` 输入收口：非字符串项 SHALL 被拒或丢弃，SHALL NOT 经 `str()` 存成字典 repr 字符串（现 `chapters/schemas.py:normalize_plot_items` 会静默存成 `{'text': ...}` 形态并拼进提示词）。
- 被删字段的下游消费者全部换源：文风建议素材与 AI 体检的「关键事件」→ 剧情条目＋概要；拆章/拆卷越纲的「已知地点集」→ 世界设定与设定侧地点单源（不再读章级 `location`）。

**非目标**：场景卡权重迁移到剧情条目（已裁定整组退役）；题材节奏自动控制（本次删掉其数据基础，如将来要做另立 change 重设字段）；卷纲侧字段；提示词精修（补全负向约束／精简）口径。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-data`: 11 格对应列/子表与 4 个隐藏字段退役（持久化 requirement 收窄到留存字段）；导出/导入不再携带被删键；`plot_items` 输入收口。
- `chapter-plot-items`: `plot_items` 数据契约补「非字符串项收口」；采纳来源新增推演走法行的追加路径（与 AI 三版采纳同表不同入口）。
- `chapter-plan-ai`: 卡面五段改四段；「客观局面」约束改由本章剧情承载；排上写入字段去「行动」；落点卡「还差 4 项／补这 4 项」改 2 项；回改保存的保全清单去场景卡。
- `outline-ai-draft`: 起草产物字段与必备骨架收缩（去段落规划/场景卡/地点/时间/视角/预期三项）；「有现有章纲」判定覆盖的格子收缩；补缺白名单收缩。
- `prompt-crafting`: 素材包块清单（去场景原材料、补章纲概要）；前情上下文来源换源（去 mood_progression/emotional_hook/期待缺口，取上章概要＋必须完成的变化＋章末落点）；章纲格子编辑控件清单收缩；提示词内容骨架（要素 6 退役、要素 2/8 措辞更新）；组装来源「本章章纲」内容收缩。
- `plot-sim`: 推演素材与兜底链换源（关键事件 → 剧情条目）；「收进章纲」写入目标改剧情条目。
- `workbench`: 章纲页签撤 11 格；「AI 起草」覆盖判定枚举收缩；必填缺口数由 6 → 2 派生并修 reqOk 错值；「剧情推演」收进章纲的落点与文案更新。

## Impact

- **后端**：`client/backend/models/chapter.py`（列与子表类）、`chapters/store.py`（装配/拆装映射与子表替换）、`chapters/schemas.py`（plot_items 收口）、`chapters/service.py`、`chapters/ai_draft.py`（起草骨架/白名单/现有章纲判定）、`chapters/ai_plan.py`（拆章素材落库字段与已知地点集）、`chapters/plan_ai.py`（卡面四段与评分判据字段名）、`write/chapter_writer.py`（两条提示词路径）、`write/ai_check.py`、`write/style_shadow.py`、`write/plot_sim.py`、`write/prompt_sources.py`、`workflow/gates.py`、`backup/format.py`（v5）与 `backup/importer.py`、`chapters/versions.py`（旧快照回退的字段处置）。无 DDL 步骤、无 alembic 迁移。
- **前端**：`components/novel/workbench/OgPane.tsx`、`chapterForm.ts`、`ChapterWorkspace.tsx`、`AiAssistPanel.tsx`、`SimModal.tsx`、`ChapterPlanModal.tsx`、`VolumeWorkspace.tsx`、`lib/chapterPlanApi.ts`、`hooks/useOutline.ts`。
- **测试与门禁**：后端两处提示词 golden（`tests/golden/plot_empty_*.txt`）与批量单测（chapter writer/outline-ai-draft/volume-chapter-crud/backup-roundtrip/plot-sim/chapter-plan-ai）；前端 vitest（`chapterForm.*`、`chapterPlan`、`plotSimAndPromptSources`）与 e2e（`chapter-plan`、`ai-assist`、`plot-sim`、`outline-ai-draft`、`workbench-features`、`plot`、`design-parity-book`）；C端 `design:lint` / `design:check` / `tsc --noEmit`。
- **数据**：零真实用户（2026-09-18 已确认），被删字段的存量内容按删除语义处理，不做兼容搬运；旧库经迁入向导走列交集。

## Design Impact

- **受影响端**：C端（`client/frontend`）。S端不涉。
- **受影响屏/弹层**：章纲页签（`OgPane`，撤 11 格与 3 个折叠组）、拆章弹窗卡面（五段 → 四段）、剧情推演弹窗（收进落点与文案）、剧情区（新增推演走法行的追加入口）、提示词页签「组装来源」区（本章章纲来源内容收缩）、右栏「AI 辅助」面板（章纲页签缺口清单与门槛分母）。
- **对象状态**：不新增任何状态；本次为纯删除。文案按 design-language §13：按钮词为动词，缺口文案「还差 2 项才能开写：必须完成的变化、主情绪」带可点击出口。
- **共享段**：不触碰两端共享段（base.css 令牌与基础组件类、pill/notice/sk/panel/f-err 家族）。退役的 `.scene-card` / `.scene-chain` / `.payoff-row` / `.seg-row` 等类不在 `design-vocab.mjs` 词表、也不在 `design-system` spec 的词汇要求内，故**不声明 Modified: design-system**；同批删除对应 CSS 段。
- **原型先行**：需要——`docs/design-c/prototypes/book.html` 章纲页签撤格与拆章卡面四段需先改，并在 `prototypes/ADJUSTMENTS.md` 登记「字段退役（c-og-slim-v2）」条目；`design:check` 基线受影响时按既有管线重录。
- **设计工件产出**：实现侧自查（纯删除既有控件与区块，不新增视觉形态，不需要设计侧出新稿）。
