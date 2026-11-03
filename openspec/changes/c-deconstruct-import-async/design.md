## Context

动机与实测证据见 proposal.md。实现侧现状（基线 `main` dc0c33c8，行号已按评审核对）：

- `POST /deconstruct/tasks/{id}/import-book`（`deconstruct/router.py:306`）同步调用
  `apply.import_book`（`apply.py:174`）。唯一慢点是 `_condense_world`（`apply.py:125`）：
  `_world_source_over`（`apply.py:96`）为真时发一次 `deconstruct_condense`
  （`max_tokens=3000`），真机 23.128s；其余写入全部 <0.2s。
- 幂等键 `task.book_id` 在 `create_project` 之后立刻提交（`apply.py:227-230`）。
- **`status` 在这套代码里同时承担三职**：生命周期、能力门（`router.py:345/389/430` 三个出口
  与 `:464` 删除都按 `== "completed"` 单值判定）、徽标口径（`router.py:140-150`）。
  `models/deconstruct.py:20` 的 `STATUSES` 是**死常量**（全仓无人 import），真正的门是字符串比较。
- 建书勾选集只存在于请求体（`router.py:326-329` → `apply.py:200-204`），`_selected` 回落的
  仅 7 个设定项（`apply.py:80-85`，不含 structure/relations/techniques）。
- 前端有**两套轮询**：清单 hook（`hooks/useDeconstructTasks.ts:14` 的 `ACTIVE`）与详情页内联
  `refetchInterval`（`TaskDetailPage.tsx:154-162`），都只认 `queued/running`。
- 清单页状态映射无兜底：`TaskListPage.tsx:100` 取 `STATUS_PILL[t.status]` 后直接读 `.cls`。
- `project_settings` KV 路径是白名单（`filesystem/paths.py:57-72`），未登记路径写入静默 no-op
  （`db_storage.py:75-78`）；专用键先例：`threads` / `style-quant` / `book-prefs`。
- 后端**没有 `asyncio.create_task` 先例**；长任务纪律是 daemon 线程 + status 收敛。桌面壳关窗
  只给 3 秒（`packaging/build/pywebview_app.py:506`）后 `os._exit`（`:526`）。
- `storage_busy` 只是请求级异常处理器（`main.py:388-405`），**不覆盖后台写入**；SQLite 侧只有
  WAL + `busy_timeout=5000`（`db.py:18-22`），各域服务自开 session 自 commit。
- 无 alembic、无就地 ALTER：`db_lifecycle` 按 schema 指纹分流改名，任何模型变更都触发用户迁移。

## Goals / Non-Goals

**Goals:**

- 建书整段作为一个后台阶段跑完：点确认即返回，可离开、可关窗、可见、可取消、可重试。
- 三条不变量做成**结构保证**而不是愿望：①失败/中断不留可见半成品；②幂等键不重复建书
  （含全部存量任务）；③取消/中断/删除任何交叉都收敛到确定状态。
- 复用既有任务状态机、清单、详情、sweep 与徽标口径，不新增任务类型/表/线程。
- 零 DB schema 变更、零新提示词模板。

**Non-Goals:**

- 不做「先落一部分、后台再补」的分段交付（用户已否决）。
- 不做按项断点续灌（写入阶段失败即整单重跑，避免「（拆书N）」副本角色）。
- 不给 `Novel.status` 加隐藏值（见 D2 的取舍）。
- 不做建书细粒度进度条（精炼是一次调用，没有可信分段）。
- 不改拆书管线与逐字段回填语义。

## Decisions

### D1 · 建书三态 + 一次建书一个身份（attempt），载荷进 `dims_json.import`

`DeconstructJob.status` 新增 `importing` / `imported` / `import_failed`（字符串列，零 schema）；
载荷放 `dims_json` 顶层 `import` 键（管线 `_state_json` 保留未知顶键，`pipeline.py:1495-1501`）：

