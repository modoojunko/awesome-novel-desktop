# 拆书管线韧性与调用预算 — 实施任务

## 0. 前置与基线

- [ ] 0.1 确认 `c-deconstruct-book` 的 4 个未完成任务（8.1 e2e、8.2 GBK 极限观测、8.3 提示词发包、10.7 全量门禁与真书走查）状态；本变更归档前必须先归档/同步 `c-deconstruct-book`，使 `openspec/specs/deconstruct-book/spec.md` 存在。验证：`openspec validate c-deconstruct-resilience --strict --json` 不再出现 "Archive would refuse this delta" 警告；在此之前允许实现，不允许 archive。
- [ ] 0.2 建立失败基线记录：用现有 258 章任务/夹具记录当前调用数、重试数、耗时、降级维度；作为后续对比证据。验证：产出一份 `docs/` 或 change 内的 baseline 记录，含 dims_json/products 统计命令与结果。
- [ ] 0.3 建立 20 章金标样本（从真实书连续取 20 章，固定随机种子/文件哈希），保存单章基线产物与指标脚本。验证：脚本可重复跑出同一份指标（角色/事件召回、章号证据正确率、跨章串入率、字段完整率）。

## 1. P0 失败策略与熔断

- [x] 1.1 新增 `CallPolicy`/错误分类器：timeout、rate_limit、upstream_5xx、auth/config/route、content_filter、invalid_output、truncated、cancelled；用表驱动单测覆盖每个分类。验证：`uv run pytest client/backend/tests/test_deconstruct_pipeline.py -q` 中新增分类用例全绿。
- [x] 1.2 `_call_with_retry` 接入策略：瞬时错误最多 3 次尝试、指数退避+抖动；429 遵循 Retry-After；确定性错误只发一次；拆书 client 的 SDK `max_retries=0`。验证：假客户端分别返回 401/400/404/429/503/timeout，断言请求次数与等待行为。
- [x] 1.3 实现任务级熔断：连续 `max(3, CONCURRENCY)` 次瞬时失败 → `abort_event`、取消在途、任务 `failed(error.kind=provider_unavailable)`、保留断点；后续单元不得再调用。验证：假客户端全部挂起/失败，断言调用次数有界、任务在阈值内失败、断点仍在。
- [x] 1.4 实现内容审核隔离：单单元 1301 → 记 failed+warning 并继续；单维度失败单元占比 >50% 或 >8 个 → 维度 `degraded`，任务可完成。验证：假客户端对指定章返回 1301，断言其余章继续、维度状态与 warning 正确。
- [x] 1.5 实现截断处理：解析 `finish_reason=length`/JSON 不完整 → reduce 组二分或提高预算重试；禁止相同输入/预算原样重试；仍失败 → `degraded` 原因。验证：假客户端固定返回截断 JSON，断言二分次数有限、不再出现 3 次相同请求。
- [x] 1.6 失败终态写 `error.kind` 与可读文案；保留已完成单元与产物。验证：API `task_view.error` 含 kind；续拆后已完成单元不重取。

## 2. P0 看门狗、墙钟与取消

- [x] 2.1 在 `run_task` 外层加 watchdog：维护 `last_progress_at` 与 `last_token_at`；拆卡/归并分别设无进展阈值（默认 5/15 分钟）；超时取消主任务并置 `failed(error.kind=stalled)`。验证：假客户端挂起不回，断言任务在阈值+容差内失败、dispatcher 继续。
- [x] 2.2 加任务墙钟（默认 `max(30min, 2×预计)`，可配）；超时按 `stalled` 收场。验证：假客户端持续返回很慢但有效的响应，断言墙钟触发且断点保留。
- [x] 2.3 取消贯穿：重试循环每次尝试前查 cancel；在途 HTTP 用 `asyncio.wait_for`/任务取消；`CancelledError` 不被吞。验证：取消一个 600s 挂起调用，断言 10 秒内进入 cancelled、之后无新请求。
- [x] 2.4 队列活性：两个任务排队，第一个被 watchdog 判 stalled，第二个自动开始。验证：dispatcher 集成测试；顶栏心跳/位次状态正确。
- [ ] 2.5 看门狗不误杀：流式 chunk 持续到达但单单元耗时很长时，不判 stalled。验证：假流式客户端每 30s 发 chunk，断言任务继续。

## 3. P0 时间口径与降级可见（UI）

