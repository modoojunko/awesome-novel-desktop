# ai-client Specification

## Purpose

AIClient 是全部大模型调用的唯一客户端层。本 capability 约束它的运行时纪律：调用必须在可预期的时间内给出结果（成功或失败），且任何一次真实发生的调用——无论成败——都留下用量痕迹。用户不应为一次挂起的供应商请求无限等待，也不应悄悄烧掉看不见的 token。

## Requirements

### Requirement: AI 调用必须有显式超时

非流式与流式调用分别设置显式超时上限；不得依赖底层 SDK 的默认超时（600 秒级）。超时上限对判定类短调用收紧、对长文流式生成放宽；整体最坏等待时间（含底层重试）必须有确定上界，不得达到 10 分钟量级。

流式调用 SHALL 另设**首字守卫**：自发起调用至首个正文片段到达的总时长有上限（默认 90 秒）；超限 SHALL 终止上游流并按失败上抛（SHALL NOT 产出完成事件）。首个正文片段到达 SHALL 即撤销守卫（长文持续生成不受影响）。**正文片段指交付给调用方的生成内容：openai 兼容路径的内联思考段（`<think>…</think>`）不构成首字，思考期间守卫持续在计；anthropic 路径的 `thinking_delta` 同口径不计。** openai 与 anthropic 两种流式实现 SHALL 同口径生效；守卫判死 SHALL NOT 触发思考拒参的去参重开重试。零片段静默仍由「相邻事件间隔」read 上限兜底。守卫超时 SHALL 与网络层超时同语义归一（调用方按类型区分给文案），llm.log SHALL 留失败行（含实测等待时长）。

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

openai 兼容路径 SHALL 在响应侧剥离内联思考：仅当响应文本以 `<think>` 开头时判定为内联思考形态，自起始至首个 `</think>`（含标签本身）的整段 SHALL NOT 出现在交付文本中；正文中后段出现的同名字面 SHALL 保持原样（判定口径从窄，避免误伤正文）。流式与非流式 SHALL 同构生效；流式下标签可能裂在增量边界，SHALL 以缓冲判明后再产出，思考段 MUST NOT 产出任何事件。响应不以 `<think>` 开头的（含走独立 `reasoning_content` 字段的供应商、普通无思考模型）交付文本 SHALL 与原始响应逐字一致。思考内容本要求下直接丢弃，不做任何呈现。剥离仅针对 `<think>` 起始形态；`<think>` 已出现但流结束仍未闭合的，整段按思考处理（交付产物为空），由既有空产物处理路径兜底。剥离处理自身 MUST NOT 因异常中断正常生成。

#### Scenario: 非流式响应剥内联思考

- **WHEN** openai 兼容非流式调用返回的文本以 `<think>` 开头、其后某处出现 `</think>`
- **THEN** 调用方拿到的文本不含 `<think>` 起始段与 `</think>` 及其间的全部思考内容，正文自 `</think>` 之后原样起算

#### Scenario: 流式思考段跨增量边界仍零泄漏

- **WHEN** 流式增量中 `<think>`、思考内容与 `</think>` 分裂在多个 chunk 边界
- **THEN** 思考段不产出任何事件，交付事件自 `</think>` 之后的正文起且逐字完整

#### Scenario: 无内联思考的响应逐字不动

- **WHEN** 响应文本不以 `<think>` 开头（普通模型正文、走 `reasoning_content` 分字段的推理模型、或正文中段出现 `<think>` 字面）
- **THEN** 交付文本与原始响应逐字一致，不发生任何删改

#### Scenario: 思考未闭合按整段思考兜底

- **WHEN** 响应以 `<think>` 开头但直至流结束/响应结束都未出现 `</think>`
- **THEN** 整段按思考处理不进入交付文本（非流式交付空文本、流式无正文事件），既有空产物重试与报错路径照常接管

#### Scenario: 剥离自身异常不中断生成

- **WHEN** 剥离处理过程中发生任何内部异常
- **THEN** 调用不因此失败，按可判定范围交付（无法判定时按原始文本交付），完成事件照常产出

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
