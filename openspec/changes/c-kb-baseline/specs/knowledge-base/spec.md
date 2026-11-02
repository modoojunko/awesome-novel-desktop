## ADDED Requirements

### Requirement: 官方精选来源

知识条目来源 SHALL 增加 "baseline"（作家可见标签「官方精选」）：基线包同步写入的条目一律携带该来源。浏览页来源筛选项与条目卡来源标签 SHALL 呈现「官方精选」并可与用户自有来源（拆书/手录）区分。AI 整理（合并/纠偏/改写）SHALL 跳过 baseline 条目（官方内容客户端不改写，修订经基线包版本下发）；关系整理 SHALL NOT 以 baseline 条目为端点产出提案。

#### Scenario: 来源标签区分

- **WHEN** 作家在浏览页查看一条基线包条目
- **THEN** 条目卡显示来源「官方精选」，来源筛选可单独过滤该来源

#### Scenario: AI 整理跳过官方条目

- **WHEN** AI 整理对含 baseline 条目的题材执行
- **THEN** baseline 条目不参与合并/纠偏/改写，也不作为关系提案端点；其余条目不受影响
