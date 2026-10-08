# chapter-data Specification

## Purpose
TBD - created by archiving change 004-free-workspace. Update Purpose after archive.

## Requirements

### Requirement: useChapterData hook

- The system SHALL provide `hooks/useChapterData.ts` exposing `{ chapter, prose, summary, status, isDirty, saveState, wordCount, targetWords, setTargetWords, save, retry, archive, unarchive, archiveJob, loading, error }`.
- On load, the hook SHALL fetch the chapter (`GET /novels/{projectId}/chapters/{ref}`) and populate prose / outline summary / status.
- Auto-save SHALL debounce at **1500ms** after the last content change (N8: reduced from the legacy 3000ms).
- The save state SHALL be one of exactly four: `autosaving | saved | unsaved | failed`; the failed state SHALL expose a `retry()` action.
- `wordCount` SHALL count non-whitespace Chinese characters, consistent with the backend `/tree` metric (B5).
- `targetWords` SHALL persist (localStorage or chapter metadata) and be adjustable via `setTargetWords`.
- When no target has been set, `targetWords` SHALL fall back to **2500** — the backend write-pipeline default — so the UI progress display and text generation share one default.
- `isDirty` SHALL be `prose !== initialProse || summary !== initialSummary || status !== initialStatus`.
- The hook SHALL flush unsaved changes on unmount or chapter switch (no lost-window).
- The save endpoint SHALL prefer `PUT .../chapters/{ref}/prose` with body `{prose}` (backend #12); while that endpoint is absent it SHALL degrade to `PUT /chapters/{ref}` with the full merged body.
- `archive()` SHALL 改为受理语义：受理成功 SHALL 只置归档任务态 `archiveJob`（提取中/失败/跳过/完成），SHALL NOT 乐观置 `status: "archived"`；`chapter:archived` 事件 SHALL 只在轮询探测到服务端真置位后派发；失败 SHALL 经 `archiveJob` 或归档失败事件暴露（含重试入口）。
- 归档任务进行中（archiveJob＝提取中）SHALL 向消费方暴露锁定信号：正文编辑与归档/取消归档入口禁用；任务态 SHALL 以服务端为准，切章返回后从服务端恢复，SHALL NOT 只存在于内存。

#### Scenario: Debounced autosave after idle
- Given a chapter with prose loaded and a change typed
- When the user stops typing for 1.5 seconds
- Then the chapter auto-saves and the save state transitions to `saved`

#### Scenario: Save failure shows retry
- Given the save request rejects
- When the save finishes
- Then the save state is `failed` and a retry action is available

#### Scenario: Word count counts Chinese chars without whitespace
- Given prose `"你好 世界\n\n。"`
- When `wordCount` is computed
- Then it equals 5

#### Scenario: Default target aligns with generation pipeline
- Given a chapter with no stored target value
- When the hook initializes `targetWords`
- Then it equals 2500, matching the backend generation default

#### Scenario: Flush on unmount
- Given a chapter with unsaved edits
- When the editor unmounts or the chapter changes
- Then the pending edits are flushed to the server

#### Scenario: 受理不等于归档完成
- Given 本书已配置模型，作者点归档且受理成功
- When 受理响应返回
- Then `status` 保持原值，`archiveJob` 为提取中，树/徽标不变；服务端真置位后才派发 `chapter:archived` 并刷新 status

#### Scenario: 归档失败暴露重试
- Given 提取四域中一域失败
- When 轮询读到失败终态
- Then `archiveJob` 为失败（含原因），章保持未归档，UI 出现重试入口

### Requirement: Free-tier chapter editor

- The system SHALL refactor `components/novel/ChapterEditor.tsx` so that the AI surface is hidden on free tier while the code remains (N14/P0-6): the prompt tab, 「AI 写本章」, 「质量检查」, and RightToolbar wiring SHALL be wrapped in `<TierGate feature="ai-generate">`.
- The prose body SHALL remain a `textarea` in this phase (ProseEditor is a later change).
- `onAIStateChange` SHALL NOT be wired in the free tier (the parent RightToolbar render chain is removed).
- Save logic SHALL move to `useChapterData`; the `ChapterEditorHandle` SHALL be retained with AI methods degraded/no-op on free tier.
- The manual save + 1.5s autosave SHALL both be available on free tier; a save failure SHALL show a 「重试」 action.

#### Scenario: Free tier hides AI controls
- Given a free-tier user editing a chapter
- When the editor renders
- Then no 「AI 写本章」, prompt tab, or 「质量检查」 control is present, but the textarea, manual save, and autosave work

#### Scenario: Pro tier restores AI path
- Given a paid user editing a chapter
- When the editor renders
- Then the AI write/quality-check/prompt controls are present as before

#### Scenario: Archived chapter is read-only
- Given an archived chapter being edited
- When the editor renders
- Then the prose area is read-only and an archive indicator is shown

### Requirement: 章档案新增列的持久化与导出（加键兼容）

- `chapters` SHALL 增加两列并随版本换代自动建出（两列进 `models/chapter.py` 即随版本换代自动建出（新版本库 `create_all` 全量建出；旧库按 db-generation 指纹/版本分流留档只读；无任何显式版本常量或 DDL 步骤））：既有 `style_shadow`（JSON 文本，默认 `{}`）与 `ghost_of`（可空字符串）之外，本能力持有两列——`challenge`（可空字符串 ≤150——本章碰到的挑战）、`plot_stage`（可空字符串 ≤20，六档闭集：开局铺垫/冲突初现/矛盾升级/重要转折/高潮爆发/卷末收束——本章在卷剧情里的位置）。
- 章装配（assemble_chapter）SHALL 输出 `style_shadow`（解析后的对象；损坏 JSON 回落 `{}` 且不阻塞读取）、`ghost_of`（set 时输出），以及两列（set 时输出）；全部 SHALL 随章档案导出并随导入回写（加键兼容：缺失键按默认值处理）。
- 两列 SHALL 同步接入消费链路：写正文素材 SHALL 包含挑战（「本章要撞的墙」）与阶段（「本章在卷剧情里的位置」）两块，且**粗组兜底提示词与全量素材包（`material_markdown`，原称「润色素材包」）两条组装路径均须包含**（c-og-slim-v2：此前仅全量素材包含这两块，直写路径会丢失拆章成果；c-retire-prompt-polish 起润色链退役，该渲染面保留为两路同源对拍面）。
- 两列的 JSON 键路径 SHALL 为**章档案顶层**（与 `ladder_exit` 同层，不进 `outline.*`）；`plot_stage` 六档闭集与各列长度校验 SHALL 在 **API 请求 schema 层先于一切写入**（422；装配端 `_fit` 只截断不拒——SHALL NOT 以截断代替校验）。
- `stale` 置位 SHALL 保留既有**第二触发面**：章保存事务内 `ladder_exit` 发生实质变更（trim 后不同）且下一主线章有正文 → 下一章置位「基于旧设定」（清除语义沿用既有「本章保存/归档即清」）；置位判定 SHALL 用 trim 后比较，措辞微调 SHALL NOT 触发。
- 既有章读取契约 SHALL NOT 因新增键破坏：未设置挑战/阶段的章，装配结果语义与字段等价于新增前。
- 章纲表单 SHALL 整表回传两列（保存章纲 SHALL NOT 因表单缺键而清空拆章写入的值）；两列 SHALL NOT 进入章纲必填项。
- **列与子表退役（c-og-slim-v2）**：下列字段 SHALL 从模型定义与装配/拆装链摘除——标量列 `current_task`、`expectation_state`、`chapter_acts`、`intensity_peak`、`intensity_level`、`location`、`story_time`、`narrative_pov`、`perspective_guidance`、`expectation_strategy`、`expectation_detail`、`mood_progression`、`emotional_hook`；子表 `chapter_key_points`、`chapter_scene_cards`、`chapter_segments` 整表退役；`chapter_payoff_items` 保留但只接受 `must_resolve`/`must_hold` 两档（`partial_advance` 档退役）。新代库 SHALL NOT 建出退役列/表；旧库 SHALL 经 db-generation 迁入走列交集（多余的列/表不搬、源库只读留存），SHALL NOT 需要任何 DDL 或 ALTER 步骤。
- 退役键的导出/导入语义：章档案导出 SHALL NOT 输出退役键；备份包格式 SHALL 按「删键＝升版」规则升版（FORMAT_VERSION v4 → v5）；导入 v4 及更早的包时，退役键 SHALL 按忽略处理，SHALL NOT 报错、SHALL NOT 复活（不写回任何退役列/表）。
- 章版本快照与旧快照回退 SHALL 与退役键解耦：旧快照中携带的退役键 SHALL 在回退时被忽略，SHALL NOT 导致保存失败或子表异常清空。

#### Scenario: 影子随导出导入往返
- **WHEN** 某章设置了影子行后导出并重新导入
- **THEN** 该章的影子行原样保留

#### Scenario: 损坏影子不阻塞读取
- **WHEN** 某章 style_shadow 存了非法 JSON
- **THEN** 章装配成功，shadow 为空对象

#### Scenario: 支线来源随章保留
- **WHEN** 某章转入旧稿支线（ghost_of=目标章号）后导出
- **THEN** 导出包含 ghost_of，导入后支线关系保留

#### Scenario: 五段随导出导入往返
- **WHEN** 拆章排上一章（本章剧情/挑战/结尾/阶段四段齐——原第五段「本章行动」已随 c-og-slim-v2 退役）后导出并重新导入
- **THEN** 该章 summary、challenge、plot_stage、ladder_exit 原样保留

#### Scenario: 拆章内容进入写正文素材
- **WHEN** 某章已填挑战与阶段后发起写正文，分别取粗组兜底与全量素材包（`material_markdown`）两条路径
- **THEN** 两条路径的产物均包含「本章要撞的墙」与「本章在卷剧情里的位置」两块（原「本章必须发生的动作」块随该格退役）

#### Scenario: 保存章纲不清空拆章内容
- **WHEN** 作者在章纲页只改主情绪并保存（表单携带两列当前值）
- **THEN** challenge/plot_stage 保持原值，SHALL NOT 被清空

#### Scenario: 阶段越界拒绝
- **WHEN** 写入 plot_stage＝「高潮」（不在六档）
- **THEN** 返回 422，值不落库

#### Scenario: 未填新列的旧章读取等价
- **WHEN** 读取一个从未拆过章的旧章
- **THEN** 装配结果不含挑战/阶段键或以空值呈现，其余字段与新增前等价

#### Scenario: 退役键不出现在读写面
- **WHEN** 读取任意章并保存一次
- **THEN** 装配结果不含任何退役键；请求体携带退役键时被忽略，不写入模型、不报错

#### Scenario: 旧备份包导入忽略退役键
- **WHEN** 导入一份 v4 备份包，其中某章携带关键事件/场景卡/段落规划/地点/预期策略等内容
- **THEN** 导入成功，这些内容按退役忽略处理（不落库、不报错），其余字段照常回写

#### Scenario: 旧库迁入走列交集
- **WHEN** 用新版本应用迁入一份含退役列的旧库
- **THEN** 列交集搬运跳过退役列/表，源库只读留存，迁入报告如实反映跳过情况，无 DDL 步骤

#### Scenario: 旧快照回退忽略退役键
- **WHEN** 恢复一个含退役键的历史章快照
- **THEN** 正文与留存字段正常恢复，退役键被忽略，SHALL NOT 因退役键导致保存失败

### Requirement: 重写旧稿支线章（后缀 ref）

- 重写产生的旧稿支线章 SHALL 以 `{源章 ref}-r{sha256(正文)[:8]}`（内容寻址）为 ref 落库，`ghost_of` 指向源章 ref；同一章不同内容重写产生多个旧稿，同内容重放命中既有 ref（幂等，不重复落）。
- 该支线章 SHALL 携带：标题（源章当时标题）、正文（快照全文）、`ghost_of`；章纲/收尾等派生数据 SHALL NOT 复制（旧稿是文稿快照，不是第二份主线数据）。
- 装配与导出契约 SHALL 与既有支线章一致（`ghost_of` 加键直出、随导出包往返、导入 ref 重绑规则不变）；书级统计（字数/章数/归档数）与主线端点 SHALL 继续排除支线章（既有口径，零改动）。
- 后缀 ref SHALL NOT 参与 `-ch-(\d+)` 章号解析链的正章匹配（解析取最后一段 `-ch-N` 之后再遇 `-r` 后缀的须按支线处理；实现侧统一走 ghost_of 判定，不做数字猜测）。

#### Scenario: 多次重写产生多个旧稿
- **WHEN** 同一章先后以不同内容重写两次
- **THEN** 旧稿支线出现该章两个快照（内容寻址 ref 不同），均可只读查看

#### Scenario: 同内容重放幂等
- **WHEN** 对同一章以未变更的正文重复发起重写
- **THEN** 命中既有旧稿 ref，不新增快照（ghost_created=false）

#### Scenario: 旧稿随导出包往返
- **WHEN** 含旧稿支线章的书导出并重新导入
- **THEN** 旧稿章与 `ghost_of` 关系保留，主线统计不因旧稿变化

### Requirement: 章写入口缺键守卫（patch-gates）

- 章 PUT／统一写入口 SHALL 按「缺键保持现值」落库（c-og-chapter-put-patch-gates；2026-09-28 演示栈事故——挑战/章末落点/必须完成的变化被部分键 PUT 抹空——后确立）：任一字段族（`outline.*` 标量、`memo.*` 子表族、`emotional_design.*`、顶层标量 `ladder_exit`/`challenge`/`plot_stage`/`word_target`、`micro_payoffs`）的键缺失、值为 `null` 或形状不符（非 dict/非 list）SHALL 保持该族现值，SHALL NOT 以空值覆盖；`plot_items` 沿用其既有 presence-gate（本要求将其推广到全部字段族）。
- 显式清空 SHALL 走显式空值：文本标量传 `""`，列表/子表传 `[]`（`word_target` 传 `null` 表清除）。
- `prose` 键缺失 SHALL 视为「本次不动正文」：正文与派生元数据（`word_count`/`has_prose`/`outline_status`）SHALL 保持现值；版本快照 SHALL 仅在 prose 或 `outline.summary` 实质变化时写入。
- 前端章纲表单继续整表回传（兼容不变）；部分键写入（旁路链路如拆章排上等）SHALL NOT 再清空未携带字段（原「AI 起草底座」已随 c-og-ai-draft-retire 退役）。

#### Scenario: 部分键保存不动其余字段
- **WHEN** 对已填全章纲的章 PUT 仅携带 `{"challenge": "新墙"}`
- **THEN** challenge 更新；summary/characters/memo 三族/emotional_design/ladder_exit/micro_payoffs/plot_items 全部保持原值

#### Scenario: 显式空值仍可清空
- **WHEN** PUT 携带 `{"ladder_exit": ""}` 或 `{"memo": {"required_changes": [], "prohibitions": [], "payoff_plan": {"must_resolve": [], "must_hold": []}}}`
- **THEN** 对应字段被清空，其余字段保持

#### Scenario: 缺 prose 键不动正文
- **WHEN** 对有正文的章 PUT 仅携带章纲字段（无 prose 键）
- **THEN** 正文、word_count、has_prose、outline_status 保持原值，且不因此写版本快照

### Requirement: 剧情条目列（plot_items）
- `chapters` SHALL 增加 `plot_items` 列并随版本换代自动建出（JSON 文本列，默认 `[]`、server_default `[]`；无任何显式版本常量或 DDL 步骤，照 db-generation 既有纪律）。
- 章装配（assemble_chapter）SHALL 输出 `plot_items`（解析后的字符串数组；空串或损坏 JSON 回落 `[]` 且不阻塞读取）。
- 章档案导出/导入 SHALL 携带 `plot_items`（加键兼容：缺失键按 `[]` 处理）。
- 落库缺键语义 SHALL 为 presence-gate：缺键保留现值、显式 `[]` 清空（与 `style_shadow` 同口径）。
- 输入收口（c-og-slim-v2）：非字符串条目（对象/数组/数字/布尔）SHALL 被拒（请求 schema 返回 422）或丢弃，SHALL NOT 经字符串化后落库——SHALL NOT 出现把整条序列化成 `{'text': ...}` 之类形态存进列表并计入正文提示词的结果。

#### Scenario: 旧库升级章读取

- **WHEN** 旧版本库升级后读取既有章
- **THEN** plot_items 输出为空数组，读取不报错、无显式回填步骤

#### Scenario: 损坏值不阻塞读取

- **WHEN** 某章 plot_items 存了非法 JSON
- **THEN** 装配输出空数组，章读取不报错

#### Scenario: 导出导入往返

- **WHEN** 一章含 4 条剧情导出章档案后导入
- **THEN** 4 条原样回写；导入包缺失该键时按空数组处理

#### Scenario: 非字符串条目被收口

- **WHEN** 保存请求携带 `plot_items: [{"text": "潜入库房", "weight": "high"}]`
- **THEN** 该条目被拒（422）或丢弃，SHALL NOT 落库为 `"{'text': '潜入库房', ...}"` 这样的字符串，SHALL NOT 进入任何提示词产物
