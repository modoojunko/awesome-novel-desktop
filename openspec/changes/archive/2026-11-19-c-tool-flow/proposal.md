# c-tool-flow 方案：对话式触发调用工具的流程整理

## Why

boss 拍板（2026-11-16）：「整理下这种对话式触发调用工具的流程，而不是碰到某个固定的话，调用以前调用的大模型的代码」，并指名参考 openworker。

现状审计（33 工具按实现形态分布）：

| 形态 | 数量 | 问题 |
|---|---|---|
| 纯读封装（store/db 直读） | 11 | 干净 |
| 自含 AI 提示词（工具内自拼 prompt＋自调模型＋自解析） | 12 | 各写各的：建 client、裁 JSON、组卡面全是手搓副本 |
| 调 *_core 服务核 | 7 | 核是端点形状（Depends 占位＋HTTPException＋面板表单 body）——工具要伪造面板快照喂它（如 CastReviewBody＝盘点面板的表单，工具只能传空壳） |
| 直调端点 handler | 3（fleet 推演/抽卡/盘点） | 最糙：直接调路由函数 |

另有**触发层靠固定话术**：chips 发死句子（「给我抽三张剧情提案卡。」），流程成立依赖模型把这句话匹配到工具——这是意图字符串匹配的老路，不是 agent 路。抽卡重复 3 次的病灶（模型自触发重抽）本质就是「话术驱动、无确定性收口」的衍生症状。

## 方案总览（对齐 openworker 工具体系）

参考：`openworker/coworker/tools/registry.py`（ToolSpec/ToolRegistry）、`tools/*.py`（域模块工厂）、`engine.py`（执行/权限/结果回填分离）。

```
┌─ 触发层 ──────────────────────────────────────────┐
│ chips＝结构化意图 {tool, args}（不再是死句子）      │
│ 作家自由输入＝纯 agentic（域收敛目录内模型自选）     │
├─ 决策层（harness 已就位）──────────────────────────┤
│ agent 循环：域收敛目录下发 → 模型决策 → 授权(write_gate)│
│ → 执行 → 结果回填 → 收口；去重守卫/域外引导/墙钟     │
├─ 能力核层（本 change 新建）────────────────────────┤
│ capabilities/<域>.py：纯函数核，干净 dataclass 入参  │
│ 与结果；大模型管线细节私有在核内                     │
│ HTTP 端点（面板）与 agent 工具同调一层——单源        │
└───────────────────────────────────────────────────┘
```

### D1 ToolSpec 执行契约对齐 openworker

- **声明与执行分离**：Tool（声明：name/描述/JSON Schema/风险档）保持现状；执行函数统一**返回 dict 契约**——成功 `{"<内容键>": …}`、失败 `{"error": …}`，不再 raise 穿透（引擎兜 `{"error", "error_type"}`，openworker `_execute_sync` 同款）
- **`_display` 侧车键对齐**：模型不可见、只给人看的元数据（apiCalls/计数）走 payload 的 `_display` 键（openworker `_record_result` 同款语义；我们 apiCalls 已是此思路，收敛成规范）
- **Schema 生成**：保留手写 JSON Schema（我们的 schema 含中文描述与枚举，aisuite 的 docstring 自动生成不适配中文契约）——只对齐「schema 即模型契约」的原则

### D2 域模块工厂（依赖注入，替代全局捞）

工具按域分模块 `assistant/caps/<域>.py`，每模块导出工厂 `chapter_tools(deps) -> list[Tool]`（openworker `file_tools(workspace, roots)` 同款）：DB 会话/书上下文/画像等依赖闭包注入，工具体内不再全局捞。注册表（tools.py 尾单向聚合）不变。

### D3 能力核层（消灭「调用以前的大模型代码」）

`capabilities/<域>.py`：把现在散在端点里的大模型管线（plot_simulate/cast_ai_draw/cast_ai_review/generate_field/run_hooks_ai/intro_ai/volume_options/expand/chapter_directions/plot 清单/arc/consistency）抽成**纯能力函数**：

- 入参：dataclass params（业务语义：章 ref/线/排除项…，不再是面板表单快照）
- 出参：dataclass CapabilityResult（结构化内容＋人话 text）
- 大模型调用/解析/重试/门槛校验私有在核内；HTTP 端点（面板 UI）与 agent 工具同调一层——面板和对话是同一能力的两个皮

### D4 chips 结构化触发（消灭固定话术依赖）

chip 定义从 `{label, command}` 改 `{label, tool, args}`；点击后 dock 照常把 label 作为意图句发进对话（记录可读），**同时带 `tool_hint: {tool, args}`**——循环首步确定性执行该工具（跳过「模型猜话术」一跳），结果回填后模型接管（解读/续做/收口）。自由输入不带 hint，全 agentic。tool_hint 只作首步锚点，域校验/授权/去重守卫全部照走。

### D5 流程规则上墙（已修的守卫进基座）

连续同参去重、域外引导、产物人话 draft、收口话术——这四条本次已修的规则随 D1 基座固化为契约条款＋测试，不再散落在单点修复里。

## Migration Plan

1. **批1 基座**：Tool 执行契约（dict 返回＋_display 规范）＋caps 目录骨架＋一个样板域（chapter：拆下一章/本章剧情/体检三工具迁 caps）
2. **批2 chips 结构化**：chatRegistry chip 加 tool/args；dock 发 tool_hint；loop 首步直执行；e2e 断言「点 chip＝确定性首步」
3. **批3 能力核抽取·章纲域**：plot_simulate/chapter_directions/chapter_plot/consistency 核入 caps/chapter.py；端点与工具同调；面板表单 body 在端点层装配
4. **批4 能力核抽取·设定/卷纲域**：generate_field/hooks/intro/volume_options/expand/arc 核入 caps
5. **批5 自含 AI 提示词工具统一**：12 个手搓 prompt 工具收敛到统一 AI 调用帮手（建 client/裁 JSON/组卡一套）
6. **批6 走查**：chips 全点一遍（确定性首步＋产物人话）＋自由输入回归

## Non-Goals

- 不改 harness 双模式/native FC 通道（决策层已就位）
- 不动 write_gate/线程模型/压缩
- 面板 UI 不退役（同一能力的另一张皮；Rail 侧保持）

## Impact

- 受影响：C端 assistant 工具层＋chips 前端；S端零
- 风险：核抽取动端点（面板回归面）——按域小批迁＋每批 e2e
- 测试：caps 纯函数直测（不再 HTTP 路径）＋chips 结构化意图 e2e＋既有 33 工具契约测试迁移
