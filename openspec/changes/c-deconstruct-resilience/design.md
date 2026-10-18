## Context

当前拆书管线（`client/backend/deconstruct/`，基线=`origin/main` 2efd8b00）已经完成 v2 的
「逐章拆卡 → 分维度分级归并」：`pipeline.py:476-506` 每章一次 `deconstruct_card`，
`pipeline.py:531-560` 按 30k 字符分批 L1，`pipeline.py:563-604` 串行树状 reduce，
`pipeline.py:362-452` 逐章补 presence，`pipeline.py:648-656` 全书地点归并。
真实 258 章任务（`.docker-data/client/novel-v0.34.db`）结构上 ≥284 次调用：
258 次拆卡 + 18 次 L1 + 6 次 reduce + 1 次补写 + 1 次地点归并；`dims_json` 约 915KB，
每完成一个单元都整体重写。该任务 `characters`/`world` 因 reduce 输出 8192 截断做了
3 次注定失败的重试后降级，`mainplot` 被 1301 拒后整维降级。

关键约束：

- 单用户桌面应用，SQLite（WAL），后端单 uvicorn worker；dispatcher 是常驻单线程
  （`dispatcher.py:46-66`），同一时刻只跑一个拆书任务。
- 现有单元级重试 2 次（`pipeline.py:323-342`）+ `AIClient` 默认 `max_retries=1`
  （`ai_client.py:287`），两层叠加；`_run_units` 用
  `asyncio.gather(..., return_exceptions=True)`（`pipeline.py:308-320`）等全部单元结束才抛错。
- 超时固定：普通调用 `read=90s`，`max_tokens>=8192` 的归并调用 `read=600s`
  （`pipeline.py:288-305`、`ai_client.py:45-50`）。没有任务级看门狗/墙钟；
  `startup_sweep` 只在应用启动时跑（`pipeline.py:768-790`）。
- 取消只在单元边界查 status（`_check_cancel`，`pipeline.py:283-285`），重试循环与在途
  HTTP 调用不响应取消。
- 提示词模板在独立仓（awesome-novel-prompts），通过分层包发布；本仓不落 `.prompt` 源。
- 设计事实源：`docs/ux/design-language.html` 的状态语言/组件词汇；本变更只复用既有
  notice/pill 的 warn 语气，不新增视觉形态。
- 2026-10-17 用户确认目标模型具备 1M 上下文；`max_output_tokens` 与长上下文计价档
  尚未实测，作为阶段二基准任务的输入。

## Goals / Non-Goals

**Goals:**

- 任何 provider 故障都收敛为有界、可读、可续拆的结果：不再出现小时级「拆解中」。
- 取消在 10 秒内生效；单任务卡死不会无限阻塞 FIFO 队列。
- 续拆粒度到单元：L1 批/reduce 组/卡片任一失败，不重跑已成功单元。
- 在不降低产物质量的前提下减少请求数与重复模板开销；1M 上下文用于单遍归并/合批，
  不用于整书×维度重复读取。
- 每个任务的调用次数、重试、失败类型、耗时、token 可视化；降级维度可见；时间口径统一 UTC。
- 兼容旧任务/旧 DB/旧提示词包；阶段二能力不足时自动回退到现有行为。

**Non-Goals:**

- 不做多 worker/任务并行/优先级队列；串行 worker 保留，靠看门狗保证队列活性。
- 不做「整本书分别喂给 10 个维度」或上下文缓存（留作后续独立变更）。
- 不改变十维产物契约、图谱契约、建书/导出出口、提示词分层包机制。
- 不做自动模型选择/分阶段模型路由；换模型由用户显式选择。
- 不重做拆书 UI，只补状态文案、降级标记与失败出口。

## Decisions

### D1 失败分类与统一重试策略

用一张显式矩阵替代 `except Exception` 全重试。分类在 `_call_with_retry` 的咽喉处实现，
所有调用点（卡片/L1/reduce/补写/地点）共用：

