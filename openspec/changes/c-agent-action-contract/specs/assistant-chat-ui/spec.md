# c-agent-action-contract 变更：assistant-chat-ui

## MODIFIED Requirements

### Requirement: 全模型逐字流式

所有模型的助手回复 SHALL 逐字流式呈现：原生 FC 模型走既有 narration_delta 增量链；文本协议模型的回复 SHALL 经流式解析增量抽取叙述段逐字交付，SHALL NOT 整段等待完成后一次性显示；协议 JSON 壳 SHALL NOT 裸露给作家（deepseek 裸 JSON 回复教训）。协议壳的定义 SHALL 覆盖哨兵分节、整段单 JSON、以及无哨兵但含 `"action"`／`"tool"`／`"args"` 键的裸片段；命中任一形态 SHALL 在流式阶段冻结，SHALL NOT 作为叙述增量流出。回合收口 SHALL 只交付清理后的叙述；清理后无叙述则交付明确失败话术。坏片段 SHALL NOT 写回会话历史或在回放中重现。流式路径解析失败 SHALL 静默降级为整段交付（narration 兜底事件已消费），SHALL NOT 白屏或重复拼接。

#### Scenario: 文本协议模型逐字出字

- **WHEN** 作家选用 deepseek 等文本协议模型发起对话
- **THEN** 回复随生成逐字上屏，全程看不到协议 JSON 片段

#### Scenario: 流式解析失败降级

- **WHEN** 文本协议流式解析中途失败
- **THEN** 该回合降级为整段交付一次显示，已流出内容不重复拼接

#### Scenario: 无哨兵裸片段不流给作家

- **WHEN** 模型输出无哨兵、以引号开头的 `"action": ...` 裸片段
- **THEN** 该片段不在气泡中逐字出现；收口只显示清理后的叙述或明确失败话术，重开历史也看不到坏片段

## ADDED Requirements

### Requirement: 任务计划卡呈现与恢复

dock SHALL 在对话流内渲染任务计划卡，数据来自服务端 `plan` 事件快照（SHALL NOT 以文本占位或假进度替代）。计划卡 SHALL 包含人话标题与逐项清单，每项按 §5 状态语言呈现四态：未开始（未填／中性）、在做（进行中／warn）、做完（已确认／ok）、没做成（阻断缺项／err，仅当该件是作家点名的交付物）。

计划卡 SHALL 在执行中实时更新，收口后保留可回看；存在未完成项时 SHALL 明示「还有 N 件没做」。切页签返回或应用重启 SHALL 按落盘快照恢复最近计划与状态。计划卡 SHALL NOT 新增胶囊形态、语气词或第四种状态色；按钮文案 SHALL 使用动词。计划卡 SHALL 挂在当前回合的轨迹组内或其上方，不单独占用一条消息气泡。

#### Scenario: 多件事计划卡实时更新

- **WHEN** 作家一条消息提出三件交付物且助手建立计划
- **THEN** dock 出现三项计划卡，执行中各项状态实时变化，收口后卡保留

#### Scenario: 未完成项如实呈现

- **WHEN** 三件中只完成两件
- **THEN** 计划卡明示「还有 1 件没做」，已完成项显示做完态，不出现全部完成的假象

#### Scenario: 恢复计划

- **WHEN** 执行中途重开会话或切走页签再切回
- **THEN** 计划卡按落盘快照恢复最近状态，未完成项仍可见

#### Scenario: 失败不伪装完成

- **WHEN** 某一步执行失败
- **THEN** 对应项显示没做成（err 仅在阻断作家点名交付物时使用），SHALL NOT 显示做完