```
import = {
  run_id,          # 本次建书身份（uuid，受理时生成）
  items,           # 受理时持久化的灌入勾选（IMPORT_ITEM_KEYS 子集，去重保序）
  step,            # refine | writing | waiting
  started_at, finished_at,
  draft_book_id,   # 预分配的书 id（见 D4），受理时即落
  warnings,        # 与书侧提示条同源
  error: {message, kind, retryable},
  attempts: [{at, result, kind, tokens}]   # append-only，可观测
}
```

- `status` 仍是唯一生命周期事实源；`run_id` 解决「我怎么知道自己是当前这次」——所有终态/清理写
  都带 `WHERE status='importing' AND run_id=本次值`，rowcount=0 即让位退出。
- 三处映射必须同步扩展（评审核实为 20+ 分支点，不是三处）：后端 `router.py` 的 5 处状态门 +
  `badge` 查询 + `delete_task` + `startup_sweep`；前端 `deconstructApi.ts` 的 status 联合类型、
  `TaskDetailPage.tsx` 状态分支与内联轮询、`TaskListPage.tsx` 的 pill/摘要、`hooks` 的 `ACTIVE`。
- **否掉的替代**：新增 `import_state` 列（可索引，但触发一次全量用户迁移）；独立
  `deconstruct_imports` 表（同上 + 一套生命周期）；新建「建书」任务类型（清单要多类型、徽标要分账）。

### D2 · 慢调用前置 + 可见性用可验收的措辞

执行顺序：①读产物与投影（纯内存）→ ②`world` 勾选且超契约时调一次 `deconstruct_condense`
（**此时还没有书行**）→ ③建书 + 全部写入（<0.2s）→ ④终态翻转。

- 精炼前置后，半本书的暴露窗口只有写入阶段的 0.2 秒量级；失败即软删，启动 sweep 兜底。
- **spec 措辞按实际改**：「新书在建书完成的同一次状态翻转后可见；写入窗口 ≤2 秒；失败/中断
  不留可见半成品」。不写「SHALL 只在全部写入成功后才可见」这种无法验收的绝对句。
- **否掉的替代**：给 `Novel.status` 加 `importing` 并让书架/配额过滤——能把这 0.2 秒也抹掉，
  但要改十几处 `!= "deleted"` 读路径（含配额、角色库、图像资产），漏一处的后果是「书看不见」或
  「配额算错」，风险高于收益。若将来真需要，单独开 change。
- **否掉的替代**：把写入包成单事务——`DatabaseFileBackend` 每次写自开 session 自 commit
  （`db_storage.py:75-91`），`create_character`/`create_volume`/`batch_create_hooks` 也各自提交，
  侵入四个域服务只换来抹掉 0.2 秒。

### D3 · 执行体：`create_task` + registry + 看门狗，单飞以 DB 条件更新为准

- 受理：条件 UPDATE `completed → importing` 与 `run_id/items/draft_book_id` 同一次提交；返回 202；
  响应后启动执行体。
- 执行体：模块级 `_inflight: dict[str, asyncio.Task]` 保留引用 + `add_done_callback` 记日志；
  主体 `try/except BaseException/finally`，异常路径用**独立短事务 + `asyncio.shield`** 写
  `import_failed`（`CancelledError` 不是 `Exception`，桌面壳 3 秒关停会走这条）。
- **单飞以 DB 为准**：条件 UPDATE 保证同一任务只有一个 `run_id` 在 `importing`；内存 `asyncio.Lock`
  只做同 loop 内的排队优化，且按 loop 懒创建（测试的多 loop / dispatcher 线程自带 `asyncio.run`
  不会撞死锁）。
- **看门狗**：精炼阶段上界（默认 180s，`import.started_at` 起算）→ 判 `failed(stalled, retryable)`，
  对齐 resilience 已有的 watchdog 形态；视图侧再加一层陈旧兜底（`importing` 且 `started_at` 超过
  上界 2 倍按可重试呈现）。