| 错误类 | 判定 | 动作 |
|---|---|---|
| `timeout` / 连接失败 | `AITimeoutError`、httpx 网络异常 | 瞬时：最多 3 次尝试，指数退避+抖动 |
| `rate_limit` | 429 / `rate limit` | 瞬时：遵循 `Retry-After`，降并发；单次不熔断 |
| `upstream_5xx` | 500/502/503/504 | 瞬时：退避重试 |
| `auth/config` | 401/403/400/404/405、模型不存在 | 终止：不重试，`error.kind=auth/config/route` |
| `content_filter` | 1301 / contentFilter | 隔离单元：跳过+warning；维度超阈值→降级 |
| `invalid_output` | 空 200、非 JSON | 1 次修正/拆分尝试，再隔离 |
| `truncated` | `finish_reason=length` / JSON 不完整 | 拆组或提预算；MUST NOT 原样重试 |
| `cancelled` | 用户取消 | 立即终止，不重试 |

实现要点：

- 拆书调用把 SDK 层 `max_retries` 设为 0（或构造专用 client），避免与管线重试相乘；
  重试策略单源在 `CallPolicy`，`ai_client` 只提供可选参数，不改变其他调用方默认行为。
- 退避：`base=1s`，`exp=2`，`cap=30s`，全抖动；429 优先 `Retry-After`。
- 内容审核阈值：单维度失败单元占比 >50% 或 >8 个单元 → 维度 `degraded`；否则任务继续。
- 截断：reduce 组二分；单份仍截断则 `degraded=输出上限不足`，不再烧重试。
- 熔断：每任务维护连续瞬时失败计数，阈值 `max(3, CONCURRENCY)`；触发后置
  `abort_event`，在途调用取消，任务 `failed(error.kind=provider_unavailable)`，
  checkpoint 保留，dispatcher 立即取下一个任务。429 单独处理：先降并发
  （4→2→1，AIMD），持续超时间窗才计入熔断。

### D2 动态超时与流式

固定 90/600s 与「输出预算可达 64k」不兼容。改为按预算计算：

- `usable_out = max_output_tokens * 0.75`
- `total_deadline = clamp(120 + usable_out / min_tps, 120, 1800)`，`min_tps` 取模型能力表
  或保守 20 tok/s；长输出允许更长总时限。
- `idle_timeout = 60~120s`：流式下按相邻 chunk 间隔判死；非流式回退为总 read timeout。
- 拆书调用优先 `chat_stream`（至少 `usable_out > 8k` 时）：边收边累计，记录
  `last_token_at`；JSON 在流结束后解析。若供应商不支持/流式不稳定，回退非流式，
  用 `total_deadline` 作为 read timeout。
- `ai_client` 需要把 `finish_reason`/`stop_reason` 暴露给调用方（新增可选返回值或
  `ChatResult`，保持旧接口兼容）；D1 的 `truncated` 判定依赖它。
- 流式收益：心跳真实、挂死快速判死、长输出不被 600s 截断；不以「流式」作为用户可见概念。

### D3 看门狗、墙钟与取消

- `run_task` 外层起一个 watchdog 协程，维护 `last_progress_at`（每个单元成功落库后更新）
  与 `last_token_at`（流式 chunk 更新）；阈值：拆卡 5 分钟、归并 15 分钟（后续可按 p50 自适应）。
- 超阈值：置 `abort_event`，取消主任务与在途 HTTP，任务
  `failed(error.kind=stalled)`，写 `stalled_at/stage`，dispatcher 继续下一任务。
- 任务墙钟：默认 `max(30min, 2×预计)`，上限可配；超过同样按 `stalled` 收场。
  墙钟是兜底，不替代单元级超时。
- 取消：`_call_with_retry` 每次尝试前查 `cancel_event`/status；每次 HTTP 调用用
  `asyncio.wait_for` 或任务取消；`_guarded` 不得吞 `CancelledError`（BaseException）。
  取消端点仍写 DB（事实源），进程内 event 只用于加速。
- 保留串行 dispatcher；看门狗保证「一个任务卡死不会堵死队列」。

### D4 单元级断点表

新增 `deconstruct_units` 表（迁移随 CLIENT_VERSION）：

