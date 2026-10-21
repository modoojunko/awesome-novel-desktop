# ai-client Specification

## Purpose

AIClient 是全部大模型调用的唯一客户端层。本 capability 约束它的运行时纪律：调用必须在可预期的时间内给出结果（成功或失败），且任何一次真实发生的调用——无论成败——都留下用量痕迹。用户不应为一次挂起的供应商请求无限等待，也不应悄悄烧掉看不见的 token。

## Requirements

### Requirement: AI 调用必须有显式超时

非流式与流式调用分别设置显式超时上限；不得依赖底层 SDK 的默认超时（600 秒级）。超时上限对判定类短调用收紧、对长文流式生成放宽；整体最坏等待时间（含底层重试）必须有确定上界，不得达到 10 分钟量级。

流式调用 SHALL 另设**首字守卫**：自发起调用至首个正文片段到达的总时长有上限（默认 90 秒；**正文流式生成 SHALL 放宽至 600 秒——深度思考模型思考期远超 90 秒，真挂死仍由「相邻事件间隔」read 上限兜底**）；超限 SHALL 终止上游流并按失败上抛（SHALL NOT 产出完成事件）。首个正文片段到达 SHALL 即撤销守卫（长文持续生成不受影响）。**正文片段指交付给调用方的生成内容：openai 兼容路径的内联思考段（`<think>…</think>`）不构成首字，思考期间守卫持续在计；anthropic 路径的 `thinking_delta` 同口径不计。** openai 与 anthropic 两种流式实现 SHALL 同口径生效；守卫判死 SHALL NOT 触发思考拒参的去参重开重试。零片段静默仍由「相邻事件间隔」read 上限兜底。守卫超时 SHALL 与网络层超时同语义归一（调用方按类型区分给文案），llm.log SHALL 留失败行（含实测等待时长）。

#### Scenario: 供应商挂起时快速失败

- **WHEN** 供应商端点接受连接后不返回响应，达到非流式超时上限
- **THEN** 调用以失败告终并向上层抛错，总耗时不超过既定上限；端点返回的 502 文案能被用户识别为网络/超时类失败（与供应商拒绝业务参数的失败可区分）

#### Scenario: 长文流式生成不误伤

- **WHEN** 流式生成持续产出内容、单次生成总时长超过判定类短调用上限
- **THEN** 调用不被短调用上限打断；流式的超时约束针对「连接建立」「迟迟无新内容」与「首字前总时长」三个环节

#### Scenario: 思考久不出正文时守卫判死

- **WHEN** 开思考的模型持续产出推理增量但迟迟无正文、首字前总时长超过首字守卫上限（推理增量含 anthropic 的 `thinking_delta` 与 openai 兼容路径的内联 `<think>` 段）
- **THEN** 上游流被终止，调用以首字守卫超时失败告终（实测等待时长随异常与 llm.log 留痕），不产出完成事件；流只开一次，思考拒参的去参重开重试 SHALL NOT 被触发

#### Scenario: 首字到达后守卫不再生效

- **WHEN** 首个正文片段（非思考内容）已到达，其后正文持续流出至自然收尾
- **THEN** 守卫撤销，长文生成不被守卫打断

### Requirement: 内联思考不得混入交付文本

openai 与 anthropic 兼容路径 SHALL 在响应侧剥离内联思考（两路同构，共用同一剥离状态机）：仅当响应文本以 `<think>` 开头时判定为内联思考形态，自起始至首个 `</think>`（含标签本身）的整段 SHALL NOT 出现在交付文本中。**交错思考口径（2026-10-20 修订）**：闭标签后正文再出现完整 `<think>` 开标签（M2 系交错思考官方口径）SHALL 转回剥离态、其思考段以思考事件通道透出（见「思考增量按独立事件通道交付」），SHALL NOT 进入交付文本；判定保持从窄——仅 exact 标签匹配才转剥离，非完整标签的相似字面（如 `<thin`）SHALL 保持原样。anthropic 路径的剥离针对 text 通道（`text_delta` 与非流式 text 块）——思考关断/未协商时部分 anthropic 兼容端点（MiniMax 实测）会把思考内联进 text 而非独立块。流式下标签可能裂在增量边界，SHALL 以缓冲判明后再产出；剥离出的思考段 MUST NOT 产出正文事件（以思考事件透出）。响应不以 `<think>` 开头且中段无再开标签的（含走独立 `reasoning_content` 字段的供应商、普通无思考模型）交付文本 SHALL 与原始响应逐字一致。思考内容以独立思考事件通道透出（见「思考增量按独立事件通道交付」），不再静默丢弃；思考内容 SHALL NOT 撤销首字守卫、MUST NOT 影响用量记账口径。剥离仅针对 `<think>` 形态；`<think>` 已出现但流结束仍未闭合的，整段按思考处理（交付产物为空），由既有空产物处理路径兜底。剥离处理自身 MUST NOT 因异常中断正常生成。

#### Scenario: 非流式响应剥内联思考

