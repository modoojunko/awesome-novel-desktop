## Context

见 proposal.md — Why。设计相关现状：

- 文本协议 v2：`actions.py` 负责哨兵分节、旧版单 JSON 兼容、纯文本兜底；`loop.py` 负责流式冻结与 degraded 重试一次；原生 FC 模式走 tool_calls，不经过文本解析。
- 工具清单已由 `tool_catalog_text(thread)` 从注册表按域派生，注入 `assistant_act` 提示词模板；缺包时回落内置 `ACT_PROTOCOL`。
- 生成类工具统一返回 `ToolResult(card=...)`；`draft_arc` 返回 `{"value": ...}`，前端卡面只读（无采纳写回路径，写回要到主线面板）。
- 会话为 append-only JSONL；`role="event"` 行支持 `payload`／`card_kind`；历史接口原样返回行；旧前端对空 content 的 event 行直接跳过。
- SSE 事件为 `run_start/step_start/step_end/thinking/narration/narration_delta/artifact/function/gate/error/run_end`。
- 多意图没有计划载体；循环单步动作，模型可做完一件就 final。

## Goals / Non-Goals

**Goals:**

- 协议形状文本在任何路径都不作为正文交付、不写回历史；协议错误可重试且只交付人话。
- `action` 槽误填工具名的形态可被确定性修复为工具调用。
- 模型对「能做什么」有与注册表同源的负向边界，不承诺正文代笔、不把产卡说成落库。
- 多交付物请求有可见、可恢复、不伪造的逐项进度。
- `draft_arc` 的素材与写法约束在入参、能力核与卡面三层可区分。

**Non-Goals:**

- 不在对话里生成正文（写作流职责不变）。
- 不修改提示词包模板、不升 pack 版本（边界块与约束分隔都在 C端组装）。
- 不给 `draft_arc` 新增采纳写回路径（现有缺口另立项）。
- 不做计划项的手工拖拽/编辑 UI；改计划仍通过对话由模型调 `update_plan`。
- 不新增设计令牌、胶囊形态或语气词。

## Decisions

### 1. 协议形状检测分两层，冻结而非删除

`stream_slice` 增加协议片段正则（`"action"｜"tool"｜"args"` 键 + 冒号），从命中位置冻结；`parse_action` 无哨兵分支先切「叙述前缀＋片段尾巴」，再尝试 `_extract_json` 抢救，失败判 `protocol_error`。

- 为什么冻结：流式内容无法撤回，唯一安全做法是从嫌疑点起不进 delta；回合收口再统一交付清理后的叙述。
- 为什么不直接丢弃整段：叙述前缀是作家要看的真实内容，丢掉等于把好回答当故障。
- 代价：叙述里合法引用 `"action":` 字样的内容会延迟到收口才显示，不会丢失。

### 2. 新增 `protocol_error` 动作类型，重试与 final/degraded 解耦

`Action.kind` 增加 `protocol_error`；`loop.py` 的「重试一次」判据从 `degraded` 扩展为 `protocol_error`（degraded 保留原语义）。重试回喂使用清理后的文本，不回声坏片段；重试后仍错，有叙述则交付清理叙述，无叙述交付明确失败话术。transcript 只存清理后文本。

- 为什么不复用 degraded：degraded 的语义是「模型就是直接回答了」，把它重试会误伤正常纯文本回答；两者混在一起也是这次坏文本写回历史的根因。
- 备选：在 UI 层遮罩坏片段——已流出无法撤回，否决。

### 3. `action` 槽填工具名的修复放在解析层，依赖注入

`parse_action(text, tool_exists=None)`：当 `action` 不在 `{tool, final}` 且 `tool_exists(action)` 为真时，组装 `tool=action`、`args=parsed.args`（若 `args.action` 存在则保留为工具参数），走正常工具路径。`loop.py` 传入 `get_tool` 判定，`actions.py` 不反向依赖注册表，测试可注入桩。

- 为什么在解析层而不是 loop 事后补救：修复后的事件、轨迹、授权链路全部走正常路径，不需要第二套执行分支。

### 4. 能力边界块追加在 `tool_catalog_text`，逐工具标 kind

清单每行追加 kind 标签（读／产卡／写），清单末尾追加固定边界块：清单外不存在；正文生成不在对话里；产卡工具不写书，不得说已落库/已保存/我写完了；写入走对应面板或授权卡。文本只依赖注册表快照，字节稳定。