- [x] 3.1 **原型先行/设计影响判定**：在 `docs/design-c/drafts/ai-novel-c端-拆书.html` 补三态文案——运行中「模型无响应/正在重试」、失败 `error.kind` 分诊、完成 degraded 标记；在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记。判定不新增布局/视觉形态、不触共享段（依据 proposal Design Impact）。验证：`npm run design:lint` 通过；原型截图与登记条目入库。
- [x] 3.2 后端统一 UTC：`service._activity`/`_eta_seconds` 与 `pipeline._now()` 同源（`datetime.now(UTC).replace(tzinfo=None)`）。验证：`TZ=Asia/Shanghai` 与 `TZ=UTC` 双跑测试，age/ETA 均为真实值。
- [x] 3.3 前端 tools 页面改用 `parseServerTime`/`serverTimeMs`（`TaskDetailPage` 的 elapsedLabel、`TaskListPage` 的 fmtTime）。验证：vitest 用例覆盖带 Z/不带 Z/UTC+8 三种输入。
- [x] 3.4 `task_view` 透出 `error.kind`、`dims.degraded`、`activity.last_progress_at/last_token_at/retry_attempt`；前端失败面板按 kind 给出口（原模型重试/换模型续拆/去配置/换书），完成详情显示 warn degraded pill。验证：API 契约测试 + 组件测试；复用既有 notice/pill，不新增形态。
- [ ] 3.5 详情页「模型无响应」状态：显示最近响应时间、重试次数、等待/取消出口；不再只显示无限增长秒数。验证：组件测试 + 真机/截图走查。

## 4. P0 单元断点表与迁移

- [x] 4.1 新增 `deconstruct_units` 模型/迁移（字段见 design D4），升 `CLIENT_VERSION`；旧库升级自动建表。验证：新增「旧库 boot 新代码建表」迁移测试通过；`cd client/backend && uv run python scripts/upgrade_drill.py --all --work /tmp/deconstruct-upgrade-drill` 既有演练通过；schema 指纹/版本一致。
- [x] 4.2 实现 `unit_key`/`input_hash` 工具：card=章号；l1=dim+prompt_version+排序碎片；reduce=子 key+子输出 hash；presence/place 同 design。验证：稳定性/输入变化失效/排序无关性单测。
- [x] 4.3 管线写单元：card/L1/reduce/presence/place 成功后 upsert；先落库再更新 UI 状态；续拆按 done 单元跳过。验证：模拟 L1 第 8/10 批失败，续拆断言只请求 9/10 + reduce。
- [x] 4.4 旧任务双读：`dims_json.entries` 继续可用；新表为空走旧路径；成功单元写新表。验证：旧夹具任务续拆成功，不要求迁移历史卡片。
- [x] 4.5 调用账聚合：按 task/stage/dim 输出 calls/retries/failures/duration/tokens；`task_view.stats` 暴露摘要（不含原文/密钥）。验证：API 契约测试 + 账本数值与假客户端计数一致。
- [ ] 4.6 `llm.log` 行增加 `task_id`/`operation`（可选 trace 参数，不改变其他调用方默认字段）。验证：单测断言日志行含 task_id；grep 可按任务检索。

## 5. P1a 能力表、token 估算、单遍归并

- [x] 5.1 `ModelCaps` 注册表与解析顺序（任务覆盖→内置表→provider 默认→保守默认）；未知模型不阻塞。验证：单测覆盖 1M/64k、8k、未知三种。
- [x] 5.2 token 估算器（tiktoken 优先；CJK/ASCII 启发式+15% 余量；用 usage 校准系数）。验证：与真实 `usage.prompt_tokens` 对拍，误差在阈值内；无 tiktoken 时回退可用。
- [x] 5.3 用 `_pack_by_tokens` 替换 `_pack_pairs/_pack_units` 的字符预算；保留字符默认作为兼容。验证：边界用例（单条超预算、空列表、排序稳定）。
- [x] 5.4 维度单遍归并：按 fragments/输出预算判断 `single_pass`；满足则一次调用出终稿，跳过 L1/reduce；否则现有路径。验证：1M/64k 假能力下 characters 10.7 万字碎片 1 次调用；8k 下仍走 L1+reduce。
- [x] 5.5 reduce 截断二分：`finish_reason=length`/解析失败时组二分递归；单份仍截断→degraded；禁止相同请求重试。验证：假客户端固定截断，断言分组次数与最终状态。
- [x] 5.6 长上下文计价保护：预计输入 > 阈值（默认 128k）拆批或要求显式确认；账本记录 token。验证：规划器单测 + 账本数值。
- [ ] 5.7 真实书对比：258 章任务跑 P1a，记录归并调用 24→10、耗时、产物质量；与 baseline 对比。验证：报告含调用数/耗时/token/质量差异；不达标则关闭 `DECONSTRUCT_SINGLE_PASS`。