- **WHEN** openai 兼容非流式调用返回的文本以 `<think>` 开头、其后某处出现 `</think>`
- **THEN** 调用方拿到的文本不含 `<think>` 起始段与 `</think>` 及其间的全部思考内容，正文自 `</think>` 之后原样起算

#### Scenario: 流式思考段跨增量边界仍零泄漏

- **WHEN** 流式增量中 `<think>`、思考内容与 `</think>` 分裂在多个 chunk 边界
- **THEN** 思考段不产出任何正文事件（以思考事件通道透出），交付正文事件自 `</think>` 之后的正文起且逐字完整

#### Scenario: 无内联思考的响应逐字不动

- **WHEN** 响应文本不以 `<think>` 开头且中段无完整 `<think>` 开标签（普通模型正文、走 `reasoning_content` 分字段的推理模型、或正文携带 `<thin` 等非完整标签相似字面）
- **THEN** 交付文本与原始响应逐字一致，不发生任何删改

#### Scenario: 中段再开标签按交错思考透出

- **WHEN** 流式响应在首个闭标签后的正文中再次出现完整 `<think>…</think>`（M2 系交错思考官方口径）
- **THEN** 第二段思考以思考事件透出、SHALL NOT 出现在交付文本；正文与思考事件按到达顺序各自完整、零串道

#### Scenario: 思考未闭合按整段思考兜底

- **WHEN** 响应以 `<think>` 开头但直至流结束/响应结束都未出现 `</think>`
- **THEN** 整段按思考处理不进入交付文本（非流式交付空文本、流式无正文事件），既有空产物重试与报错路径照常接管

#### Scenario: 剥离自身异常不中断生成

- **WHEN** 剥离处理过程中发生任何内部异常
- **THEN** 调用不因此失败，按可判定范围交付（无法判定时按原始文本交付），完成事件照常产出

#### Scenario: anthropic 路径内联思考同构剥离

- **WHEN** anthropic 兼容端点把内联思考以 `text_delta`（`<think>…</think>` 前缀）交付而非独立 thinking 块
- **THEN** 思考段零正文事件产出（以思考事件透出）、正文自闭标签后逐字完整；内联思考段 SHALL NOT 撤销首字守卫（独立 `thinking_delta` 同口径不计）

### Requirement: 失败调用也必须记账

任何真实发出的 AI 调用，无论成功、失败或超时，都必须落一条用量记录；失败记录的 operation 以 `_fail` 后缀区分。失败时已消耗的 token 如实记录；未返回用量时允许记零，但记录本身必须存在。成功调用「零 token 不落库」的防噪音语义保持不变。

#### Scenario: 判定类调用超时后查用量

- **WHEN** 一次设定页 AI 调用因供应商挂起而超时失败
- **THEN** token_log 中存在该次调用的记录，operation 带该业务动作的 `_fail` 后缀；同名无后缀 operation 的成功记录不受影响

#### Scenario: 成功零 token 调用仍不落库

- **WHEN** 一次调用成功返回但用量为零
- **THEN** 不落用量记录（与既有行为一致）

### Requirement: 多次尝试的用量必须完整回填

客户端层的重试包装（如空文本自动重试一次）在 ANY 退出路径上（成功、可重试失败、不可重试失败）都把所有尝试累计的用量回填给调用方；不得只在部分异常分支回填。调用方据此落库的数字 = 供应商实际计费的总和。

#### Scenario: 首次尝试烧 token 后失败

- **WHEN** 判定类调用首次尝试消耗 token 后抛出不可重试的异常
- **THEN** 调用方拿到的用量包含首次尝试的 token；失败记账落库数字与之相符

#### Scenario: 重试成功按两次合计记账

- **WHEN** 判定类调用首次尝试返回空文本、重试成功
- **THEN** 落库用量为两次尝试之和（既有语义，保持）

### Requirement: 记账失败不得回滚主流程写入

用量记账与事件埋点的写入 SHALL 在与调用方主流程隔离的事务边界内承载（独立会话——实测 SAVEPOINT 方案下 flush 失败会把整个会话标记为 deactive，无法保住主流程写入）：写入失败时只回滚记账自身，同会话中主流程已暂存的写入 MUST NOT 被连带回滚。失败 SHALL 记 warning 级日志（含 operation/event_type 标识），MUST NOT 全静默。

#### Scenario: FK 失败不丢主数据

- **WHEN** 记账写入因外键（如 user 未落库）失败，而同会话已暂存业务写入
- **THEN** 仅记账回滚，业务写入随后照常提交；日志出现 warning 级 `event=usage.write_failed`

#### Scenario: 失败不抛出

- **WHEN** 记账失败
- **THEN** 调用方不收到异常（记账失败不影响主流程的既有契约保持）

### Requirement: 流式用量按输入/输出拆分

流式生成的完成事件 SHALL 分别携带输入侧与输出侧 tokens：OpenAI 兼容分支取 `completion_tokens`/`prompt_tokens`，anthropic 分支输出侧取 `message_stop` 的 `output_tokens`、输入侧取 `message_start` 的 `input_tokens`。消费方记账 SHALL 分别记录 `tokens_in`/`tokens_out`，MUST NOT 把 total 记入输出侧。

