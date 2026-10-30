## Why

拆书完成后的「建书」是一个同步长请求，而且慢的部分只有一次 AI 调用：真机日志
（`logs/app.log` 2026-10-30 10:07:20，任务 `91a13fd5…`）

```
POST /api/deconstruct/tasks/.../import-book  200  23263ms
└─ ai_client op=deconstruct_condense  duration_ms=23128   ← 99.4%
```

23.263 秒里 23.128 秒是「世界设定 AI 精炼」（产物超字段契约时触发，整本拆书基本都会超），
其余全部写入（建项目/题材/角色/卷/伏笔/关系/技法）合计不到 0.2 秒。

这段等待在界面上只有一个置灰不变文案的确认按钮，✕／点击遮罩／「稍后再说」三条关闭路径
全部畅通，且没有任何在进行中的文案——用户很容易把它当卡死点掉，然后：

1. 请求没有被取消，成功时用户可能已在别的页面，却被强行跳进新书；
2. 失败信息写进已关闭的弹窗（`exitErr`），用户看到的是「点了没反应」；
3. `book_id` 在重活开始前就已落库，重试走幂等早退，用户拿回一本静默缺维度的书。

同时，`import-book` 返回的 `warnings`（世界条目截断、主角降级、关系按角色对合并、题材字段
推断、幂等提示）前端一条都不展示，与主 spec「超出部分截断并汇总为提示展示给用户」
（`openspec/specs/deconstruct-book/spec.md:273`）不一致——书缺内容时用户无从得知。

## What Changes

- **建书成为该任务的下一个阶段，整段在后台执行**：任务状态新增
  `importing`（建书中）/ `imported`（已建书）/ `import_failed`（建书失败），与拆书共用
  一条任务；`POST import-book` 立即返回（弹窗关闭、提示「已开始建书，可以离开」），
  整段建书（含 AI 精炼与全部写入）在后台跑完。
- **慢调用前置，半本书不再可能**：AI 精炼在任何书内写入之前完成，写入窗口 ≤2 秒；
  写入失败或中断即软删半成品并清掉建书幂等键，启动 sweep 兜底——**不留可见的半本书**，
  重试完整重跑。（不引入「导入中不可见」的隐藏状态：那要动十几处 `!= deleted` 读路径，
  漏一处就是书看不见或配额算错，风险高于这 0.2 秒窗口。）
- **一次建书一个身份**：受理时生成 `run_id` 与预分配的书 id 并随勾选一起持久化；取消后
  立刻重建视为新一次，旧的在途执行不得写终态、不得删新书。
- **勾选随受理持久化**：后台执行与重试读同一份勾选，不再回落到 7 个设定项的旧口径
  （现状回落会静默丢掉章卷结构/人物关系/写作技法）。
- **存量任务兼容**：本次变更前已建过书的任务（已完成且带 book_id）一律视为「已建书」，
  重复确认返回同一本书；否则升级后老任务会被重建成第二本同名书。
- **建书不再抢拆书队列**：建书不进入拆书 FIFO，开始即执行（不受运行中的拆书阻塞），
  同一时刻至多一个建书在跑。
- **进度与结果在任务管理里可见**：详情显示建书步骤（精炼世界设定／写入设定）与已运行
  秒数；完成后显示「已建书 · 打开这本书」；失败按可重试性给「重试建书」或其它可执行出口；
  建书中可取消（二次确认后回到已完成、清理半成品）、**取消会真中断在途模型调用**；
  建书中禁止删除任务（提示先取消）。
- **结果与既有出口不因建书而丢失**：结果目录、只读预览、存本地文件夹、收进角色库在
  已建书与建书失败两态必须照常可用（现状三处后端守卫与详情块都只认 `completed`，
  不改就是建完书反而没法导出/收录）。
- **不再自动跳转**：用户可能已经离开，建书完成改为详情入口 + 书架自动出现新书。
- **建书 warnings 汇总呈现**：新书设定页顶部可关闭提示条 + 任务详情同源可见。
- **重启收敛**：应用退出导致的「建书中」在下次启动时收敛为「建书失败（可重试）」并
  清理半成品。
- 不改拆书管线、不改建书逐字段回填语义、不改提示词模板（仍是同一次
  `deconstruct_condense`）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `deconstruct-book`：四条既有 Requirement 的行为变化——
  - 「建书出口」：确认后立即返回、整段后台执行；成功判定改为「新书出现在书架」；
    不再自动跳转；失败按可重试性分诊且不产生半本书；书架满额在受理时即拦。
  - 「任务清单与详情」：状态表由六类扩展为九类（+建书中/已建书/建书失败），详情新增
    建书进度、取消、重试与「打开这本书」；轮询只在建书中计入活动态；未知状态回落不崩。
  - 「任务队列与串行调度」：建书不进拆书 FIFO、开始即执行；重启对建书阶段的收敛规则。
  - 「结果目录与出口勾选」：结果目录与三个出口在已建书/建书失败两态保持可用；确认建书
    即关闭弹窗并禁用重复提交；徽标口径按出口分别判定。
  - 新增一条 Requirement「建书任务（后台整体执行）」：整段后台执行、勾选随受理持久化、
    一次建书一个身份、慢调用前置与可验收的可见性、取消真中断、失败分诊、收敛语义。

