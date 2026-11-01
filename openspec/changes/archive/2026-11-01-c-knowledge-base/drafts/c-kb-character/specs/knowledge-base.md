## ADDED Requirements

### Requirement: 挑原型建卡
新建角色时可从知识库「角色设定」条目挑一个原型，payload 逐格复制进新卡：archetype＝persona 一句；档案格 look/background/speech；认知格 w1/s1/v1。relation_slot/arc 不进建卡预填。

#### Scenario: 原型逐格复制
- **WHEN** 作家在角色列表点「挑原型」并选中一条
- **THEN** 新卡以原型字段预填创建（无格不落空键），名字留空由作家起
- **AND** 首卡默认「主角」规则与手动添加一致

#### Scenario: 原型列表为空
- **WHEN** 知识库还没有角色设定条目
- **THEN** 弹窗给空态，指引去知识库手录或从拆书收进来

### Requirement: 用作原型计数
一条原型被用作建卡后，账号级使用计数累加（KbPref.adopt_count）；计数回写失败不影响建卡。

#### Scenario: 计数累加
- **WHEN** 同一条原型被用作建卡两次
- **THEN** adopt_count 从 1 累加到 2
- **WHEN** 计数接口失败
- **THEN** 建卡照常成功，无报错打扰