- 为什么不动提示词包：边界必须与注册表同批生效，跨仓发包会让旧包客户端继续越界；C端组装可随版本立即生效。
- 为什么逐工具标 kind：给模型判定「这句话能不能说落库」提供结构化依据，而不是靠它记描述。

### 5. 计划用工具承载，不用新动作动词

新增 `update_plan`（kind=read 的会话状态工具，共享读集），原生 FC 与文本协议两模式同构；计划快照以 `role="event", card_kind="plan"` 追加落盘（最新快照胜出），同时下发 SSE `plan`。一个线程一个活跃计划；`mode=replace` 开新计划，`merge` 按 id 更新。

- 为什么不用 `"action":"plan"`：动作动词是封闭集，扩动词要同时改文本协议、原生 FC 映射与所有解析测试；工具是既有双模式通道。
- 为什么落 event 行而不是 meta：append-only 与崩溃容忍现成；旧前端对空 content event 行天然跳过，回滚安全。
- 计划状态只由模型更新，服务端不猜；服务端只在 `run_end` 做安全网：带 error 收口时把 `active` 降为 `failed`，正常收口把残留 `active` 降回 `pending`，避免永远「在做」。

### 6. `draft_arc` 分层在能力核组装，模板零改动

`draft_arc` 参数改为 `material`／`constraints`／`input`（兼容别名）；`caps.settings.arc_ai_action` 与 `run_arc_ai` 接受可选 `constraints`，在格式化 `{input}` 之前把两层拼成带标题的分隔块。卡面 payload 增加 `constraints_used`，`CardBody` 的通用标签表加「写法约束」。

- 为什么在能力核组装：HTTP 面板与 agent 工具同核，未来面板也能传约束；提示词模板的 `{input}` 语义不变，不需要 prompt pack 发布。
- 为什么不用 `_display`：这是卡面内容而非用户可见侧车元数据；且在采纳路径不存在的前提下不会污染写回。

### 7. 计划卡作为独立自定义卡，按 planId 落位

Aui2Dock 注册 `plan` 卡；SSE `plan` 事件与历史 `card_kind="plan"` 行走同一个 upsert（id=`plan-<planId>`），位置在当前回合轨迹组上方；收口后保留。四态映射 §5：未开始（中性）、在做（warn）、做完（ok）、没做成（err，仅阻断点名交付物时）。视觉复用 chat 卡面骨架与既有语义类。

- 为什么不塞进 TraceCard：轨迹是一次运行的临时过程，计划跨步、跨轮、可恢复，生命周期不同；混在一起会让「回看轨迹」变成回看计划。

## Risks / Trade-offs

- [协议正则误伤正常叙述] → 只冻结不删除，收口整段补发；正则限定键名形态，不匹配普通引号文本。
- [协议错误重试增加一次模型调用] → 只重试一次；重试仍败按清理叙述交付，不无限循环。
- [计划工具被滥用（单件事也建计划）] → 提示词与工具描述限定「两件以上独立交付物」；UI 对单件计划照常渲染，不额外惩罚。
- [计划快照让会话文件变大] → 每次快照只存 id/标题/状态；单线程计划项个位数，JSONL 增量可忽略。
- [旧前端遇到 `card_kind="plan"`] → 旧逻辑对空 content 的 event 行直接跳过，不渲染空卡；新前端按 plan 行折叠。
- [边界块文本变长稀释指令] → 按域收窄后清单本身 ≤17 行；边界块固定 4 行，字节稳定利于前缀缓存。
- [`draft_arc` 卡仍无采纳写回] → 边界话术改为「还没写进书里，写入到主线面板」，不承诺卡上采纳；采纳链另立项。

## Migration Plan

- 全部为增项：新 SSE 事件、新工具、新参数、新 event 行；无数据库迁移。
- 发布顺序：后端先上（旧前端忽略 `plan` 事件与空 event 行），前端同版本随后；回滚只需回退版本，会话文件中的 plan 行旧读端跳过。
- 回滚后 `constraints` 参数被旧后端忽略的风险：同版本发布避免跨版本混用；灰度包同时含两端。

## Open Questions

（无——影响规格与拆解的不确定项已在上面定案。）