- 启动 `startup_sweep` 增一步：`status='importing'` → `import_failed(interrupted)`，软删
  `import.draft_book_id`、清 `book_id`。
- **否掉的替代**：塞进拆书 dispatcher（排在 30 分钟拆书后）；第三个常驻 dispatcher（只为排队公平）。

### D4 · 预分配书 id + 幂等键后移 + 存量任务兼容

- 受理时生成 `book_id = uuid4()`，与 `run_id/items` 同一提交写进 `import.draft_book_id`；
  `create_project` 增加可选 `book_id` 参数。这样任何时刻被杀，sweep 都有 id 可清（现状
  `create_project` 内部就 commit 且 `status='active'`，`novels/service.py:83-85`，拿不到 id 就是永久孤儿）。
- 写入全部成功 → 一次收尾写 `task.book_id`、`status='imported'`、`import.state`/`finished_at`。
- 写入失败 → **先**写 `import_failed`（含 draft_book_id）并提交，**再**尝试软删；软删失败由 sweep
  按 `draft_book_id` 重试（顺序反了会卡在 `importing`）。
- **入口幂等第一判定永远是 `task.book_id`（不看 status）**：
  - 书存在（含本次变更前的 `completed + book_id` 存量任务）→ 200 返回同一本书，顺带把状态读时
    升级为 `imported`；
  - 书已被删/不存在 → 清键、按当前勾选重建（保留既有「删书后再建书」语义）；
  - `importing` → 409 返回当前状态，不排第二次。
- 重试沿用同一份 `items`（从 `import.items` 读），不回落默认勾选。

### D5 · 取消：真中断 + run_id 守卫

- 取消端点：条件 UPDATE `importing → completed`（清 `step`），并 `_inflight[task_id].cancel()`
  作为加速；执行体在阶段边界与收尾前校验 `run_id`，不符即清理自己的 draft 并退出。
- **在途模型调用真中断**：复用管线现成形态（`pipeline.py:545-556` 的 `_Stopper` + `asyncio.wait`
  竞速），取消后 SHALL NOT 继续烧 token。状态仍是唯一事实源，Event 只是加速器。
- 取消端点**不挂 `require_ai_access`**（只登录+档位门）：Key 失效/降档的用户必须能止损取消。
- **取消后立刻重建**：新一次受理生成新 `run_id`，旧执行体的条件写 rowcount=0 → 只清理自己的 draft，
  不影响新一次（这是评审给的反例序列 1，必须有用例）。

### D6 · 状态矩阵（后端判据一处写死，前后端共用口径）

| 状态 | 结果目录/预览 | 导出 | 收进角色库 | 建书 | 取消 | 重试 | 删除 | 打开这本书 |
|---|---|---|---|---|---|---|---|---|
| completed（未建书） | ✅ | ✅ | ✅ | ✅ 受理 | — | — | ✅ | — |
| importing | ✅（只读，可预览） | ✅ | ✅ | 409 进行中 | ✅ | — | ❌ 409「先取消」 | — |
| imported | ✅ | ✅ | ✅ | 200 幂等回同一本 | — | — | ✅ | ✅ |
| import_failed | ✅ | ✅ | ✅ | 可重试→重跑；不可重试→回同一失败 | — | ✅（可重试时） | ✅ | — |

落地方式：后端定义 `RESULT_READY = {"completed", "importing", "imported", "import_failed"}` 常量，
`export`/`library-candidates`/`to-library` 与详情页结果块统一用它；**不要**继续散落写
`== "completed"`。`delete_task` 增 `importing → 409`。前端结果块渲染条件同步改为该集合。

### D7 · 前端：确认四臂、轮询统一、翻转触发一次失效

