## ADDED Requirements

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