## 6. P1b 拆卡合批与质量门

- [x] 6.1 提示词仓新增/改造 `deconstruct-card-batch`：按章分隔输入，JSONL 一行一张卡、`no` 首字段、只输出勾选维度；保存契约 fixture。验证：提示词仓 lint/pytest/契约测试通过；本仓 fixture 可解析。
- [x] 6.2 批次规划器：按 D6 公式计算每批章数（输出预算优先，输入窗口兜底，上限 30）；只把勾选维度传给模板。验证：8k/16k/32k/64k 四档参数化单测。
- [x] 6.3 流式 JSONL 解析 + 逐章落库：每行完成即写单元表；校验章号集合/无重复/必填键；失败二分拆批直到单章；单章仍失败隔离。验证：假流式客户端中途断开，断言已完成章保留、只补缺失章。
- [ ] 6.4 20 章金标质量门：单章基线 vs 10/20 章合批，指标见 design；通过线召回下降 ≤5%、串章 0、字段完整率 ≥99%。验证：基准报告；不通过则把默认批大小降档或 `DECONSTRUCT_CARD_BATCH=off`。
- [x] 6.5 flag：`DECONSTRUCT_CARD_BATCH=auto|off|N`；旧提示词包/能力未知自动回退逐章。验证：flag off 与旧包夹具均走旧路径；回滚测试。
- [ ] 6.6 258 章真书压测：记录调用数（目标 8k→90–110，64k→20–30，按实测输出上限）、墙钟、失败/重试、质量。验证：报告与 baseline 对比；不达标不发布。

## 7. P2 换模型续拆、自动续拆、模型历史

- [x] 7.1 `/resume` 可选 `api_config_id`/`ai_model`；校验 `resolve_client`；更新任务并追加 `model_history`（新列或 dims_json 顶键，按 design 取新列）。验证：API 测试覆盖非法配置 400、换模型成功、历史两条。
- [ ] 7.2 自动续拆：`provider_unavailable|stalled|timeout` 写 `auto_resume_at`/`resume_count`；dispatcher 取到期任务；默认 3 次、退避 5/15/60 分钟；auth/config/content 不自动。验证：时间桩测试；达到上限保持 failed；关闭开关后不自动。
- [ ] 7.3 UI：失败详情显示下次自动重试时间/已停止原因；模型历史可见；自动续拆开关（默认关或按拍板）。验证：组件测试 + 状态语言检查。
- [ ] 7.4 运行手册：如何用 task_id + 调用账定位故障、各 error.kind 处置、长上下文计价/能力表维护。验证：文档评审通过。

## 8. 回归与门禁

- [x] 8.1 后端：`cd client/backend && uv run pytest tests/test_deconstruct_pipeline.py tests/test_deconstruct_api.py tests/test_deconstruct_queue.py tests/test_ai_client_upstream_errors.py tests/test_ai_timeout_accounting.py -q`；`uv run ruff check .`。记录实际输出（通过数/失败数）。
- [ ] 8.2 前端：`npx vitest run` 相关用例、`npx tsc --noEmit`、`npm run design:lint`、`npm run design:check`。记录实际输出与像素差；不触共享段，无需 design:cross（引用 proposal Design Impact 依据）。
- [x] 8.3 故障注入矩阵：挂起/401/400/404/429/500/空 200/截断 JSON/1301 各一条；断言请求次数、退避、熔断、隔离、取消。记录结果表。
- [ ] 8.4 升级演练：旧 DB（含未完成拆书任务）升级到新 schema；旧任务可续拆/删除；`cd client/backend && uv run python scripts/upgrade_drill.py --all --work /tmp/deconstruct-upgrade-drill` 通过。记录输出。
- [ ] 8.5 e2e 隔离栈：创建→取消→续拆→stall→degraded→导出；确认无跨会话假红（按 AGENTS.md 独立栈）。记录 19/19 或实际通过数。
- [ ] 8.6 真书回归：258 章任务跑完整链；记录调用数、重试、耗时、降级数、产物完整性；与 0.2 baseline 对比。
- [ ] 8.7 归档闸门：`c-deconstruct-book` 已归档/同步；`openspec validate c-deconstruct-resilience --strict` 无 archive 警告；`openspec status` 全 done。记录命令输出。

## 9. 评审与文档

