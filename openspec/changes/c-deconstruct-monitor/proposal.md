# 拆书运行监控面板

## Why

用户反馈（2026-10-19，附参考截图）：拆书动辄数小时，当前详情页只有百分比＋十行文字明细，
看不到「现在到底在干什么、快不快、刚才几次调用成没成」。参考外部产品的拆书监控形态，
把运行态详情升级为监控面板：总进度＋批次/卡片账、各维度进度条、当前动作＋时长、
近 5 分钟速度、最近调用流水（耗时/产出/成败与原因），并给「测试模型」一键出口。

数据不需要新表：c-deconstruct-resilience 落的单元账（`deconstruct_units`：stage/dim/
status/attempts/error_kind/duration_ms/tokens_out/updated_at）就是每次模型调用的账本，
监控是它的一个只读聚合视图。

## What Changes

- **调度即现**：单元**派发即写 running 行**（管线 6 类站点：拆卡/合批/归并/收敛/在场补写/
  地点归并），完成时覆盖终态；任务终局清扫 running 残留为 failed(cancelled)——
  「在途 N」与最近明细随 1.5s 轮询实时反映调度。
- **详情接口**：`GET /deconstruct/tasks/{id}` 运行态（queued/running）新增 `monitor` 块——
  在途数、归并批进度（l1 done/total）、近 5 分钟速度窗（成功/失败次数、平均耗时、产出 tok、
  累计调度）、最近 8 条调度流水（时间/**调度对象（章号/维度·阶段）**/耗时/产出/成败/失败原因
  kind）、并发度。终态为 `null`。聚合只取计数列，**不读 `output_json` 大载荷**（reduce
  partials 不得进 1.5s 轮询）；`reduce_state` 检查点非模型调用，与 task_stats 同口径排除。
- **详情页运行态**（监控面板，参考截图布局）：
  - 总进度条（复用 `.pbar`）＋「批次 N/M · 卡片 N/M · 在途 N · 并发 N」摘要行；
  - 各维度一行进度条（条＋`进行中 · 归并 x/y`/完成/排队/失败 文案不变，容器从文字行换条）；
  - 当前动作（activity 账原样）；
  - 「速度（近 5 分钟）」摘要＋「最近」调度流水（进行中行置顶「● 进行中」；✓ 绿 /
    ✕ 红＋error_kind）；
  - 新增「测试模型」按钮：复用模型配置探针（`/api-configs/{id}/test`），结果 toast。
- **不改**：取消/续拆/删除等既有出口；失败面板；轮询节奏（沿用详情 1.5s）；不新增独立
  悬浮窗/折叠挂件（参考图为外部产品形态，v1 面板放任务详情运行态——独立窗口需 pywebview
  多窗口支持，留后续拍板）；速度以 tok 计（单元账只有 tokens，不读载荷换算字数）。
- **拍板修订（2026-10-19 boss「具体的调度任务要在明细刷新出来」）**：原「在途降级为并发 N」
  收回——单元派发即写 running 行，在途为真实计数；流水行从只报阶段升级为具体调度对象。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `deconstruct-book`: 新增「运行监控面板」Requirement（ADDED；主 spec 已于 #899 落库，
  基线干净）。`c-deconstruct-resilience` 的 open delta 不触碰监控，无叠层冲突。

## Impact

- **后端**：`deconstruct/service.py`（`monitor_view` 聚合）、`deconstruct/router.py`
  （详情挂 `monitor`）。零 schema 变更、零新端点。
- **前端**：`deconstructApi`（类型）、`TaskDetailPage`（运行态监控面板＋测试模型按钮）、
  `index.css`（`.mon-*`，仅令牌）。
- **测试**：后端 monitor 聚合（窗口边界/排除 reduce_state/终态 null/流水字段）；
  前端面板渲染＋测试模型两臂＋既有断言回归（文案保持原串，仅容器换条）。
- **风险**：低——只读聚合；单位账已有 task_stage 索引。

## Design Impact

- **受影响端**：C端。
- **屏/弹层**：`/tools/deconstruct/:id` 运行态就地升级，无新页面/弹层。
- **共享段**：不触碰 `base.css`；`.mon-*` 落 `index.css` tools 段，仅引用既有令牌；
  `.pbar` 复用 book.css 既有类。
- **原型**：`docs/design-c/drafts/ai-novel-c端-拆书.html` 运行态补监控面板注记；
  `ADJUSTMENTS.md` 登记。
