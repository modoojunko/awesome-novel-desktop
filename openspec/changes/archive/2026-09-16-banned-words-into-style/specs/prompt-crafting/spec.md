# prompt-crafting 变更（增量）

> 基线依赖：本 delta 以 style-settings-v2 归档后的 prompt-crafting spec 为基线；style-settings-v2 须先归档 sync。

## MODIFIED Requirements

### Requirement: 素材包确定性组装

- 文风段 SHALL 重排为单一来源结构：身份（叙事身份一句）→红线（硬约束逐条）→手法（描写手法逐行）→例句（few_shot 逐条）；`possible_mistakes` 行与「叙事基调」块（`build_tone_section`）SHALL 退役——通用反模式由文风硬约束子区（禁用词/句式规则）承接，基调信息经归一并入身份/手法。
- 「原则与禁忌」段 SHALL 单源化：「禁止使用以下词汇」SHALL 只取文风 KV 的 `banned_words`，「禁止以下句式」SHALL 只取文风 KV 的 `tic_patterns` 前 5 条（现行为钉住，机器体检仍全量）；对 style 卡 fatigue_words 与题材行疲劳词的合并读取 SHALL 删除。
- 续写/润色/扩写辅助链的风格格式（`_format_style`）与禁用词注入 SHALL 同步为文风 KV 单源。
- 新增量化基线段：style-quant `confidence > 0` 时 SHALL 注入六行基线（约 X（±容差）、可按本章剧情在容差内自行调节）；`confidence = 0`/缺失 SHALL NOT 注入。
- 活跃伏笔块 SHALL 为 `planned_chapter_id == 当前章 id` 的条目追加「建议本章收束」标记。
- 未填字段 SHALL 跳过对应内容，SHALL NOT 注入未替换占位符；旧键（possible_mistakes/tone/fatigue_words）经归一后不再直接读取。

#### Scenario: 三区文风段

- **WHEN** style KV 归一后含 role「冷静叙事者」、rules 3 条、craft 2 条、few_shot 1 条
- **THEN** 提示词文风段依次含身份行、红线列表、手法列表、例句行；无「叙事基调」「文风常见错误」字样

#### Scenario: 归一后的旧书不丢文风

- **WHEN** 存量书 style KV 只有旧键 narrator_role/tone.pov/possible_mistakes/core_principles
- **THEN** GET /settings/style 返回归一三区（旧基调并入身份、旧错误并入红线），写章提示词按三区注入且内容不丢（原文留 `_legacy_style`）

#### Scenario: 禁忌词句单源注入

- **WHEN** 文风 KV banned_words 含「突然」、tic_patterns 含「不是…而是」，组装写章提示词
- **THEN** 「禁止使用以下词汇」段恰含「突然」、「禁止以下句式」段恰含该正则；来源唯一（无第二份词表参与拼接）

#### Scenario: 迁移词迁移后仍生效

- **WHEN** 存量书禁用词原在 anti-ai.yaml，完成迁移后组装写章提示词
- **THEN** 这些词出现在「禁止使用以下词汇」段（迁移不丢拦截能力）

#### Scenario: 章级量化指令可预期

- **WHEN** style-quant confidence=82，本章章纲剧情标注「打斗」
- **THEN** 提示词量化段给全书基线与 ±10% 容差指令（对话约 48%（±10%）……），无按章预生成的参数覆盖

#### Scenario: 新字段落进素材包

- **WHEN** 某章场景卡填了权重「高」、爽点填了「info·主角获知仇人身份」、章末落点填了「拿到半张地图，更不安」
- **THEN** 素材包中对应内容存在，润色产物能引用它们

#### Scenario: 字段留空不产生占位符

- **WHEN** 某章的爽点、章末落点、文风例句全部留空
- **THEN** 素材包与润色产物中无这些字段的位置，也不出现 `{role}`、`{}` 类占位符文本

#### Scenario: 本章引入的伏笔被排除

- **WHEN** 某伏笔的 introduced_chapter_id 等于正在写作的章 id
- **THEN** 该伏笔不出现在本章素材包的伏笔块中；其他活跃伏笔照常注入

#### Scenario: 已收束与废弃伏笔不注入

- **WHEN** 某伏笔 status 为 resolved 或 abandoned
- **THEN** 该伏笔不出现在素材包伏笔块中（mentioned_in_chapter_id 仅作归档留痕，不参与注入判定）

#### Scenario: 本章计划收束的伏笔被点名

- **WHEN** 某活跃伏笔 planned_chapter_id 等于当前写作章 id
- **THEN** 该伏笔注入行带「建议本章收束」标记；其他活跃伏笔不带