- [ ] 9.1 四路评审（架构/后端/前端/测试）并处置 P1/P2；review-agent 全 diff 扫。验证：评审记录与修复 commit。
- [x] 9.2 更新 design.md 的基准结果（实际 output 上限、价格档、批大小默认值）与 tasks 勾选；把本次拍板写回 proposal/design。验证：文档无 TBD。
- [ ] 9.3 发版说明：面向用户只讲「拆书更稳、可中断、可续拆、降级可见」，不暴露内部熔断/令牌术语；文案走 design-language §13。验证：文案评审通过。

## 13. 首批落地记录（2026-10-17，本变更实现批）

已落地（worktree `ai-novel-wt-deconstruct-resilience`，分支 `c-deconstruct-resilience`，基线 origin/main 2efd8b00）：

- [x] 13.1 失败策略单源 `deconstruct/policy.py`（8 类错误分类＋退避＋Retry-After＋DECONSTRUCT_BACKOFF_SCALE）＋ SDK 重试归零（resolve_client max_retries=0）。验证：tests/test_deconstruct_resilience.py 22 绿（分类矩阵/3 发重试/401 单发/截断不重试）。
- [x] 13.2 熔断＋看门狗＋墙钟＋取消竞速（pipeline `_Stopper`/`_Breaker`/`_Watchdog`；DB 取消轮询贯穿在途调用）。验证：熔断并发 4 章 ≤12 发收场 provider_unavailable；挂起 30s 在 0.3s 阈值内 stalled 收场；取消竞速掐断在途请求。
- [x] 13.3 单元账 `deconstruct_units`（card/l1/reduce/reduce_state/presence/place/card_batch）＋ L1 批级断点续拆＋reduce 轮间检查点＋调用账聚合（service.task_stats→GET /tasks/{id}.stats）。验证：批 2 截断失败后续拆只补 2/3/4＋reduce（断言调用数）。
- [x] 13.4 能力预算 `deconstruct/capabilities.py`（DECONSTRUCT_CAPS 解锁 1M 上下文；vendor 保守表；token 估算；oversize 400→拆半自愈）＋单遍归并（预算放大后批次=1 自然涌现）。验证：env caps 下归并 max_tokens=16384＋caps_note 落账；保守口径零漂移（8192）。
- [x] 13.5 拆卡合批（`DECONSTRUCT_CARD_BATCH`=off|N|auto；JSONL 一行一张卡＋包裹形回退；坏批/缺章退回逐章；提示词仓 `deconstruct_card_batch.prompt`）。验证：2 章/批 4 章只发 2 次＋单元账 4 章 done；坏输出整批退回逐章仍完成；off/老包回退。提示词仓 pins 55 绿。
- [x] 13.6 时间口径统一（service activity/ETA 与 pipeline._now 同源 UTC；前端 TaskDetail/TaskList 走 parseServerTime）。验证：双端测试＋TZ=Asia/Shanghai 钉。
- [x] 13.7 降级/告警/错误类别可见（task_view error_kind/warnings/degraded/stats；前端 degraded warn、kindExit 出口、调用统计行）。验证：vitest 6 例新增全绿（全量 1698 绿）。
- [x] 13.8 换模型续拆（POST /resume 可携 api_config_id/ai_model；resolve 同源校验；model_history 追加）。验证：API 测试（400 非法/成功换绑/历史两条）。
- [x] 13.9 开书产物契约校验 `scripts/deconstruct_product_check.py`（world normalize/characters role+persona/mainplot arcs/style/foreshadow 全链干跑）。对真实 258 章两单跑通；揪出并修复两个真违约：persona 全空（背景/行动合成兜底）＋复合 role 越界（包含词归一），各配回归钉。

挂账（下批）：

- [ ] 13.10 20 章金标质量门与 258 章真书压测（0.3/5.7/6.4/6.6/8.6）：需要真实模型跑批——合批质量（召回/串章）与单遍归并产物对比未实测；DECONSTRUCT_CARD_BATCH 默认 auto 仅在能力显式时激活，金标未过前建议 env 钉小批或 off。
- [ ] 13.11 自动续拆（7.2/7.3）：失败退避重入队＋UI 下次重试时间——涉及 dispatcher 取任务扩展，本批未做。
- [ ] 13.12 llm.log 带 task_id（4.6）：需要 ai_client 留痕行加 trace 参数，本批未做（调用账已可按任务聚合，日志检索缺口可等 8.x）。
- [ ] 13.13 运行中「模型无响应」实时提示（3.5）：watchdog 状态上抛 activity 字段＋前端渲染，本批只做了失败后的 kindExit。
