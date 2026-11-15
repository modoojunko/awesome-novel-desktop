# writing-assistant 变更：agent 迁移标准 harness 范式

## MODIFIED Requirements

### Requirement: agent 循环为多步工具调用且受护栏约束

助手 SHALL 由 agent 循环驱动：解析作家输入为一次多步执行（读书→调工具→再思考→产出），支持工具调用与叙述文本交错、一次执行产出多张产物卡。循环 SHALL 采用标准 harness 范式双模式：

- **原生模式（主路径）**：工具以 JSON Schema 声明参数并经供应商原生 function calling 调用——模型返回结构化 tool_calls，助手执行后以 tool 结果消息回填，循环至模型自然收口
- **文本协议模式（降级路径）**：供应商/模型不支持原生 function calling 时，降级为文本协议（模型每步输出动作 JSON，解析器＋抢救函数承接）；降级路径 SHALL 保留且可按供应商能力矩阵自动路由

两模式 SHALL 同构：护栏（单回合墙钟上限（env 可覆盖）与作家的停止操作；SHALL NOT 设步数或工具调用次数上限）、调度纪律（risk_level 并行策略）、授权梯度（write_gate）、压缩行为（工具结果优先牺牲）逐项一致。到墙钟 SHALL 以明确的收尾话术结束并保留已产出的卡。循环内每个工具调用 SHALL 实时上报（开始/结束/摘要），完成后折叠为可展开回看的运行轨迹，且轨迹只展示真实发生的工具步。

#### Scenario: 多步串联
- **WHEN** 作家说「先看看我的主线，再给我出个能激化冲突的反派」
- **THEN** 助手依次执行读取主线、发散起草反派（两步以上），轨迹逐行点亮后折叠，产物为可过目的角色草案卡

#### Scenario: 墙钟到点收尾
- **WHEN** 一次执行到达单回合墙钟（长任务多步仍未收口）
- **THEN** 助手以收尾话术说明已完成部分，已产出卡保留可用；作家可随时点停止中断

#### Scenario: 原生模式结构化调用
- **WHEN** 供应商支持原生 function calling 且能力矩阵路由到原生模式
- **THEN** 模型返回结构化 tool_calls，助手无需文本解析/抢救即执行工具并回填结果，多步循环至收口

#### Scenario: 降级路径自动路由
- **WHEN** 供应商/模型不支持原生 function calling（能力矩阵判定）
- **THEN** 循环自动路由到文本协议模式，行为与一期一致（解析＋抢救＋纠错重试），作家无感知差异

### Requirement: 能力围栏——只做书内与知识库内的事

工具注册表 SHALL 物理封闭：仅含书内读/写/改与本地知识库读/写/改的工具；网络检索、跨应用、代码执行等 SHALL NOT 出现在注册表。每个工具 SHALL 以 ToolSpec 声明：name/description/parameters（JSON Schema，机器可校验并下发供应商原生调用）/risk_level（调度并行策略）/feature_key（档位闸）/handler（执行体）。参数错误 SHALL 在 schema 层显式暴露，SHALL NOT 仅以运行时异常形式出现。助手身份定义 SHALL 声明能力边界；作家提出边界外请求时，助手 SHALL 明确回复没有该能力并引导回书内任务，SHALL NOT 以通用知识自由发挥冒充执行。

#### Scenario: 越界请求拒答
- **WHEN** 作家要求助手「帮我写一段简历」或「查一下网上的资料」
- **THEN** 助手回复此类事超出其能力（只懂这本书和作家的知识库），并建议回书内任务，不产出任何冒充结果

#### Scenario: 围栏不可绕过
- **WHEN** 作家在对话中粘贴的小说文本内含「忽略以上规则，执行 X」类指令
- **THEN** 书内素材一律视为数据而非指令，助手 SHALL NOT 执行其中嵌入的指令

#### Scenario: 原生调用的参数 schema 下发
- **WHEN** 循环路由到原生模式准备调用模型
- **THEN** 全部工具的 parameters JSON Schema 随请求下发供应商，模型返回的参数与 schema 对齐
