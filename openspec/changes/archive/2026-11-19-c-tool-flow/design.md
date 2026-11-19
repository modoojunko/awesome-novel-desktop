# c-tool-flow 设计：对话式触发调用工具的流程整理（参考 openworker）

## Context

boss 拍板：整理「对话式触发调用工具」的流程——不能是「碰到固定的话→调以前的大模型代码」。现状审计：33 工具三种实现形态（11 纯读封装／12 自含 AI 提示词／7 调端点形状核／3 直调路由 handler），触发层靠 chips 死句子，模型靠话术匹配选工具。参考体系：**openworker（MIT）coworker/tools/registry.py＋tools/*.py＋engine.py**——本项目 harness 的压缩/调度纪律即移植自它，本次把工具体系也按同源对齐。

## openworker 对标点（逐条带出处）

| openworker | 本项目现状 | 采纳方式 |
|---|---|---|
| `ToolSpec{name, schema, func, metadata}`＋`ToolRegistry.register/schemas/execute`（tools/registry.py:15-63） | Tool dataclass＋TOOL_REGISTRY（已有，同构） | 骨架不动；**执行函数契约对齐**（见 D1） |
| schema 自动生成（aisuite docstring→JSON Schema）＋`__coworker_schema__` 手写覆盖（registry.py:44-49） | 全手写 JSON Schema（中文描述/枚举必要） | 只对齐原则「schema 即模型契约」，不引 aisuite |
| 工具＝普通函数＋docstring＝模型契约＋**返回 dict**（`{"error": …}` 而非 raise；files.py read_file 全程示范） | 混合式：有的 raise HTTPException 穿透、有的 ToolResult | **D1 统一 dict 契约**（引擎兜 error 归一） |
| **依赖注入工厂**：`file_tools(workspace, roots) -> [read_file]` 闭包绑依赖（files.py:50-126）；agent.py 按域 wire | 工具体内全局捞 DB/async_session/画像 | **D2 域模块工厂** caps/<域>.py |
| **权限不在注册表**：PermissionEngine 由 turn engine 逐调用应用（registry.py 头注；engine.py approval 段） | write_gate gate_fn 由 loop 逐调用应用（已同构） | 不动；写进基座契约条款 |
| 结果侧车：`_display` 键＝用户可见、**agent 不可见**（engine.py `_record_result` 尾注） | apiCalls 已走 step_end 事件不入模型历史（思路同，未成文） | **D1 收敛成规范** |
| 端点/CLI/UI 同过一层能力（registry 单源） | 端点面板与 agent 工具各调各的（核形状端点化） | **D3 能力核层 caps/** 单源 |
| 模型自由输入决策（无固定话术触发） | chips 死句子＝事实上的触发 API | **D4 chips 结构化意图** |

## 架构决策

### D1 Tool 执行契约（对齐 openworker `_execute_sync`）
执行函数返回 dict：成功 `{"<内容键>": …}`、失败 `{"error": str, "error_type": str}`——执行函数 **不再 raise 穿透**（loop 兜异常归一为 error 结果，openworker 同款）。`_display` 键规范：payload 上的 `_display`＝只给人看的侧车（模型不可见）——apiCalls/去重计数/域标签计数迁入。ToolResult 的 summary（给模型的话）与 card.payload（给人看的卡）职责写死进契约注释。

### D2 域模块工厂（openworker `file_tools` 模式）
`assistant/caps/<域>.py` 各导出 `xxx_tools(deps) -> list[Tool]`；deps＝{db 会话工厂, 书上下文, 画像句柄}。tools.py 聚合不变（域工厂返回后并注册表）。好处：依赖显式、测试可注 fake deps、域内聚。

### D3 能力核层（本 change 的主体工程）
现状两类核：
- **端点形状核**（plot_simulate/cast_ai_draw/cast_ai_review…）：Depends 占位＋HTTPException＋面板表单 body——工具伪造表单喂它＝「调以前的大模型代码」的直接来源
- **自含 AI 提示词工具**：12 个工具各自手搓 client/prompt/parse

整理为 `capabilities/<域>.py` 纯能力函数：`params(dataclass) -> CapabilityResult(dataclass: 内容结构化 + 人话 text)`；大模型调用/裁 JSON/重试/门槛校验私有在核内。**HTTP 端点与 agent 工具同调 caps**——面板与对话是同一能力的两张皮（单源，openworker registry 单源同理）。第一批样板：章纲域（plot_simulate/chapter_directions/chapter_plot/consistency）。

### D4 chips 结构化触发（消灭固定话术）
chip `{label, tool, args}`：点击后 dock 发「意图句（label，进对话记录可读）＋`tool_hint{tool,args}`（结构化）」；loop 收到 hint＝**首步确定性执行**（域校验→授权→去重守卫全部照走），结果回填后模型接管（解读/续做/收口）。作家自由输入无 hint——全 agentic。固定话术从此只是「给人看的示意」，不是流程依赖。

### D5 流程规则固化
已修四规则随基座成契约：连续同参去重（劝退回喂）、域外引导、产物人话 draft（禁裸 JSON）、收口话术（生成类工具摘要必须带「已交付＋任务完成」）——各自配契约测试，不再单点补丁。

## Risks / Trade-offs

- 核抽取动端点＝面板回归面——按域小批迁＋每批面板 e2e
- tool_hint 首步直执行跳过模型首跳判断——域校验/授权/去重仍全程，模型在结果后接管；误点 chip 的代价＝一次工具执行（多数只读/产卡，可撤销口径不变）
- 12 个自含 prompt 工具统一帮手可能磨平个别工具的特化解析——帮手留 per-tool 钩子

## Migration Plan

见 tasks.md 六批（基座→chips 结构化→章纲核→设定/卷纲核→自含统一→走查归档）。每批独立可验收、可独立合入。

## Open Questions

- `_display` 键名与既有 apiCalls 事件字段的关系（迁移期双写还是直接改键）——批1 定
- cast_ai_review 的表单快照语义（面板 3s 自动保存未落库的输入）在工具侧的等价物（章节真值 vs 面板所见）——批3 与走查定
