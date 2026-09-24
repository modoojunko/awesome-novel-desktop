## ADDED Requirements

### Requirement: 记账失败不得回滚主流程写入

用量记账与事件埋点的写入 SHALL 使用 SAVEPOINT（`begin_nested`）承载：写入失败时只回滚记账自身，同会话中主流程已暂存的写入 MUST NOT 被连带回滚。失败 SHALL 记 warning 级日志（含 operation/event_type 标识），MUST NOT 全静默。

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
