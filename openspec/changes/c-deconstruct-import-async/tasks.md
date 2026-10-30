# 建书作为任务的整段异步阶段 — 实施任务

> 评审整改说明：本版已折入三份评审（后端架构／前端／架构师）的 4 个 P0 与主要 P1。
> 所有"现状把 `completed` 当单值门"的分支点必须一次性改干净，漏一处即 happy path 回归。

## 0. 原型先行（C端 UI 变更）

- [x] 0.1 在 `docs/design-c/drafts/ai-novel-c端-拆书.html` 补：任务详情建书三态（建书中步骤＋已运行秒数＋取消／已建书＋打开这本书／建书失败＋原因＋按可重试性给出口）、建书失败的独立面板（结果目录与出口共存，且不出现「从断点续拆」）、清单行三类徽标与摘要、出口弹窗「确认即关闭＋已开始建书」、取消的二次确认态。验证：原型可静态打开，各态可切换；不新增色彩/字号档位。
- [x] 0.2 修正原型与实现里的旧承诺：弹窗文案「确认后直接进新书设定页（会标待确认）」改为「确认后开始建书，可以离开；完成后在任务详情打开这本书」。验证：`rg "直接进新书" docs/design-c client/frontend/src` 仅剩改后文案。
- [x] 0.3 新书设定页顶部提示条（无 parity 基线）在 drafts 补画，并在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记（理由、与原型关系、共享段零改动）。验证：`cd client/frontend && npm run design:lint` 通过；登记条目入库。
- [x] 0.4 三态静态截图入 change 目录（建书中/已建书/建书失败＋出口共存），供评审对照。验证：截图路径写进 PR 描述。

## 1. 后端：状态门统一与受理

- [x] 1.1 定义 `RESULT_READY = {"completed", "importing", "imported", "import_failed"}`（`deconstruct/service.py` 单一常量），把 `router.py:345`（export）、`:389`（library-candidates）、`:430`（to-library）的 `status != "completed"` 全部改为集合判定；`library-candidates` 的拒因按状态区分（建书中≠"任务还没拆完"）。验证：后端契约测试「结果目录三出口 × 四态」矩阵（16 格，逐格断言 200/409 与文案）。
- [x] 1.2 `delete_task`（`router.py:464`）增 `importing → 409「建书中，请先取消建书」`。验证：用例断言 409 与任务仍在。
- [x] 1.3 受理分支四臂：`task.book_id` 指向现存书（**含存量 completed+book_id**）→ 200 幂等同书 + 读时升级 `imported`；书已删/不存在 → 清键重建；`importing` → 409 返回当前状态；否则条件 UPDATE 抢 `importing` → 202。验证：契约四臂 + 「存量 completed+book_id 不建第二本」回归（对齐 `test_deconstruct_api.py:263` 删书重建语义）。
- [x] 1.4 受理时把 `items` 规范化后与 `run_id`、预分配 `draft_book_id` 一次提交进 `dims_json.import`（白名单 `IMPORT_ITEM_KEYS`、去重保序、空则默认 8 项）；执行体与重试只读该值。验证：契约用例「非默认勾选（勾上 structure）→ 202 → 建出的书只含所选维度」；重试用例断言两次执行 items 一致。
- [x] 1.5 取消端点 `POST .../import-book/cancel`：仅 `importing` 可取消（条件 UPDATE 回 `completed`），并 `_inflight[task_id].cancel()`；**不挂 `require_ai_access`**（Key 失效/降档也必须能止损）。验证：用例覆盖可取消/409/降档用户仍可取消。
- [x] 1.6 满额：受理时查一次（快速失败、不烧 AI）+ 执行体 `create_project` 前再查一次；`require_project_limit` 在 handler 内 `await`，**不挂 `Depends`**（否则在 200/409 之前 403）。验证：超限用例断言 403 且 `deconstruct_condense` 调用数＝0；两任务先后受理时第二次在写入前被拦。
- [x] 1.7 写 `import` 必须基于整份 `dims_json` 读改写（保留未知顶键），并加断言：`importing/imported/import_failed` 状态下管线不得启动（`run_task` 入口守卫）。验证：单测 + 「管线补丁后 import 键仍在」的回归用例。

