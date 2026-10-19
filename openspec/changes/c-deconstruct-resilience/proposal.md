# 拆书管线韧性与调用预算

## Why

真实 258 章、81.5 万字的拆书任务结构上至少 **284 次模型调用**，其中 258 次是逐章拆卡（91%）。
问题不只是“调用多”：当前管线对模型故障没有止血机制——单元 3 次重试叠加 SDK 1 次重试、
`gather(return_exceptions=True)` 要等全部单元结束、没有熔断/看门狗/任务墙钟。provider 挂起不回时，
一个任务最坏可空转 **5–10 小时**才失败，串行 dispatcher 还会堵住后续所有任务；用户取消也要等
在途 600s 调用与重试结束才生效。真实任务里 `characters`/`world` 两个维度因 8192 输出截断做了
3 次注定失败的 reduce 重试后降级，`mainplot` 被内容审核拒掉后整维降级；而任务详情仍显示全绿。

2026-10-17 用户确认目标模型具备 **1M 上下文**。输入窗口不是当前瓶颈，输出预算才是：每章卡片约
1.5k tokens 输出，258 章约 390k 输出 tokens；即使 64k 输出上限也要 6 次以上才能写完卡片。
因此本变更分两阶段：先把失败变可判定、可打断、可续拆；再按模型能力（上下文/输出/token 计价）
规划调用预算，把 1M 上下文用在单遍归并与合批上，而不是整书重复读取。

## What Changes

- **失败策略矩阵**：只重试 timeout/连接/429/5xx；鉴权、400、模型不存在等确定性错误立即失败；
  内容审核按单元隔离并留告警，不因一章 1301 拖垮整本；JSON 截断检测 `finish_reason=length`
  后拆组或提预算，**不再原样重试**。瞬时失败连续 N 次触发熔断，任务以
  `provider_unavailable` 失败并保留断点，dispatcher 立刻处理下一个任务。
- **看门狗与任务墙钟**：每完成一个单元更新 `last_progress_at`；拆卡/归并分别设无进展阈值，
  超时判 `stalled`、取消在途调用、释放队列。用户取消贯穿重试循环与在途 HTTP 调用，目标 10 秒内生效。
- **单元级断点**：新增 `deconstruct_units`（L1 批/reduce 组/卡片/补写逐单元落库）；
  续拆只补未完成单元，不再“维度失败整维重跑”。单元记录同时作为调用账本。
- **能力感知调用预算（阶段二，基准门控）**：新增模型能力表（`context_window` /
  `max_output_tokens` / 长上下文计价档）与 token 估算器；批大小由输出预算决定，而不是固定 30k 字符。
  短章拆卡合批（JSONL 流式、逐章断点、失败二分拆批）；维度碎片在窗口与输出允许时**单遍归并**，
  否则保留 L1+reduce；1M 上下文只用于“单遍/更大批次”，不用于整书×10 维度重复读取。
  若实测输出仍为 8k，则只做 3–4 章合批，不承诺 20 次级总调用。
- **换模型续拆与自动续拆**：`/resume` 可携带 `api_config_id`/`ai_model`，记录模型历史；
  瞬时故障可退避后自动续拆有限次，鉴权/内容审核失败不自动重试。
- **可观测性**：每任务调用账（op/attempts/ok/fail_reason/duration/tokens）；`llm.log` 带 `task_id`；
  `dims.degraded` 在详情页可见；后端 activity/ETA 与前端时间显示统一 UTC。
- **不改**：逐章拆卡作为证据粒度的产品口径、建书/导出出口、图谱契约与提示词分层包机制不变。

## Capabilities

### New Capabilities

无。本变更是在既有拆书能力上修改执行策略与可观测行为，不引入新 capability。

### Modified Capabilities

- `deconstruct-book`: 修改「任务队列与串行调度」「十维度拆解管线与断点续拆」「任务清单与详情」，
  并新增失败策略/熔断/看门狗/单元断点/调用预算/调用账/换模型续拆等 Requirement。
  基线为活跃变更 `c-deconstruct-book`（已实现未归档，主 `openspec/specs/` 尚无该 capability）；
  归档时须先 sync/归档 `c-deconstruct-book`，再归档本变更，避免 delta 丢失基线。

## Impact

- **后端**：`client/backend/deconstruct/{pipeline,dispatcher,service,router}.py`、
  `models/deconstruct.py`（新表/字段）、`ai_client.py`（暴露 finish_reason 与可选流式/超时参数，
  不改变既有调用方默认行为）、`api_configs`（内置模型能力表或等价解析器）。
  新表改变 schema 指纹：须升 `CLIENT_VERSION` 并跑 upgrade drill。
- **前端**：`TaskDetailPage`、`TaskListPage`、`useDeconstructTasks`、`deconstructApi`；
  `serverTime` 统一时间解析。无新增页面。
- **提示词仓（awesome-novel-prompts）**：阶段二新增/改造 `deconstruct-card-batch`
  （按章 keyed 的 JSONL 输出契约）与可选的维度单遍模板参数；发布顺序仍为
  本仓合码 → 提示词仓合入+发包 → 用户更新客户端。
- **测试**：故障注入桩（挂起/401/429/空 200/JSON 截断/内容审核）、调用次数上限钉、
  20 章金标质量门、`TZ=Asia/Shanghai` 时间口径测试、升级演练。
- **风险**：合批质量回退（需金标门）、长上下文阶梯计价（可能抵消合批收益）、
  自动续拆消耗配额（需上限与显式开关）、schema 迁移（需演练）。

## Design Impact

- **受影响端**：C端。
- **屏/弹层**：`/tools` 任务清单、`/tools/deconstruct/:id` 详情；无新增页面/弹层。
- **对象状态**：运行中增加「模型无响应/正在重试」说明；失败面板按 `error.kind` 区分
  `provider_unavailable` / `stalled` / `timeout` / `content_filter`；完成详情增加维度
  `degraded` 标记。不新增第七种任务状态（仍用 failed + error.kind）。
- **共享段**：不触碰 `base.css` 令牌、基础组件类或两端共享段；复用既有 notice/pill 的
  `warn` 语气，不新增 `.b`/`.strip`/第四种胶囊。
- **原型**：不改布局与视觉形态，属状态文案与既有组件复用。以
  `docs/design-c/drafts/ai-novel-c端-拆书.html` 为视觉真值补三态注记，
  在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记文案偏差；设计工件由实现侧自查，
  不需要设计侧会话。若评审认为需新增原型，则在任务 0 追加 `prototypes/deconstruct-tools.html`
  的状态补注，不阻塞后端阶段一。
