## MODIFIED Requirements

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