不改 `design-system`：复用既有 `notice`（info/warn）与 `pill`（accent/ok/err）语气，
不新增令牌、类名或胶囊形态，不触碰两端共享段。

## Design Impact

- **受影响端**：仅 C端（S端控制台无拆书链路）。
- **受影响屏/弹层**：
  - 任务详情：建书中（步骤＋已运行秒数＋取消）、已建书（打开这本书）、建书失败（原因＋按可重试性给出口）；结果目录与三出口在三态共用
  - 任务清单行：三类新状态的徽标与摘要文案；未知状态回落默认徽标
  - 拆书出口弹窗：确认后立即关闭＋「已开始建书」提示（不再等结果）；文案去掉「直接进新书设定页」
  - 新书设定页：顶部建书提示条（可关闭，落点不依赖设定分页）
- **对象状态**（对照状态语言总表）：进行中＝`pill-accent`、完成＝`pill-ok`、失败＝
  `pill-err`；提示条走 `notice info/warn`。不新增第四种胶囊；新增三态需在 §5 状态语言
  总表核对归口（任务清单「进行中」沿用 accent 属既有偏差，登记不改）。
- **共享段**：零改动（不碰 `base.css` 令牌与 `pill/notice/sk/panel/f-err` 家族），
  无需双端同改。
- **原型先行**：需要——`docs/design-c/drafts/ai-novel-c端-拆书.html`（任务详情建书三态、
  清单行文案、出口弹窗确认后关闭）；新书设定页提示条无 parity 基线，drafts 补画；在
  `docs/design-c/prototypes/ADJUSTMENTS.md` 登记。
- **设计工件产出**：实现侧自查（全部为既有形态的复用与文案，无新视觉语言）。

## Impact

- **后端**：`deconstruct/router.py`（import-book 受理式 202 + 幂等/进行中/满额四臂；取消端点；
  `export`/`library-candidates`/`to-library` 的状态门从 `== completed` 改为 `RESULT_READY`
  集合；`delete_task` 增 `importing → 409`）、`deconstruct/apply.py`（拆「先精炼后写入」、
  勾选持久化、预分配书 id、幂等键后移与存量兼容）、`deconstruct/pipeline.py`
  （`startup_sweep` 收敛 `importing` + 有界锁重试 + 取消用既有 `_Stopper` 竞速）、
  `deconstruct/service.py`（状态/步骤/warnings/error.kind 透出、徽标口径）、
  `novels/service.py`（`create_project` 接受预分配 id）、`filesystem/paths.py` +
  新增 `settings/import_notice_router.py`（提示条专用 KV 键与 GET/DELETE）、
  `ai_client`（`ai_call` 行带 task_id/run_id，保住证据链）。
- **前端**：`components/tools/TaskDetailPage.tsx`（确认四臂、三态详情、结果块共用、
  详情内联轮询）、`components/tools/TaskListPage.tsx`（三态徽标 + 未知状态兜底）、
  `hooks/useDeconstructTasks.ts`（活动态与翻转触发的一次性失效）、`lib/deconstructApi.ts`
  （返回类型改判别联合）、`components/novel/workbench/SettingsView.tsx`（提示条落点）。
- **契约**：`POST import-book` 由「同步建完返回 book_id」变为「202 受理，返回任务当前
  状态」；新增 cancel 端点；任务详情/清单新增 `import`（run 步进、时间、warnings、
  `error{message,kind,retryable}`）。
- **AI 依赖**：仍是同一次 `deconstruct_condense`（同 op 名与模板），无需重发提示词包；
  新增的是调用时机（前置）与记账（`import.attempts`）。
- **数据**：零 schema 变更（状态用既有 `status` 字符串；建书载荷进 `dims_json` 顶层
  `import` 键，管线已明确保留未知顶键），不触发 db-per-version 迁移。新书复用既有
  `Novel.status` 值与软删口径；已知债：软删不清理子表与盘目录，重试会累积不可见垃圾行。
- **并行变更**：`c-deconstruct-resilience` 仍开放且同样 MODIFY「任务队列与串行调度」
  「任务清单与详情」；MODIFIED 是整条替换，只排顺序会让后归档方删掉对方新增的场景。
  本 change 的 delta 逐字对齐当前主 spec，**应先归档本 change**，再让 resilience 的
  delta rebase 到归档后的文本。

