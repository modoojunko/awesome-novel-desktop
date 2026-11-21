## Context

见 `proposal.md`。当前 `assistant/router.py::_stream_chat`：

- `brief = await build_book_brief(project, db)`（含进度/字数/frontier）→ `build_system_prompt(..., book_brief=brief, memory_section=memory_section)`；
- `note = build_page_note(...)` + unsaved/profile/gap/tab → `message_for_model = f"{message}\n{note}"`。

动态 brief 与 memory 在 system 前缀，写作进度/决策一变，后续轮次的前缀缓存整段失效。`AIClient.chat_stream` 的 usage 解析只取 prompt/completion tokens，未读 DeepSeek 的缓存字段。

## Goals / Non-Goals

**Goals:**
- system 前缀跨轮稳定（只留稳定内容），动态内容进当前 user 消息尾部。
- llm.log 能观测 `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`。
- 现有提示词模板（`assistant_system` 的 `{book_brief}` 占位）不改，包兼容。

**Non-Goals:**
- 不持久化每回合注入（页面/画像会过期）；不改 compact 策略。
- 不改前端/会话文件格式/API。

## Decisions

### 1. `build_book_brief` 拆稳定/动态两段
新增 `build_book_brief_parts(novel, db) -> (stable, dynamic)`：
- stable＝书名＋题材（题材解析失败只留书名）；
- dynamic＝进度行（frontier 三态真值/字数）。
`build_book_brief` 保留为两段拼接（既有调用/测试零改）。router 的 system 用 stable，dynamic 拼到 note。
- 理由：书名/题材跨轮稳定；进度随写作变化。prompt pack 的 `{book_brief}` 占位继续工作。
- 备选：整段 brief 进 note（书名/题材也丢出 system，模型对书情的系统级锚定变弱，否决）。

### 2. memory/decision 段从 system 移到 note
`build_system_prompt(..., memory_section="")`；把 `memory_section` 与 dynamic brief 一起拼进 `note`（当前 user 消息尾部）。
- 理由：决策/记忆随对话增长，是高频动态段；放 system 会整段失效缓存。它是数据段，放 user 尾部语义不变。
- 备选：持久化为单独 system 消息（会跨轮残留过期页面状态，且仍进入前缀，否决）。

### 3. 缓存字段解析与留痕
`chat_stream` openai 分支在 usage 块读 `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`（含 SDK `model_extra` 兜底）；`_log_call` 增可选参数，成功行追加 `cache_hit=`/`cache_miss=`（两字段都未返回不加）。
- 理由：DeepSeek 的字段名与 Anthropic 的 `cache_read/creation` 不同；不改变 tokens 记账。
- 备选：写进 TokenLog/DB（需要迁移，观测用 llm.log 足够，否决）。

### 4. note 组装顺序
`page/focus/unsaved/profile/gap/tab` → dynamic brief → memory section，块间 `\n\n`。都在当前 user 消息尾部；不持久化。
- 理由：动态内容越靠后，前面可命中的前缀越长；与既有 L2 注入同段。

## Risks / Trade-offs

- [每回合 note 不持久化，下一轮历史里没有它] → 缓存命中点在「上一条 user 消息原文」处截断，仍能复用 system+更早历史；这是保留页面状态新鲜的既有取舍，不因本 change 改变。
- [memory 段放 user 尾部，模型对它的服从度可能略降] → 它是数据不是规则；身份/围栏仍在 system，安全段不受影响。测试断言注入内容仍在。
- [缓存字段只有 DeepSeek 返回] → 未返回不输出，日志兼容；其它供应商后续有实证再扩。

## Migration Plan

- 纯提示词组织与日志字段，无数据/API 迁移。
- 回滚：还原 brief/memory 的 system 拼接与 note 组装；缓存字段留痕可独立保留。

## Open Questions

（无）