## 2. 后端：整段执行体

- [x] 2.1 `apply.import_book` 重排：①读产物与投影（纯内存）→ ②`world` 勾选且超契约时调 `deconstruct_condense`（**此时不建书行**）→ ③建书 + 全部写入 → ④终态。精炼结果作为世界写入 body；「条目超上限截断」的 warning 循环作用在**最终 body**（精炼结果）上，不能只留机械路径。验证：假 client 记录调用序，断言「精炼调用 < 建书行创建」；世界＝精炼结果且截断 warning 仍在。
- [x] 2.2 预分配书 id：`create_project` 接受可选 `book_id`，`draft_book_id` 在受理提交里就落库；写入成功后一次收尾写 `book_id` + `status='imported'` + `import.finished_at`。验证：崩溃演练（在写 book_id 前后各杀一次）后 sweep 都能凭 `draft_book_id` 清到书。
- [x] 2.3 失败与取消清理：**先**写 `import_failed`（含 draft_book_id、error.{message,kind,retryable}）并提交，**再**软删；软删失败留 `draft_book_id` 给 sweep 重试。取消与异常路径都以 `run_id` 条件写（`WHERE status='importing' AND import.run_id=:token`），rowcount=0 只清理自己的 draft 即退出。验证：三臂单测（写失败／取消竞态／取消后立即重建）——反例序列「取消→立刻重建」不得出现两本书或旧次写终态。
- [x] 2.4 精炼可中断：复用管线 `_Stopper` + `asyncio.wait` 形态包住 `client.chat`，取消即放弃在途调用。验证：桩客户端挂起时点取消，断言 5 秒内收敛、其后无新调用（假 client 计数不增）；`llm.log` 无新 `ai_call`。
- [x] 2.5 执行体生命周期：模块级 `_inflight` 字典持引用 + `add_done_callback` 记日志；主体 `try/except BaseException/finally`，异常路径用独立短事务 + `asyncio.shield` 写终态（桌面壳 3 秒关停会抛 `CancelledError`）。验证：注入 `CancelledError` 后状态不卡 `importing`；逃逸异常有栈日志。
- [x] 2.6 看门狗：精炼阶段上界（默认 180s，`started_at` 起算）→ `import_failed(stalled, retryable)`；视图侧再加一层「超 2 倍上界按可重试呈现」。验证：桩果冻结不回，断言在阈值+容差内收敛。
- [x] 2.7 写入阶段的锁冲突有界重试：仅 `database is locked`/`disk I/O error` 退避重试 3 次，其余直接失败（`storage_busy` 只覆盖请求级，后台没有）。验证：桩 session 抛 `OperationalError` 两次后成功 → 建书成功；一直失败 → `import_failed` 且 error.kind=`storage_busy`。
- [x] 2.8 步骤与秒数：`import.step ∈ {refine, writing, waiting}`、`started_at` 用 `pipeline._now()`（UTC naive）；`attempts[]` append-only 记时间/结果/kind/tokens。验证：单测断言字段与时间口径（`TZ` 双跑）。

## 3. 后端：重启收敛与可观测

- [x] 3.1 `startup_sweep` 增一步：`status='importing'` → `import_failed(interrupted)`，凭 `draft_book_id` 软删并清 `book_id`；残留 draft 的重试清理要幂等。验证：构造残留行跑 sweep；重复跑不报错。
- [x] 3.2 `ai_client` 的 `ai_call` 行带 `task_id`/`run_id`（异步后请求行与 23 秒调用行失去时间对齐，证据链会断）。验证：`llm.log` 出现 `task=… run=…`；按 run_id 能把一次建书的调用串起来。
- [x] 3.3 旧任务兼容：无 `import` 键一律按 `completed`；`completed+book_id` 走 1.3 的存量分支。验证：旧夹具任务详情与受理行为用例。

## 4. 后端：透出与徽标

