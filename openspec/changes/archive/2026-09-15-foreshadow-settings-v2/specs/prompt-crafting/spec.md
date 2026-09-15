# prompt-crafting 变更（增量）

## MODIFIED Requirements

### Requirement: 素材包确定性组装

- 系统 SHALL 从数据库确定性组装「素材包」供润色消费，来源覆盖：文风设定（含 few_shot 例句）、题材注入段、世界观、反 AI 规则、故事前提、卷概要、章纲全字段（关键点、场景卡含 weight/focus、读者获得 micro_payoffs、章末落点 ladder_exit、情绪设计、payoff 三分类、信息差）、出场角色状态、活跃伏笔。
- 活跃伏笔块 SHALL 只注入 status==active 的伏笔行（真表 `novel_hooks`）；「排除本章引入」SHALL 按 introduced_chapter_id 与当前章 id 相等判断（替代 ref 字符串比较）。
- 裁剪预算：世界观注入 SHALL ≤600 字；活跃伏笔 SHALL ≤8 条；出场角色 SHALL ≤5 人。
- 伏笔块 SHALL 展示编号（#H-#### 派生自 seq）与描述；优先级 SHALL 以「高/中/低」口径注入（存储 Integer 1/2/3，映射唯一），非法值 SHALL 丢弃该标注而非静默吞错。
- 未填字段 SHALL 跳过对应内容，SHALL NOT 向提示词注入 `{...}` 等未替换占位符。

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