#### Scenario: OpenAI 流式拆分

- **WHEN** OpenAI 兼容供应商流式返回 usage（prompt=100/completion=200/total=300）
- **THEN** 记账为 tokens_in=100、tokens_out=200（不再把 300 记入输出侧）

#### Scenario: anthropic 流式拆分

- **WHEN** anthropic 流式完成（message_start 携带 input_tokens、message_stop 携带 output_tokens）
- **THEN** 记账分别为两个方向的 tokens

### Requirement: 流式 usage 块不得中断生成

流式迭代 SHALL 跳过不含 choices 的块（OpenAI 兼容供应商流末的 usage-only 块），MUST NOT 因索引越界中断已成功的生成；流为空时完成事件 SHALL 正常产出（tokens 记零）。

#### Scenario: 流末 usage 块不炸

- **WHEN** OpenAI 兼容供应商在文本块之后发送 `choices=[]` 的 usage 块
- **THEN** 文本完整产出、完成事件带拆分用量，不抛 IndexError、不记 `*_fail`

#### Scenario: 空流不炸

- **WHEN** 供应商未返回任何块即结束
- **THEN** 完成事件正常产出且 tokens 为零，不抛未定义变量异常

### Requirement: JSON 响应模式调用必须自证满足供应商前置约束

以 JSON 响应模式（response_format 为 json_object）向 OpenAI 兼容供应商发出的调用，其生效提示词——system 段与用户消息的合并全文——SHALL 含「json」字样（大小写不限）；不满足时 DeepSeek 等供应商以 400 invalid_request_error 整单拒收。该约束 SHALL 由提示词仓测试链的仓库不变量守卫强制：除显式登记的「成品文本类」例外名单（散文正文、提示词成品等非 JSON 输出模板）与注入片段资产外，一切对外调用模板剥除注释后的有效文本缺「json」字样即守卫失败并指名模板；例外名单的每次增删 SHALL 逐条有据并在变更 diff 中可审。例句提炼调用点另 SHALL 有行为钉：桩化客户端捕获实发提示词，断言含「json」字样且模板声明了 JSON 输出契约。

#### Scenario: 例句提炼不再被供应商拒收
- **WHEN** 用户在文风面板触发例句提炼且本书存在已归档章节
- **THEN** 实发请求的提示词含「json」字样，且模板给出 `{"lines": [...]}` 输出契约（1–3 条原文摘录）；供应商正常返回时端点解析 lines 并返回例句列表，不再出现 invalid_request_error

#### Scenario: 模板迁移丢失 json 字样时守卫拦截
- **WHEN** 任一例外名单外的调用模板，其剥除注释后的有效文本不再含「json」字样
- **THEN** 提示词仓守卫测试失败，报告指名该模板

#### Scenario: 新调用模板默认受守卫覆盖
- **WHEN** 提示词仓新增一个对外调用模板而未登记进例外名单
- **THEN** 该模板缺「json」字样时守卫测试失败——默认必须带 JSON 输出契约，豁免必须显式登记并有据

### Requirement: 思考增量按独立事件通道交付

流式调用的思考增量 SHALL 以独立的思考事件通道交付，与正文事件分流；三个来源统一口径——openai 兼容路径的内联思考段（`<think>…</think>`，由内联思考剥离状态机边剥边透出）、openai 兼容路径的 `reasoning_content` 增量、anthropic 路径的 `thinking_delta`。思考增量 MUST NOT 混入正文事件；交付正文文本零思考的口径（见「内联思考不得混入交付文本」）不变。思考事件 MUST NOT 影响首字守卫（不构成首字、不撤守卫）与用量记账口径（tokens 仍按供应商回报拆分记录）。不消费思考事件的调用方 SHALL 行为不变（正文流、完成事件照旧）。非流式调用不产出思考事件（思考直接丢弃，见内联思考剥离口径）。

#### Scenario: 内联思考段转为思考事件

- **WHEN** openai 兼容供应商流式响应在 content 中内联 `<think>…</think>` 思考段
- **THEN** 思考段以思考事件按到达顺序交付（不落正文事件），正文事件自闭标签之后起且逐字零混入

#### Scenario: reasoning_content 分字段转为思考事件

- **WHEN** DeepSeek/Qwen/Kimi 形态的流式响应并行携带 `reasoning_content` 增量与 `content` 增量
- **THEN** 思考事件仅来自 `reasoning_content`，正文事件与 `content` 逐字一致，两通道无重复内容

#### Scenario: anthropic thinking_delta 转为思考事件

- **WHEN** anthropic 流式响应交替下发 `thinking_delta` 与 `text_delta`
- **THEN** 思考增量走思考事件、正文增量走正文事件，按到达顺序各自完整

#### Scenario: 思考事件不碰守卫与记账

- **WHEN** 思考事件持续产出而正文未到、首字前总时长超过守卫上限
- **THEN** 首字守卫照常判死（思考事件不算首字）；用量记账口径与无思考事件时完全一致
