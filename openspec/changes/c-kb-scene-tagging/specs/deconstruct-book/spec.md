## ADDED Requirements

### Requirement: 拆书产出适用条件（when）

拆书文风产出（`deconstruct_style`）的 `rules` 与 `craft` 条目 SHALL 可选携带适用条件：`scene`（场面）与 `emotion`（情绪），值 SHALL 取既有封闭词表（`SCENES` / `EMOTIONS`）；判不出、或规则换到别的场面也成立时 SHALL 留空，SHALL NOT 为凑字段硬填「日常」。`role` 与 `examples` SHALL NOT 携带适用条件（叙述身份与示范段为全书恒定）。章位（`chapter_pos`）本轮不产：拆书材料没有卷边界，无法可靠判定。

拆书技法产出（`deconstruct_techniques`）的 `techniques` 卡 SHALL 可选携带 `scene`；与 `kind`（打法类型）是两个维度，SHALL NOT 互相串填。

拆书归并（`deconstruct_reduce`）SHALL 把 `scene` / `emotion` 视为已登记字段随条目保留；两条规则的适用条件不一致（含一条有、一条无）时 SHALL 保留两条，SHALL NOT 合并、取并集，也 SHALL NOT 把条件括注进 `name`。

入库 SHALL 把条目级适用条件写入 `when_json`；为空时不写（保持 `{}`）。仅写法类条目（文风/文笔/手法）可带适用条件；世界设定与角色设定 SHALL NOT 携带。

#### Scenario: 文风条目带场景

- **WHEN** 拆书文风产出中一条「对峙用短句」的规则，材料能判定专用于对峙场面
- **THEN** 条目携带 `scene: "对峙"`，入库后 `when_json` 非空，`scope` 读时推导为 scene

#### Scenario: 判不出留空

- **WHEN** 一条文笔规则换到别的场面也成立、或材料无法判定其专用于某场面
- **THEN** 条目不带适用条件（或为空对象），SHALL NOT 硬填「日常」或其他默认值

#### Scenario: 归并保留不同条件的规则

- **WHEN** 同一规则在两张卡片里分别标注 `scene: "对峙"` 与 `scene: "打斗"`
- **THEN** 归并后保留两条，各带自己的适用条件；SHALL NOT 合成一条、不取并集、不把条件括注进 name

#### Scenario: 技法卡的 scene 与 kind 分离

- **WHEN** 拆书技法卡同时有 `kind` 与 `scene`
- **THEN** `kind` 只取五类打法（大招/体术/兵器/异能/群战），`scene` 只取七个场面词；`scene` 不写「群战」、`kind` 不写「打斗」

#### Scenario: 世界与角色不携带适用条件

- **WHEN** 拆书产出世界设定或角色设定条目
- **THEN** 该条目 SHALL NOT 携带适用条件；入库闸拒绝时按既有错误码返回
