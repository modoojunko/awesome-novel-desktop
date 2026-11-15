# c-agent-harness 设计：标准 harness 范式

## Context

一期自研文本协议（模型每步吐动作 JSON＋三级抢救＋纠错重试）已走查实证可用，但协议维护成本高、参数无 schema、与业界 agent 不同构。openworker 对账把调度纪律（risk_level 并行、停止落库、COMPACTING 信号、墙钟护栏）先对齐了——本 change 把执行层升级为标准 harness 范式：**原生 function calling 主路径＋文本协议降级**。

## Goals / Non-Goals

- Goals：原生 tool calling 主路径；ToolSpec（JSON Schema 参数）；双模式路由；事件契约/SSE 不变
- Non-Goals：不做 MCP 接入（二期评估）；不做多 agent 编排；不改能力围栏清单；不改 dock UI；不动线程模型与授权梯度

## 架构决策

### D1：双模式路由（供应商能力矩阵）
`ai_client` 增 `supports_native_tools(model) -> bool`——按模型/供应商查能力矩阵（GLM 原生 FC、openai 兼容系按 config 标注；未知默认降级文本协议）。`_stream_chat` 组装时查一次，选 `AgentLoop(harness="native"|"text")`。

- native：`client.chat_stream(messages, tools=schemas)`——供应商返回结构化 `tool_calls`；解析器不介入
- text：现路径原样（解析器＋抢救＋纠错重试保留）
- 判据：spike 实测 GLM 原生 FC 三轮服从度（多步＋参数含中文/长文本）通过才全量切；不过则保留 text 为主路径，harness 层照建（路由开关翻转即可用）

### D2：ToolSpec 迁移
Tool dataclass 增 `parameters: dict`（JSON Schema）。迁移策略：
- 读类 5 工具/写类/profile/kb/settings：参数少且已知——手写 schema（draft 式工具 field 白名单枚举进 schema enum）
- args_hint 文案由 schema 派生生成（协议模板 text 模式仍用）
- 校验：原生模式由供应商保障；text 模式解析后仍走现有 args 传递（不重复造校验器，TypeError 兜底保留）

### D3：循环双模式
`AgentLoop` 增 harness 分支。两模式共享：write_gate（授权梯度）、压缩（COMPACTING/COMPACTED/阈值/keep/重试）、墙钟、停止落库、线程落盘、apiCalls 归集与事件、TraceFolded steps 事件。native 分支循环：
```
while True:
  turn = await client.chat_stream(messages, tools=schemas)   # 结构化 tool_calls
  for tc in turn.tool_calls: 授权(write_gate) → 执行 → 结果消息回填（_display 侧车：apiCalls 不进模型历史）
  if not turn.tool_calls: 收口（answer）；
  墙钟检查 → 停止检查 → 压缩检查
```
文本协议分支＝现循环原样（含 while True 无步数上限、GeneratorExit 收尾）。

### D4：事件契约不动
SSE 词表零增删：run_start/step_start/step_end/thinking/narration/artifact/permission_required/gate/run_end/error/clear——native 模式把原生事件翻译成同词表（tool_calls→step_start/step_end；reasoning→thinking）。dock 零改动。

### D5：测试迁移
- FakeClient 增 native 形态（返回结构化 tool_calls 的 fake）
- loop 8 例拆双模式参数化（native/text 各跑一遍核心行为）
- golden 13 例：native 模式下 stub 直返 tool_calls（语义等价复验）；text 模式保持现断言
- 新增：路由测试（能力矩阵→模式选择）、降级切换测试

## Risks / Trade-offs

- GLM 原生 FC 服从度未知→spike 先行（多步＋中文参数＋长文本参数三场景）
- 双模式长期并存＝双倍测试面→能力矩阵稳定后评估 text 模式收缩（另立项）
- Depends 占位直调的端点核（generate_field 等）在 native 工具 handler 里沿用 tools_settings 既有模式

## Migration Plan

1. spike：GLM 原生 FC 服从度实测（独立分支，不进主链）
2. ToolSpec＋schema 迁移（29 工具）
3. ai_client 原生调用支持＋能力矩阵
4. AgentLoop native 分支＋路由
5. 测试迁移＋双模式参数化
6. 走查栈真 GLM 验证（多步/卡片/写回全链）

## Open Questions

- openrouter 兼容系供应商（openai-compat 自配 Key）原生 FC 支持度参差——能力矩阵初版按 vendor 白名单（glm/openai/anthropic 已知支持；其余默认 text）