- 确认建书四臂，每臂都有出口：**202** → 关弹窗 + toast「已开始建书，可以离开」+ 失效任务 query；
  **200 幂等** → toast「这本书已经建过了」+ 失效（不跳转）；**4xx**（满额/档位/409）→ 弹窗内错误
  或 toast，弹窗保留；**网络失败** → toast 报错，弹窗保留。`busy` 只防这一次提交。
- **两套轮询合并**：把活动态判定抽成共享纯函数，`ACTIVE = queued | running | importing`；详情页
  内联 `refetchInterval` 改为调同一函数（这是本次要修的主屏，漏改等于症状不消失）。
- **终态只触发一次**：hook 内用 `useRef<Set<string>>` 记录已见终态的任务 id，只在
  `importing → imported/import_failed` 翻转时失效一次 `queryKeys.novels` 与该任务详情。**不要**
  把 `imported` 放进 `ACTIVE`（`ToolsMenu` 全局常驻 + `refetchIntervalInBackground`，会让 1.5s
  轮询永不停止，撞 `shelf-request-budget` 的请求预算口径）。
- **清单页兜底**：`STATUS_PILL[t.status] ?? {label: t.status, cls: "pill"}`，并补「未知状态不崩」用例
  （现在 `TaskListPage.tsx:100` 会 TypeError 白屏，回滚/脏数据直接整页挂）。
- **详情结构**：`showResults = status ∈ RESULT_READY` 共享结果块；三态各自 banner 与主 CTA；
  `import_failed` 用独立面板读 `import.error.{message,kind,retryable}`，**不得**复用 `failed|cancelled`
  分支（那里读 `task.error` 空串并会出现「从断点续拆」→ 409）。默认全选 effect 的条件
  （`TaskDetailPage.tsx:187-193`）同步扩到该集合，否则显示「已选 0/N」、导出报「至少勾选 1 份」。
- **按钮错误出口**：取消/重试走本地 `busy` + `toast.error`，不用 `act()`（它的 `exitErr` 只渲染在
  弹窗里，弹窗关着＝无出口）。取消用行内两步确认并说明「已精炼的结果不保留」；重试/取消成功后显式
  失效该任务 query。
- **秒数**：用 `import.started_at` 单独算并本地 1s tick（现有 `elapsedLabel` 按分钟算，23 秒会显示
  「已运行 1 分内」）。
- **文案修正**：弹窗现在承诺「确认后直接进新书设定页（会标待确认）」（`TaskDetailPage.tsx:864`、
  `drafts/ai-novel-c端-拆书.html:17/894`），改为「确认后开始建书，可以离开；完成后在任务详情打开这本书」。

### D8 · 建书提示条：专用 KV 键 + 专用端点，落点在设定页顶部

`deconstruct-import-notice` 必须按专用键先例登记（照 `book-prefs`：`filesystem/paths.py` 加常量
+ `route_relative_path` 分支，**不进 `PATH_TO_KEY`**，否则会漏进通用 `/settings/{type}` 白名单），
并新增 `settings/import_notice_router.py`：`GET`（无则空）+ `DELETE`（幂等，键不存在也 200）。

- 落点是 `SettingsView` 页顶（默认面板是「题材」，`WorldSettingPanel` 只有切到世界页才挂载——
  放那里等于用户看不到）。
- 内容分级：截断/降级=warn，幂等/说明=info；关闭即删键，删除失败要 toast（不静默）。
- 与 `import.warnings` 的关系：书侧 KV 是给用户看的副本，任务详情读 `import.warnings`；两份
  允许分叉并在此登记（不做跨后端事务），以后者为准可重生成。

### D9 · 接口契约

- `POST /deconstruct/tasks/{id}/import-book`：命中 D4 的四条分支（200 幂等 / 202 受理 / 409
  进行中 / 4xx 档位·满额）。受理时校验并持久化 `items`（白名单 + 去重 + 保 `IMPORT_ITEM_KEYS` 序）。