- [x] 4.1 `service.task_view` 与清单摘要新增 `import`（step/started_at/elapsed/warnings/`error{message,kind,retryable}`/attempts 摘要），不含产物正文与提示词。验证：契约测试断言字段与旧字段不变。
- [x] 4.2 徽标：`importing` 计入活动态心跳（顶栏可见），`import_failed` 计入「已完成未取结果」，`imported` 为已消费；文件夹导出/角色库出口的消费各自判定。验证：badge 计数矩阵用例（四态 × 三出口）。

## 5. 后端：建书提示条的存储与端点

- [x] 5.1 照 `book-prefs` 先例新增专用键：`filesystem/paths.py` 加 `IMPORT_NOTICE_PATH/KEY` 与 `route_relative_path` 分支（**不进 `PATH_TO_KEY`**，防漏进通用 `/settings/{type}` 白名单）。验证：`GET/PUT /settings/{type}` 对 `deconstruct-import-notice` 仍拒绝；专用路由可读写。
- [x] 5.2 新增 `settings/import_notice_router.py`：`GET`（无则空）+ `DELETE`（幂等，键不存在也 200）；建书写入阶段末尾落 `{items, task_id, at}`。验证：契约三臂 + 「建书后读回与 `import.warnings` 同文」。
- [x] 5.3 登记两份副本允许分叉（不同后端、无共同事务），以前者为准可重生成。验证：设计/代码注释留痕。

## 6. 前端：确认四臂与三态详情

- [ ] 6.1 确认建书四臂：202 → 关弹窗 + toast「已开始建书，可以离开」+ 失效详情与清单；200 幂等 → toast「这本书已经建过了」+ 失效（**不跳转**）；4xx（满额/档位/409）→ 弹窗保留 + 错误文案；网络失败 → toast + 弹窗保留。`busy` 只防本次提交。验证：组件用例四臂，断言无 `navigate`。
- [ ] 6.2 `doExit` 里建书分支的 `navigate` 整段删除（跳转改到详情的「打开这本书」）；`lib/deconstructApi.ts` 返回类型改判别联合。验证：`toolsApi.test.ts` 的 `.book_id` 断言改为判别后取法；`tsc --noEmit` 绿。
- [ ] 6.3 详情结构：`showResults = status ∈ RESULT_READY` 共享结果块（含结果目录、预览、证据报告、出口）；三态各自 banner 与主 CTA；`import_failed` 用独立面板读 `import.error`（**不得**复用 `failed|cancelled` 分支，那里会渲染「从断点续拆」→ 409）。验证：组件用例四态 × 结果块可见性；`import_failed` 下不出现「从断点续拆」。
- [ ] 6.4 默认全选 effect（`TaskDetailPage.tsx:187-193`）扩到 `RESULT_READY`。验证：`imported/import_failed` 下「已选 N/N」正确，导出不报「至少勾选 1 份」。
- [ ] 6.5 建书中：步骤文案 + 独立秒数（`import.started_at` + 本地 1s tick，不用按分钟算的 `elapsedLabel`）+「取消建书」（行内两步确认，说明「已精炼的结果不保留」）。取消/重试走本地 `busy` + `toast.error`，**不用 `act()`**（其 `exitErr` 只渲染在弹窗内）。验证：组件用例含取消确认、取消后回到已完成、重试成功后失效并翻态。
- [ ] 6.6 `import_failed` 时结果目录、存本地文件夹、收进角色库仍可用（前端渲染 + 后端 1.1）。验证：组件用例 + 契约用例双层。

## 7. 前端：清单、轮询与失效

- [ ] 7.1 清单 `STATUS_PILL` 扩三态（建书中 accent／已建书 ok／建书失败 err），并加兜底 `?? {label: t.status, cls: "pill"}`。验证：九态文案用例 + 「未知状态不崩」用例（当前 `TaskListPage.tsx:100` 会 TypeError 白屏）。
- [ ] 7.2 抽共享活动态纯函数 `isActiveTask(status)` = `queued|running|importing`，清单 hook 与**详情页内联 `refetchInterval`（`TaskDetailPage.tsx:154-162`）** 都改用它。验证：纯函数全分支单测；组件用例断言 importing 下持续请求、imported 后停表。
- [ ] 7.3 终态一次性失效：hook 内 `useRef<Set<string>>` 记录已见终态，仅在 `importing → imported/import_failed` 翻转时失效一次 `queryKeys.novels` 与该任务详情。**不得**把 `imported` 放进活动态集合（会永久 1.5s 轮询，撞请求预算口径）。验证：单测断言只失效一次；`e2e/shelf-request-budget` 不回归。
- [ ] 7.4 建书失败的环境信号：badge 恢复 + 应用前台时 toast 一次；离开页面则靠徽标/清单。验证：单测断言 toast 只一次。

