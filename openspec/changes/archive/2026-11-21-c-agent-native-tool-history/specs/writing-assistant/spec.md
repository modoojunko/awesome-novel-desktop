## MODIFIED Requirements

### Requirement: agent 循环为多步工具调用且受护栏约束

助手 SHALL 由 agent 循环驱动：解析作家输入为一次多步执行（读书→调工具→再思考→产出），支持工具调用与叙述文本交错、一次执行产出多张产物卡。循环 SHALL 采用标准 harness 范式双模式：

- **原生模式（主路径）**：工具以 JSON Schema 声明参数并经供应商原生 function calling 调用——模型返回结构化 tool_calls，助手执行后以 tool 结果消息回填，循环至模型自然收口
- **文本协议模式（降级路径）**：供应商/模型不支持原生 function calling 时，降级为文本协议（模型每步输出动作 JSON，解析器＋抢救函数承接）；降级路径 SHALL 保留且可按供应商能力矩阵自动路由

两模式 SHALL 同构：护栏（单回合墙钟上限（env 可覆盖）与作家的停止操作；SHALL NOT 设步数或工具调用次数上限）、调度纪律（risk_level 并行策略）、授权梯度（write_gate）、压缩行为（工具结果优先牺牲）逐项一致。到墙钟 SHALL 以明确的收尾话术结束并保留已产出的卡。循环内每个工具调用 SHALL 实时上报（开始/结束/摘要），完成后折叠为可展开回看的运行轨迹，且轨迹只展示真实发生的工具步。

**原生工具历史完整性（同一 run 多步）**：请求携带 tools 时，循环内历史 assistant 行的 `tool_calls` 与 tool 结果行的 `tool_call_id` SHALL 原样回传；DeepSeek openai 协议另须把每步 `reasoning_content` 挂回该 assistant 行（有工具调用的行与最终收口行都挂）——即使该步未实际调用工具也要回传，漏回传端点返回 400。非 DeepSeek vendor SHALL NOT 被附加该字段（避免未知字段被拒）。跨轮历史 SHALL 继续按既有 user/assistant 文本投影（无 tool_calls）；DeepSeek 原生跨轮在 native 转写持久化落地前不保证可用，能力矩阵 SHALL NOT 默认路由 DeepSeek native（env 强制仅用于诊断）。文本协议不带 tools，思考内容 SHALL NOT 进入外发窗口（仍只用于 UI 过程回看）。

工具执行 SHALL 以结构化结果回填：失败归一为失败结果（ok=false＋人话摘要）回填循环，SHALL NOT 以异常穿透执行层或断流。给模型看的结果摘要与给人看的产物卡 SHALL 职责分离，用户可见侧车元数据 SHALL 走 `_display` 键（模型不可见）。生成类工具的结果摘要 SHALL 含「已交付＋任务完成」收口语义，SHALL NOT 诱导模型原地重跑。循环 SHALL 对连续同工具同参数的调用去重劝退（不执行、回喂）。

#### Scenario: 多步串联
- **WHEN** 作家说「先看看我的主线，再给我出个能激化冲突的反派」
- **THEN** 助手依次执行读取主线、发散起草反派（两步以上），轨迹逐行点亮后折叠，产物为可过目的角色草案卡

#### Scenario: 执行异常归一
- **WHEN** 工具执行抛出异常
- **THEN** 循环归一为失败结果（ok=false＋人话摘要）回填，SHALL NOT 断流

#### Scenario: 生成工具摘要收口
- **WHEN** 抽卡/推演/盘点类工具完成
- **THEN** 摘要带「已交付＋本轮完成」，SHALL NOT 诱导模型原地重跑

#### Scenario: 连续同参调用劝退
- **WHEN** 模型连续发起同工具同参数的调用
- **THEN** 第二次不执行，回喂去重话术（产物已交付——收口或换做法）

#### Scenario: 墙钟到点收尾
- **WHEN** 一次执行到达单回合墙钟（长任务多步仍未收口）
- **THEN** 助手以收尾话术说明已完成部分，已产出卡保留可用；作家可随时点停止中断

#### Scenario: 原生模式结构化调用
- **WHEN** 供应商支持原生 function calling 且能力矩阵路由到原生模式
- **THEN** 模型返回结构化 tool_calls，助手无需文本解析/抢救即执行工具并回填结果，多步循环至收口

#### Scenario: 原生工具历史完整回传
- **WHEN** 原生模式同一 run 的第二步请求携带 tools 与第一步的工具调用
- **THEN** 历史 assistant 行携带 tool_calls、tool 结果行携带 tool_call_id；DeepSeek 还携带该步 reasoning_content，端点不因历史残缺返回 400

#### Scenario: 降级路径自动路由
- **WHEN** 供应商/模型不支持原生 function calling（能力矩阵判定）
- **THEN** 循环自动路由到文本协议模式，行为与一期一致（解析＋抢救＋纠错重试），作家无感知差异