| 列 | 说明 |
|---|---|
| `id` | uuid |
| `task_id` | FK deconstruct_jobs.id，索引 |
| `stage` | card / l1 / reduce / presence / place |
| `dim` | 维度 key；card/place 用空串或 `*` |
| `unit_key` | 章号 / 输入指纹 |
| `status` | running / done / failed / skipped |
| `output_json` | 成功产物（卡片/碎片/归并稿） |
| `input_hash` | 输入内容 sha256（防 stale 复用） |
| `attempts` | 尝试次数 |
| `error_kind` / `error_msg` | 失败归因 |
| `duration_ms` / `tokens_in` / `tokens_out` | 调用账 |
| `created_at` / `updated_at` | UTC |

唯一键 `(task_id, stage, dim, unit_key)`；成功即 upsert，先落库再更新 UI 状态。

`unit_key` 生成：

- card：章号（章文本变化由 `input_hash` 捕捉）。
- l1：`sha256(dim + prompt_version + 排序后的 (章号, 碎片文本))`。
- reduce：`sha256(dim + prompt_version + 排序后的子单元 key + 子输出 hash)`。
- presence：`sha256(章号 + missing_names + 章文本 hash)`。
- place：`sha256(book_name + 全部 place 碎片)`。

续拆：按 stage/dim 读取 `done` 单元，跳过；`input_hash` 不匹配的单元标 stale 并重算。
卡片可以继续留在 `dims_json.entries`（兼容旧任务），但新任务建议也写单元表；
过渡期实现「读两处、写单元表」。调用账由单元表聚合，不再单独建统计表。

为什么不把 partials 塞回 `dims_json`：每单元重写 915KB JSON 造成写放大，且无法记录
每次尝试/token/错误；表天然支持幂等、续拆与账本。

### D5 模型能力表与 token 估算

- `ModelCaps`：`context_window`、`max_output_tokens`、`long_context_threshold`（计价档）、
  `supports_json_schema`、`supports_stream`、可选 `rpm/tpm`。
- 解析顺序：任务显式覆盖（后续）→ 内置已知模型表 → provider 默认 → 保守默认
  （context 32k、output 4096/8192、无长上下文加价）。能力未知不阻塞任务，只在账本标注。
- token 估算：优先 `tiktoken`（OpenAI 兼容）；否则 CJK 字符≈1 token、ASCII≈0.3 token，
  加 15% 余量。用响应里的 `usage.prompt_tokens` 反向校准每个模型的系数并持久化。
- 打包：`_pack_by_tokens(items, budget)` 替代 `_pack_pairs/_pack_units` 的字符预算；
  字符上限只作为兼容默认。
- 长上下文计价保护：预计输入 > `long_context_threshold`（默认 128k）时拆小批次，
  除非任务显式 `allow_long_context`；MUST NOT 静默进入高价档。
- 不在本变更做 UI 能力编辑；内置表+环境变量覆盖足够，后续再加模型配置页。

### D6 能力感知规划：合批、单遍归并、质量门

**拆卡批次**

```
per_card_out = 1500 tokens（用真实 usage 校准）
usable_out   = max_output_tokens * 0.75
max_by_out   = floor(usable_out / per_card_out)
max_by_in    = floor((context_window - usable_out - prompt_overhead - margin) / per_chapter_in)
batch_size   = clamp(min(max_by_out, max_by_in), 1, 30)
```

参考：8k 输出→3–4 章；16k→8–10；32k→16–20；64k→20–30。批次内用
`deconstruct-card-batch` 模板，输入按章分隔，输出 **JSONL（一行一张卡，`no` 为首字段）**；
流式解析，每行完成即写单元表。校验：章号集合精确、无重复、必填键齐全；失败二分拆批，
直到单章；单章仍失败则隔离。只把创建时勾选的维度传给模板，减少输出体积。

**维度归并**

```
fragments_tokens = sum(estimate(fragment))
expected_out     = estimate_dim_output(item_count, compression_ratio)  # 用真实产物校准
single_pass      = fragments_tokens + synopsis + prompt <= input_budget
                  and expected_out <= usable_out
```