## 8. 前端：提示条

- [x] 8.1 提示条落点改为 `SettingsView` 页顶（不是 `WorldSettingPanel`：默认面板是题材，世界面板要切页才挂载）。读 5.2 的端点，按 `notice info/warn` 分级，可关闭（DELETE），关闭失败 toast。验证：组件三态（有/无/关闭后）+ 关闭失败臂。

## 9. 契约、兼容与回滚

- [ ] 9.1 回滚预案按真实后果重写：旧版本清单页遇未知状态整页崩（不是回落原文串）。收敛脚本**独立随包交付**（`scripts/`），或在回滚步骤里给手工 SQL（`importing → completed` + 软删 `draft_book_id`）。验证：按预案在测试库演练一次，结果附 PR。
- [ ] 9.2 PR 切分：第一刀＝2.1+2.2（重排 apply + 幂等键后移，保持同步接口不变，可独立发布并消掉半本书病根）；状态机 + 执行体 + 前端三态必须同一个 PR。**不得**「后端先合」。验证：PR 描述写明切分与依赖。
- [ ] 9.3 状态映射自查清单（20+ 分支点）：后端 `router.py` 五处门 + badge + delete + sweep；前端 status 联合类型、详情分支与内联轮询、清单 pill/摘要、hook 活动态。验证：`rg "completed" client/backend/deconstruct client/frontend/src/components/tools client/frontend/src/hooks` 逐条勾。

## 10. 回归

- [ ] 10.1 后端全量：`cd client/backend && uv run pytest -q`（含新增矩阵用例）。验证：输出结论附 PR。
- [ ] 10.2 前端单测＋覆盖率：`cd client/frontend && npm run coverage`。验证：新增分支矩阵全覆盖（step 三值、error 空兜底、book_id 空、取消/重试 busy、结果块四态、确认四臂、未知状态兜底）；明确**不得**把新增可达 UI 扩进 `TaskDetailPage.tsx:837-1195` 的 `v8 ignore` 区。
- [ ] 10.3 类型与设计门禁：`cd client/frontend && npx tsc --noEmit && npm run design:lint`；`npm run design:check`（像素差 <0.2%）。验证：命令实际输出结论。
- [x] 10.4 前端整链 e2e：仿 `e2e/character-library.spec.ts:67-92` 的 route-mock，新增 `e2e/deconstruct-import-async.spec.ts` 覆盖「确认 → 202 → 弹窗关 → toast → 建书中 → 已建书 → 书架出现 → 打开这本书」，以及失败→重试、取消两臂。验证：用例通过输出附 PR（后端链仍由 10.1 的契约测试 + 10.5 真机兜底）。
- [ ] 10.5 真机验收：真实任务（世界设定超契约）走建书——记录 `POST import-book` 返回耗时（应 <300ms）、转建书中、书出现时间、完成态；再测三段：精炼中取消（确认无新 `ai_call`）、建书中杀应用（重启后为建书失败、无半本书、重试成功）、建书中删除任务（409）。验证：`api.request` / `ai_call` 日志行 + 截图附 change。

## 11. 归档准备（随实现 PR）

- [ ] 11.1 先归档本 change（delta 逐字对齐当前主 spec），再让 `c-deconstruct-resilience` rebase 到归档后的文本——MODIFIED 是整条替换，顺序排错会互删场景。验证：`openspec validate --strict` 全绿；archive 后主 spec 与 delta 一致；PR 写明顺序。
- [ ] 11.2 三态语义在 `docs/ux/design-language.html` §5 状态语言总表登记归口（不新增档位；任务清单「进行中」用 accent 属既有偏差，登记不改）。验证：§5 与实现口径对照记录。
