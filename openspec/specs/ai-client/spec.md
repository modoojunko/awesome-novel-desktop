# ai-client Specification

## Purpose

AIClient 是全部大模型调用的唯一客户端层。本 capability 约束它的运行时纪律：调用必须在可预期的时间内给出结果（成功或失败），且任何一次真实发生的调用——无论成败——都留下用量痕迹。用户不应为一次挂起的供应商请求无限等待，也不应悄悄烧掉看不见的 token。

## Requirements

### Requirement: AI 调用必须有显式超时

非流式与流式调用分别设置显式超时上限；不得依赖底层 SDK 的默认超时（600 秒级）。超时上限对判定类短调用收紧、对长文流式生成放宽；整体最坏等待时间（含底层重试）必须有确定上界，不得达到 10 分钟量级。

#### Scenario: 供应商挂起时快速失败

- **WHEN** 供应商端点接受连接后不返回响应，达到非流式超时上限
- **THEN** 调用以失败告终并向上层抛错，总耗时不超过既定上限；端点返回的 502 文案能被用户识别为网络/超时类失败（与供应商拒绝业务参数的失败可区分）

#### Scenario: 长文流式生成不误伤

- **WHEN** 流式生成持续产出内容、单次生成总时长超过判定类短调用上限
- **THEN** 调用不被短调用上限打断；流式的超时约束针对「连接建立」与「迟迟无新内容」两个环节

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
