# ai-client-timeout-and-usage-accounting — Design

## Context

- `AIClient._init_client`（`client/backend/ai_client.py`）构造 `AsyncAnthropic`/`AsyncOpenAI` 时不传 `timeout`/`max_retries`，走 SDK 默认（600s 超时 + 内置重试）——最坏一次点击 ~20 分钟才落 502。
- 记账现状三类缺口（均已实勘）：
  1. `settings/ai_router.py` 六处判定端点：`except → raise HTTPException(502)` 丢弃 usage；`_judge_chat` 只在「成功」与「非空文本 ValueError」两条路径 `_flush_usage` 回填，超时/连接类异常不回填。
  2. `write/router.py` 流式写章只在 `is_done` 分支记账，流中断零记账；润色/扩写等非流式端点无失败分支。
  3. `api_configs/usage.py:24` 零 token 早退把失败记录（多为零 token）整体挡在库外。
- `settings/characters_ai.py`（角色 change 新代码）已是失败记账样板：`except` 里 `record_usage` 再 raise；但 operation 成败同名，未带失败标记。
- `TokenLog` 无 status 列；`operation` String(50)。前端对 AI 失败统一 toast 502 detail 文案，不区分状态码。

## Goals / Non-Goals

**Goals:**
- 任何 AI 点击的等待时间有确定上界（分钟级，非 20 分钟）。
- 任何真实发出的调用在 `token_log` 留痕，成败可区分。
- usage 回填在所有退出路径成立，落库数字 = 供应商实际计费总和。

**Non-Goals:**
- 不动 `TokenLog` 表结构（零 DDL，不加 status 列——`_fail` 后缀承担区分职责）。
- 不改前端展示（502 状态码保持，只改文案可识别性）。
- 不做用量页的失败筛选/统计视图（`_fail` 行自然汇入现有汇总，是否单列展示留待真实需求）。
- 不动 `prompt_crafting` 探测类短调用以外的连接池/并发参数。

## Decisions

### D1 超时分级：客户端构造默认 + 流式按事件间隔生效

- `AIClient.__init__` 增加 `timeout` 参数（默认注入），构造 SDK 客户端时显式传入：
  - 非流式 `chat`：`httpx.Timeout(connect=10, read=90, write=30, pool=10)`——判定类 `max_tokens=4096`、思考默认关闭，90s read 覆盖最慢合规生成。
  - 流式 `chat_stream`：`httpx.Timeout(connect=10, read=120, write=30, pool=10)`——read 是「相邻事件间隔」上限而非总时长，长文持续出 chunk 不受影响，供应商挂起 120s 内判死。
- `max_retries` 显式设 1（保留一次瞬时故障重试，收敛最坏等待 ≈ 3 分钟；SDK 默认 2 会把超时等待翻倍）。
- 备选：每调用点单独传 timeout——否，调用面 30+ 处，客户端层统一默认 + 需要更紧的调用点再覆盖（本 change 不出现此需求）。

### D2 超时异常类型化：新增 `AITimeoutError`

- `ai_client.py` 定义 `class AITimeoutError(Exception)`；`chat`/`chat_stream` 捕获 SDK 超时/连接类异常转抛之。
- 端点层 `except AITimeoutError` 分支返回 502，文案「AI 服务响应超时，请稍后重试」（状态码不动，前端零改动、文案可识别）；其余异常维持现文案。
- 不走「转 ValueError」路线——会与 `_judge_chat` 的空文本重试判据纠缠。

### D3 失败记账：operation `_fail` 后缀 + `record_usage(force=True)`

- `record_usage` 签名加 `force: bool = False`：`tokens` 全零且非 force 才早退。成功零 token 防噪音语义不变。
- 七个消费方文件的异常路径统一：`except` 分支先 `await record_usage(..., operation=<原名>+"_fail"[:50], force=True)` 再 raise/转 502。空结果型失败（如「AI 没给出可用的内容」）同口径。
- `characters_ai.py` 现役失败记账补 `_fail` 后缀对齐（成功路径保持原名）。
- 流式端点：生成器 try/except 包裹 yield 循环，中断时落 `_fail` 记录（`tokens_out` 取已累计的事件 tokens，拿不到则零）再重抛。

### D4 `_judge_chat` 回填改 finally

- 现三次 `_flush_usage` 调用点（成功 / 非「空文本」ValueError / 重试耗尽）收敛为 `try/finally` 单点：`finally: _flush_usage(caller_usage, total_in, total_out)`。任何异常路径调用方都拿到已烧 token，成功路径行为不变（防止 double flush 靠单点化保证）。

### D5 记账收口不抽公共装饰器

- 各端点 except 分支手写 `record_usage`（与成功路径同款参数、operation 加后缀），不引入装饰器/上下文管理器抽象——调用面仅 30+ 处、参数各异（chapter_id 有无、operation 命名），抽象收益低于显式成本；样板照 `characters_ai.py`。

## Risks / Trade-offs

- **90s read 对个别慢端点可能误杀**：思考未关死的端点（`_THINKING_UNSUPPORTED_BASES` 未覆盖的 base_url）生成可能超 90s。缓释：超时文案明确「稍后重试」；实测若误杀率可见再对个别端点放宽，不动全局默认。
- **失败零 token 行的噪音**：连接立刻失败时落 0 token `_fail` 行，对「总用量」无影响（tokens 全零），仅行数增多；汇总查询按 token 聚合不受扰。
- **流式记账的 tokens_in 缺失**：流式协议 `is_done` 事件常无输入 token，现状成功路径就只记 `tokens_out`，`_fail` 行沿用同一口径，不新增不一致。
- **重试叠加超时的边界**：SDK 内置重试对超时类错误同样生效（最坏 90s×2≈3 分钟），已在 D1 上界内接受。
