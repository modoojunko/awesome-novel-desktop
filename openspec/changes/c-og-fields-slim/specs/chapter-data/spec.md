# chapter-data delta

## Purpose

由 c-og-fields-slim 修改：核心任务／读者当前状态退役，归档门槛六项改四项（见 proposal）。

## MODIFIED Requirements

### Requirement: 章档案新增列的持久化与导出（加键兼容）

- `chapters` SHALL 增加三列并随版本换代自动建出（三列进 `models/chapter.py` 即随版本换代自动建出（新版本库 `create_all` 全量建出；旧库按 db-generation 指纹/版本分流留档只读；无任何显式版本常量或 DDL 步骤））：既有 `style_shadow`（JSON 文本，默认 `{}`）与 `ghost_of`（可空字符串）之外，本 change 新增三列——`challenge`（可空字符串 ≤150——本章碰到的挑战）、`chapter_acts`（多行文本，一行一条 ≤4 行 × 60 字——本章行动：谁做了什么）、`plot_stage`（可空字符串 ≤20，六档闭集：开局铺垫/冲突初现/矛盾升级/重要转折/高潮爆发/卷末收束——本章在卷剧情里的位置）。
- 章装配（assemble_chapter）SHALL 输出 `style_shadow`（解析后的对象；损坏 JSON 回落 `{}` 且不阻塞读取）、`ghost_of`（set 时输出），以及三新列（set 时输出：`challenge`/`chapter_acts`（按行拆为字符串列表，读回与写回同形）/`plot_stage`）；全部 SHALL 随章档案导出并随导入回写（加键兼容：缺失键按默认值处理）。
- 三新列 SHALL 同步接入两处判定与消费链路：①「有现有章纲」判定 SHALL 覆盖三新列（见 outline-ai-draft 素材汇集）；②写正文素材 SHALL 包含挑战（「本章要撞的墙」）、行动（「本章必须发生的动作」）、阶段（「本章在卷剧情里的位置」）三块。
- 三新列的 JSON 键路径 SHALL 为**章档案顶层**（与 `ladder_exit` 同层，不进 `outline.*`）；`plot_stage` 六档闭集与各列长度校验 SHALL 在 **API 请求 schema 层先于一切写入**（422；装配端 `_fit` 只截断不拒——SHALL NOT 以截断代替校验）。
- `chapter_acts` 校验 SHALL 归一化（换行归一、逐行去空白、丢空行、逐行 ≤60、行数上限 4），装配端复用同一归一。
- `stale` 置位 SHALL 增加**第二触发面**：章保存事务内 `ladder_exit` 发生实质变更（trim 后不同）且下一主线章有正文 → 下一章置位「基于旧设定」（清除语义沿用既有「本章保存/归档即清」）；置位判定 SHALL 用 trim 后比较，措辞微调 SHALL NOT 触发。
- 既有章读取契约 SHALL NOT 因新增键破坏：未设置挑战/行动/阶段的章，装配结果语义与字段等价于新增前。
- 章纲表单 SHALL 整表回传三新列（保存章纲 SHALL NOT 因表单缺键而清空拆章写入的值）；三新列 SHALL NOT 进入章纲必填项。

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
- **WHEN** 拆章排上一章（剧情/挑战/结尾/行动/阶段齐）后导出并重新导入
- **THEN** 该章 summary、challenge、chapter_acts（列表同形）、plot_stage、ladder_exit 原样保留

#### Scenario: 拆章内容进入写正文素材
- **WHEN** 某章已填挑战、行动与阶段后发起写正文
- **THEN** 素材包含「本章要撞的墙」「本章必须发生的动作」「本章在卷剧情里的位置」三块

#### Scenario: 保存章纲不清空拆章内容
- **WHEN** 作者在章纲页只改主情绪并保存（表单携带三新列当前值）
- **THEN** challenge/chapter_acts/plot_stage 保持原值，SHALL NOT 被清空

#### Scenario: 阶段越界拒绝
- **WHEN** 写入 plot_stage＝「高潮」（不在六档）
- **THEN** 返回 422，值不落库

#### Scenario: 未填新列的旧章读取等价
- **WHEN** 读取一个从未拆过章的旧章
- **THEN** 装配结果不含挑战/行动/阶段键或以空值呈现，其余字段与新增前等价
- **列退役（c-og-fields-slim）**：`current_task`（核心任务）与 `expectation_state`（读者当前状态）两列 SHALL 转**只留不读写**——存量列留在库中（SQLite 无迁移链，删列无路径），但章档案读写、归档门槛、AI 体检/推演/起草补缺 SHALL NOT 再消费；对应表单格一并退役，必填门槛改四项（预期策略/必须完成的变化/主情绪/段落规划）。
