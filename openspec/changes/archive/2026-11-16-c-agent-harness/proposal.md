# c-agent-harness：写作助手 Agent 迁移标准 harness 范式

## Why

一期 agent 是自研文本协议：每步让模型吐 JSON 字符串，由解析器＋三级抢救＋纠错重试承接。这条链路能用，但：

- **自研协议维护成本高**——小模型格式漂移就要打抢救补丁；业界（Claude Code/ZCode/openworker）全部走供应商原生 tool calling，模型直接返回结构化调用，格式服从度由供应商保障
- **工具定义无机器可校验的参数 schema**——dataclass＋文字 args_hint，参数错误只能运行时撞 TypeError
- **调度语义散落在 loop 内**——risk_level 并行策略、停止收尾、压缩信号等刚从 openworker 对齐的纪律，缺一个正式的 harness 层承载

boss 拍板（2026-11-15）：agent 要定义标准 harness 范式——原生工具调用为主、文本协议降级兜底、工具定义标准化（ToolSpec/JSON Schema）、循环标准化（openworker 同构）。

## What Changes

- **ToolSpec 标准化**：Tool dataclass 增 parameters（JSON Schema）字段；29 个工具迁移出机器可校验参数定义；协议模板的 args_hint 由 schema 派生
- **供应商适配层**：ai_client 增原生 function calling 支持（GLM 主推能力）；按供应商/模型能力矩阵路由——支持原生 FC 的走新链路，不支持的降级现有文本协议（解析器＋抢救函数保留为降级路径）
- **循环双模式**：AgentLoop 增 native 模式（model 返回结构化 tool_calls → 授权 → 执行 → 结果回填）；文本协议模式保留为降级。调度纪律（risk_level 并行策略、停止落库收尾、COMPACTING 信号、墙钟护栏）两模式同构
- **事件契约不变**：SSE 词表与 dock UI 零改动（执行层替换，呈现层不动）
- **能力围栏不变**：封闭注册表语义保持；工具清单不增不减（纯范式迁移）

## Design Impact

- 受影响端：C端 only（S端 零改动）
- 受影响屏/弹层：无新增屏/弹层——dock 呈现层零改动（SSE 事件契约不变）
- 对象状态：无新增用户可见状态；复用既有 info/ok/warn/err 语气词表
- 两端共享段：不触碰
- 原型先行：不需要（执行层范式迁移，无新 UI；供应商 FC 服从度用 spike 实测代替原型）
- 设计工件：实现侧自查（本 change 无用户可见界面改动，走查清单 B 段回归覆盖）

## Capabilities

### 修改
- `specs/writing-assistant/spec.md`——§执行循环：增「原生工具调用为主路径、文本协议为降级路径」的范式条款与降级 Scenario；§工具注册表：工具 SHALL 以 JSON Schema 声明参数

## Impact

- 不影响：dock UI、线程模型、write_gate 授权梯度、压缩、能力围栏、事件契约
- 风险：GLM 原生 function calling 格式服从度——spike 实测先行（一期避开的遗留疑虑，原生 FC 是 GLM 主推能力，风险可控）；文本协议降级路径保底
- 测试迁移：loop/golden 测试重写为原生调用口径（fake client 返回结构化 tool_calls）