- `POST /deconstruct/tasks/{id}/import-book/cancel`：仅 `importing` 可取消；除登录外不做 AI/档位门。
- `DELETE /deconstruct/tasks/{id}`：`importing` → 409「建书中，请先取消」。
- 满额：受理时查一次（快速失败、不烧 AI）+ 执行体 `create_project` 前再查一次（持锁期间防并发越过）；
  `require_project_limit` 在 handler 内 `await`，**不要**挂成 `Depends`（会在 200/409 分支之前 403）。
- 时间一律用 `pipeline._now()`（UTC naive，与 `service._activity/_eta_seconds` 同源）。

### D10 · 徽标与心跳

- `importing` 计入活动态（顶栏心跳可见「建书中」），失败后计入「已完成未取结果」（需处理），
  `imported` 视为已消费。避免 1→0→1 闪烁。

### D11 · 可观测性

- `ai_client` 的 `ai_call` 行带 `task_id`/`run_id`（现在没有，异步后请求行与 23 秒调用行会失去
  时间对齐，本次定位问题的证据链会消失）。
- `deconstruct_condense` 记账进 `import.attempts`（时间、结果、kind、tokens）；重试重付的成本可见。

## Risks / Trade-offs

- [回滚会白屏] 旧版本清单页遇到未知状态取 `pill.cls` 直接 TypeError，整页崩（不是「回落原始串」）。
  → 收敛脚本**必须独立于新版本**交付（随包放在 `scripts/`，或在回滚步骤里手工执行 SQL）；
  更稳的做法是先发一个只读兼容补丁（清单默认 pill + 详情 `?? status`）。
- [写入窗口 0.2s] 书架/配额在这段时间能看到书。→ spec 已改为可验收措辞；失败即软删 + sweep 兜底。
- [软删留垃圾] 软删只改 `Novel.status`，`project_settings`/characters/volumes/relations/盘目录
  留着，且 slug 查重不看 deleted（`novels/service.py:40-44`），重试会累积垃圾行。→ 本变更接受
  （不可见、随备份带走），在 tasks 登记为已知债。
- [并发写 SQLite] `storage_busy` 不覆盖后台路径，5 秒等不到锁就是 `OperationalError`。→ 写入阶段
  外围加**有界重试**（仅 `database is locked`/`disk I/O error`，退避 3 次），其余直接 `import_failed`。
- [dims_json 双写者] 管线自称唯一写者（`pipeline.py:1497`），import 成为第二个。→ 加断言
  （`importing/imported/import_failed` 状态下管线不得启动）+ 用例；写 `import` 时必须基于整份
  `dims_json` 读改写，不能只写 `{"import": ...}`。
- [取消与重建的 ABA] → D1 的 `run_id` + D5 的条件写，配一条反例用例（取消→立刻重建）。
- [AI 仍要 23 秒] → 本变更只保证「不用盯着等」；缩短需另开 change（把精炼移出建书路径）。
- [旧任务无 `import` 键] → 一律按 `completed` 处理；`completed + book_id` 走 D4 的存量兼容。

## Migration Plan

- 零 DB schema 变更；发布即生效（前后端同包）。
- **不能后端先合**：旧前端的清单页会对未知状态白屏、详情页结果块整块消失、三出口全 409。
- 可独立验收的第一刀是「重排 apply + 幂等键后移」（保持同步接口不变、只消除半本书与重试拿回
  半本书的病根）；三态状态机 + 执行体 + 前端三态必须同一个 PR。
- 回滚：先跑收敛脚本（`importing` → `completed` 并软删 `draft_book_id`），再回旧版本；否则清单页崩。

## Open Questions

（无。三个曾待拍板的点已按上文定案：可见性用可验收措辞而非隐藏状态 D2；取消真中断在途调用 D5；
失败带 `kind/retryable` 分诊 D1/D6。若否决任一条，改的是 D2/D5/D1 三节与对应 spec 句子。）
