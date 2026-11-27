## ADDED Requirements

### Requirement: 存量写法条目的适用条件回标与场景贯通

系统 SHALL 对存量全书级（`when_json` 为空）的文风/文笔条目执行一次性适用条件回标：按条目 `instruction` 语义与既有封闭词表判定 `scene` / `emotion` / `chapter_pos`；只标 `rules` 与 `craft` 类条目，`role` 与 `sample` 类 SHALL 保持全书级（叙述身份与示范段不随场面变化）。

回标 SHALL NOT 触碰世界设定、角色设定、情节与用户书级副本；SHALL NOT 修改条目标题与正文，只补 `when_json`。回标结果 SHALL 经人工抽检（每题材抽样，标准＝场景判定可复述、无明显错标）后随基线下一个版本发布；版本目录只增不改，旧版本保留可回滚。

回标后基线条目中 `scope=scene` 的文风/文笔条目 SHALL 大于 0，使写章候选的 style 组不再恒空；老客户端读不懂新增字段时 SHALL 跳过该条并按既有向前兼容口径继续读其余条目。

#### Scenario: 回标产出场景条目

- **WHEN** 回标任务处理一条「对峙/僵持时用短句清点资源」的文笔规则
- **THEN** 该条目标注 `scene: 对峙`（或等价封闭值），入库后 `scope=scene`，写章候选 style 组可见

#### Scenario: 全书恒定类保持 base

- **WHEN** 条目为文风 `role`（叙事身份）或 `sample`（示范段）
- **THEN** 回标 SHALL NOT 给它加 `when`，`scope` 保持 base

#### Scenario: 世界角色不参与

- **WHEN** 回标扫描到世界设定或角色设定条目
- **THEN** 直接跳过，`when_json` 与正文均不变

#### Scenario: 抽检不过不发布

- **WHEN** 某题材抽检发现场景判定不可复述或明显错标超过约定阈值
- **THEN** 该题材回标结果不进入新基线版本，修正后重跑
