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

## MODIFIED Requirements

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
