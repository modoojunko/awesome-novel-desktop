## ADDED Requirements

### Requirement: 流式缓存命中留痕

OpenAI 兼容流式调用在供应商 usage 返回缓存统计时，`ai_call` 留痕行 SHALL 追加 `cache_hit=<prompt_cache_hit_tokens>` 与 `cache_miss=<prompt_cache_miss_tokens>`；供应商未返回这两个字段时 SHALL NOT 输出该段（日志格式向后兼容）。缓存统计 MUST NOT 改变 tokens_in/tokens_out 记账口径。

#### Scenario: DeepSeek 返回缓存统计
- **WHEN** 流末 usage 携带 prompt_cache_hit_tokens=80、prompt_cache_miss_tokens=20
- **THEN** ai_call 成功行包含 cache_hit=80 cache_miss=20，tokens 记账不变

#### Scenario: 供应商未返回缓存统计
- **WHEN** 流末 usage 只有 prompt_tokens/completion_tokens
- **THEN** ai_call 行不出现 cache_hit/cache_miss 字段
