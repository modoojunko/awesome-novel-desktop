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

## 附录：spike 实测结论（2026-11-16，走查栈真 GLM，tasks 1.1/1.2 收口）

- 端点：`open.bigmodel.cn/api/coding/paas/v4`（openai 兼容）＋ `glm-5.3-flash`，`tools` 参数原生支持
- ①单工具调用 **PASS**：finish=tool_calls；中文参数（书名「血夜三案」/题材「西式奇幻」）无编码问题；arguments 合法 JSON
- ②多步串联 **PASS**：工具结果回填后连续 2 次调用后自然收口（finish=stop＋正文答案）
- ③中文长文本参数 **PASS**：429 字中文正文完整保真传入 content 参数（截断/转义零损伤）
- **判定：三场景全过→native 全量可切**（无部分服从边界需记录）
- 实现注意：①`reasoning_content` 与 `tool_calls` 并行流出（思考流 145~1323 字/轮）——native 分支须把 reasoning 映射成 thinking 事件（D4 既有口径）；②流式增量按 index 聚合 tool_calls（name/arguments 分片拼接）；③finish_reason 原生语义（tool_calls/stop）可直接当步边界
- spike 脚本：`/tmp/fc_spike.py`（docker cp 进走查容器跑；GLM 配置自走查库 api_configs 行＋app_meta fernet_key 解密）

## 附录二：走查清单收口实录（2026-11-16，tasks 6.1-6.4）

- **6.1 真 GLM native 全链 ✓**：read_progress→read_chapter 两步原生 tool_calls 驱动＋settings_og_fill 的 apiCalls 全可见（op/model/ms/tokens/ok）＋思考回看 41 个 thinking 事件到 SSE；书绑 GLM 临时切换实测后还原
- **6.2 降级路径 ✓**：走查书实际绑定 deepseek-v4.1-flash（opencode 网关，vendor 白名单外）——同一批指令全程文本协议路径行为一致（步/叙述/产物卡/收口），降级即默认路径真机长跑
- **6.3 停止/断开 ✓**：断开 6s→25s 内定稿落库（占位文案＋已产出 tool 行保留）——**定诊并根修两处**：①router 消费挪自管 drive task（starlette 1.9 断开既不迭代也不关闭 SSE 生成器→streaming 悬行）；②drive 用自有短会话（请求级 db 随断开即死，后台定稿拿到死会话）；loop.run 补 CancelledError 对称处理
- **6.4 dock 回归 ✓**：chat-dock e2e 14/15（唯一挂＝③stale 二版标注，stash 实证 2026-11-15 前存量，非本 change 回归，挂账）

### 定诊判例（走查清单期间三连）

1. **GLM 顶层 reasoning_effort 吞思考流**：`{"thinking":{enabled}, "reasoning_effort":low}` 扁平形态被 coding 端点静默吞 reasoning_content（不报错、工具照常）；嵌套 `{"thinking":{enabled, reasoning_effort}}` 才照常流。探针矩阵四形态对照定诊；**vendor 分叉修复**（glm 嵌套/方舟等保持 2026-10-24 实证扁平）；FORCED「关」路径保持扁平（吞流恰好贴合最接近关语义）
2. **router thinking 从批 A 起就没发 SSE**：`if etype == "thinking": continue` 把实时思考回看全灭（前端整套 thinkingText 渲染是死路）——改照发 SSE、落盘分支本就不匹配
3. **openai-compat 白名单误纳**：通用自配兜底 vendor 形态未知，桩模型文本动作 JSON 被当自然收口直灌 narration（e2e 全链 5 用例全灭）——白名单收缩到实测验证 vendor（glm/openai），fail-safe 钉子入库