- `single_pass`：把该维度全部碎片一次性喂 `deconstruct-{dim}`，直接得终稿；跳过 L1/reduce。
  真实书 characters 10.7 万字碎片在 1M 上下文/32–64k 输出下可单遍。
- 否则：现有 L1 分批 + reduce；批次大小按 token/输出预算，不按固定 30k/40k 字符。
- reduce 截断：组二分递归；单份仍截断→`degraded`。MUST NOT 相同输入/预算重试 3 次。
- 不为用满上下文而把整本书按维度重复读取；维度只用卡片碎片（证据章号保留且便宜）。

**质量门**

- 20 章金标（从真实 258 章书取连续 20 章）：单章基线 vs 10/20 章合批 vs 单遍归并。
- 指标：逐章角色/事件召回（名称集合）、章号证据正确率、跨章串入率、产物条目数/字段完整率。
- 通过线：召回下降 ≤5%，跨章串入为 0，字段完整率 ≥99%；不达标则降批大小（20→10→单章）
  或关合批 flag。
- 质量门是阶段二上线前置；阶段一 P0 不依赖它。

### D7 可观测性与时间口径

- 调用账 = `deconstruct_units` 聚合：按 stage/dim 输出 calls/retries/failures/duration/tokens；
  `task_view` 增加 `stats` 摘要（不含原文/密钥）。
- `llm.log` 行增加 `task_id` 与 `operation`；通过可选 `trace` 参数从 `_call_with_retry`
  传到 `AIClient.chat`，不改变默认日志字段。
- `activity` 增加 `last_progress_at`、`last_token_at`、`retry_attempt`、`stage`、
  `done/total`；UI 用它渲染「模型 3 分钟未响应」而不是无限增长的秒数。
- 降级：`dims[dim].degraded` 已有写入，`task_view` 透出；前端详情用既有 warn pill 显示
  原因；完成态不再「全绿但实际降级」。
- 时间：后端统一 `datetime.now(UTC).replace(tzinfo=None)`（或带时区），`service._activity`/
  `_eta_seconds` 与 `pipeline._now()` 同源；前端 tools 页面改用 `parseServerTime`/
  `serverTimeMs`（`client/frontend/src/lib/serverTime.ts`）。测试用 `TZ=Asia/Shanghai` 与 UTC 双跑。
- `error.kind` 枚举：`auth`、`config`、`route`、`rate_limit`、`provider_unavailable`、
  `stalled`、`timeout`、`content_filter`、`invalid_output`、`truncated`、`cancelled`；
  失败面板按 kind 给文案/出口。

### D8 换模型续拆与自动续拆

- `POST /tasks/{id}/resume` 可选 body `{api_config_id?, ai_model?}`；校验走
  `resolve_client`，成功后更新任务并追加 `model_history`（`[{config, model, at}]`，
  存 `dims_json` 顶键或新列，设计取新列更清晰）。
- 单元断点在输出契约不变时跨模型复用；若模型能力不同导致输出契约变化，任务应提示
  「换模型可能改变产物口径」，但不强制重跑已完成单元。
- 自动续拆：`failed(provider_unavailable|stalled|timeout)` 时写
  `auto_resume_at = now + backoff(n)`、`resume_count`；dispatcher 每次轮询同时取到期的
    自动续拆任务。默认 3 次，退避 5/15/60 分钟；`auth/config/content_filter` 不自动。
  用户可关闭；UI 显示下次重试时间或已停止原因。
- `first_started_at` 保留，`last_started_at` 每次 claim 更新；不再覆盖历史。

### D9 迁移与发布顺序

- schema：新增 `deconstruct_units`，可选新增 `model_history_json`、`resume_count`、
  `first_started_at`、`auto_resume_at`；全部为 additive，升 `CLIENT_VERSION` 并跑 upgrade drill。
- 旧任务：继续读 `dims_json.entries`；新表为空时按旧路径执行；成功单元写新表。
  双读期结束后再考虑迁移历史卡片。
