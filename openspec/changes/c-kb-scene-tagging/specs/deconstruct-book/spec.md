## ADDED Requirements

### Requirement: 拆书产出适用条件（when）

拆书文风产出（`deconstruct_style`）的 `rules` 与 `craft` 条目 SHALL 可选携带 `when` 对象，键限 `scene` / `emotion` / `chapter_pos`，值 SHALL 取既有封闭词表（`SCENES` / `EMOTIONS` / `CHAPTER_POS`）；判不出 SHALL 留空，SHALL NOT 为凑字段硬填「日常」。`role` 与 `examples` SHALL NOT 携带 `when`（叙述身份与示范段为全书恒定）。

拆书技法产出（`deconstruct_techniques`）的 `techniques` 卡 SHALL 可选携带同一形状的 `when`。拆书归并（`deconstruct_condense`）SHALL 保留来源条目的 `when`；同一对象多来源冲突时 SHALL 取并集或降 `confidence` 为 low，SHALL NOT 静默丢弃。

入库 SHALL 把条目级 `when` 写入 `when_json`；`when` 为空时不写（保持 `{}`）。仅写法类条目（文风/文笔/手法）可带适用条件；世界设定与角色设定 SHALL NOT 携带。

#### Scenario: 文风条目带场景

- **WHEN** 拆书文风产出中一条「对峙用短句」的规则，材料能判定用于对峙场面
- **THEN** 条目携带 `when: {scene: "对峙"}`，入库后 `when_json` 非空，`scope` 读时推导为 scene

#### Scenario: 判不出留空

- **WHEN** 一条文笔规则无法从材料判定适用场面
- **THEN** 条目不带 `when`（或 `when` 为空对象），SHALL NOT 硬填「日常」或其他默认值

#### Scenario: 归并保留适用条件

- **WHEN** 同一规则在两张卡片里分别标注「对峙」与「打斗」
- **THEN** 归并条目保留两类场景（并集）或标 low 并注明分歧，SHALL NOT 只留一个而不说明

#### Scenario: 世界与角色不携带适用条件

- **WHEN** 拆书产出世界设定或角色设定条目
- **THEN** 该条目 SHALL NOT 携带 `when`；入库闸拒绝时按既有错误码返回
