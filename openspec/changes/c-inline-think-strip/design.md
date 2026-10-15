# c-inline-think-strip — Design

## Context

泄漏面只有 openai 兼容路径的 content 通道（见 proposal）。客户端层 `AIClient` 是所有业务调用的唯一出口：`chat()`（非流式）与 `chat_stream()`（流式），openai/anthropic 双实现。anthropic 路径思考是独立块/事件天然分离；openai 路径需在响应侧净化。

## Goals / Non-Goals

**Goals**
- openai 路径交付文本零内联思考（流式/非流式同构），对调用方完全透明。
- 首字守卫口径恢复设计意图：内联思考不算首字。
- 普通响应（无内联思考）零改动、零额外延迟感知。

**Non-Goals**
- 思考内容的呈现/留存（归 c-thinking-display）。
- anthropic 路径改动（协议层已分块，`thinking_delta`/thinking 块现行丢弃口径不变）。
- `reasoning_content` 字段改动（独立字段，现行不读即丢弃，天然干净）。
- 请求侧参数（`reasoning_split` 等 vendor 专属参数不在本 change）。

## Decisions

1. **剥离位置＝客户端层出口（ai_client 单点），不是各业务层。**
   业务层剥离意味着正文/章纲/判定/拆书每条链各剥一遍，必然漂移；客户端层是唯一汇聚点，全部 operation 通吃。备选「业务层各自剥」拒绝。

2. **判定口径从窄：仅「响应以 `<think>` 开头」进剥离态。**
   MiniMax 系只把思考前缀内联；正文中段出现 `<think>` 字面（叙事文本理论上可拼出）不剥。理由：误伤正文是不可逆的内容损坏，漏剥的代价小于误剥。

3. **流式＝跨 chunk 缓冲状态机，三态：**
   - `HOLDING`：以「缓冲是否为 `<think>` 的前缀」判定——是开标签完整形态转 `STRIPPING`；仍可能是前缀（如 `<th`）继续攒；一旦偏离（首个字符 ≠ `<` 即命中）缓冲整体放行转 `PASSING`。普通模型首 chunk 零延迟直通。
   - `STRIPPING`：增量丢弃；为防 `</think>` 裂在边界，仅保留尾部 ≤`len("</think>")-1` 字符的滑窗做匹配，闭合后残余（含闭合标签）丢弃、转 `PASSING`。**不保留思考内容**——缓冲有界，思考再长内存不动。
   - `PASSING`：直通，直到流结束。
   - 流结束仍在 `HOLDING`/`STRIPPING`：按整段思考处理（交付空）。`</think>` 之后若无正文（空产物），交给既有空文本重试/报错路径。

4. **非流式与流式共享同一剥离核心**（同一份纯函数/状态机驱动），非流式一次喂入、流式逐 chunk 喂入——双实现必漂移，单实现两种驱动。

5. **首字守卫撤点＝剥离器放行首个正文事件时**。`HOLDING`/`STRIPPING` 期间不撤守卫，90s 判死、AIThinkingTimeoutError 归一、去参重开禁令全部不变。原实现「首个 `delta.content` 即撤」正是被内联思考缴械的点。

6. **异常兜底**：剥离器整体 try/except，内部异常时按原始文本交付——净化是尽力而为的卫生层，不得毁掉正常生成（spec 场景钉死）。

## Risks / Trade-offs

- [模型正文真以 `<think>` 开头（极端叙事场景）] → 会被整段剥掉；生成正文均为小说叙事，该形态实际不存在，且用户重生成即可恢复。漏剥（思考泄漏进正文）与误剥（正文被删）之间取窄口径倾向后者低概率。
- [`</think>` 滑窗匹配漏配] → 行为钉测试覆盖标签在各位置裂开的矩阵（`</th`＋`ink>` 等）。
- [STRIPPING 期供应商只发思考不发正文] → 守卫 90s 判死兜底，语义与 c-prose-thinking-timeout 一致。
- [剥离改变交付字节数，usage 统计不受影响] → tokens 按供应商回报记账，与交付文本长度天然解耦，无连带。

## Migration Plan

无数据/配置迁移，部署即生效。回滚＝还原本次代码（无任何持久化痕迹）。

## Open Questions

无。