- 发布顺序：
  1. **P0 韧性**（D1/D2/D3/D7 的失败策略、看门狗、取消、UTC、降级可见）——不依赖提示词仓。
  2. **P1a 单遍归并/动态预算**（D5/D6 的维度部分）——使用现有维度模板，无提示词改版。
  3. **P1b 拆卡合批**（D6 卡片部分 + JSONL）——需提示词仓发 `deconstruct-card-batch`，
     按既有顺序：本仓合码 → 提示词仓发包 → 用户更新客户端；老包回退逐章。
  4. **P2 换模型/自动续拆/调用账 UI**（D7/D8）——可与 P1 并行。
- 开关：`DECONSTRUCT_CARD_BATCH=auto|off|N`、`DECONSTRUCT_SINGLE_PASS=auto|off`、
  `DECONSTRUCT_AUTO_RESUME=0|1`、`DECONSTRUCT_STALL_CARD_SEC`/`..._MERGE_SEC`。
  `off` 即回退现有行为；新表/新列保留不碍回滚。
- 回滚：关 flag → 恢复固定 30k/40k、逐章拆卡、L1+reduce、无自动续拆；已有单元表
  不影响旧路径（旧路径不读它）。

### D10 思考档位（2026-10-18 用户拍板）

拆书是结构化抽取：思考与输出共用 max_tokens（burn 预算是截断/空响应的放大器，真机
实证），且思考全在首 token 前是纯串行等待。任务级 `thinking_mode`（off 默认/low/inherit）
随任务保存、续拆沿用；`resolve_client` 折算成客户端构造覆盖（off＝thinking_enabled=False，
GLM-5.3 强制端点在请求层自动折算 enabled＋low；inherit＝跟随 ApiConfig，旧行为）。
创建页模型选择之下出三档下拉（原型 `ai-novel-c端-拆书.html` v7.2＋ADJUSTMENTS 登记）。
不加运行时开关（简洁优先）：档位是创建期决策，护栏由模板三铁律兜底。

## Risks / Trade-offs

- **合批质量回退** → 20 章金标质量门；不达标降批大小/关 flag；二分拆批限制单次影响面。
- **大调用失败影响面大** → JSONL 逐章落库；二分拆批；看门狗/流式空闲超时。
- **长上下文计价抵消收益** → token 计价档保护（默认 <128k）；不整书×维度重复读；
  账本显示实际 input tokens，按任务可审计。
- **自动续拆烧配额** → 次数/退避上限、默认关闭或显式开启、auth/content 不自动。
- **看门狗误杀慢但正常的调用** → 以 `last_token_at` 而非仅单元完成时间判活；阈值可配；
  只有持续无 chunk 且无单元进展才判 stalled。
- **熔断误杀 429 抖动** → 429 单独降并发/Retry-After，不计入连续失败；阈值按并发取 max。
- **schema 迁移风险** → additive、upgrade drill、旧任务双读、失败可回退旧代码。
- **时区修复改变显示** → 双时区测试 + 相关快照更新；只改展示，不改存储。
- **单元表写放大** → 每单元一行 upsert，比 915KB 全量 JSON 小；按任务/阶段索引查询。

## Migration Plan

1. 先落 P0：错误矩阵、breaker、watchdog、cancel、UTC、degraded 透出；在 dev 栈用故障注入
   桩验收（挂起/401/429/空 200/截断/1301）。
2. 建 `deconstruct_units` 表并升 `CLIENT_VERSION`；旧任务双读；跑 upgrade drill。
3. 落 P1a 单遍归并（flag auto，能力表默认保守）；用真实 258 章书对比归并质量与调用数。
4. 提示词仓发 batch 模板后落 P1b；先 10 章批，金标通过再 auto 到 20–30 章。
5. P2 换模型/自动续拆/账本 UI；自动续拆默认关闭，灰度开启。
6. 回滚：关 flag 即回旧路径；新表/列 additive 不回滚。

## Open Questions

- 目标模型的真实 `max_output_tokens`、长上下文计价档、流式稳定性：由阶段二 20 章基准
  实测；只影响批大小/开关默认值，不改变本设计结构。
- 供应商是否稳定支持 JSONL/结构化输出：不支持则回退 `{"chapters":[...]}` + 二分拆批；
  仍不改变失败策略。
- 历史卡片是否迁移到单元表：先双读，按真实写放大数据再决定；不影响新任务。
