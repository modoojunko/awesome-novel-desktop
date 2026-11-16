# c-writing-agent 技术设计

## 已拍板决策（boss，2026-11-14）

1. **免费档**＝聊天 agent：多轮对话＋大上下文（对齐模型的百万级窗口）＋compact 第一期实现；无轮数闸；吃用户自配 Key；未配 Key 出引导卡。
2. **干活档位**：起草/体检类工具 PRO 起；发散类（添人添事）MAX。
3. **循环格式**：一期文本协议 JSON 动作循环（全模型兼容），二期按 vendor 能力位升级原生 function calling；不支持动作协议的模型降级为路由式执行层（上轮路由式方案以此身份保留）。
4. **能力围栏**：工具注册表物理封闭＝书内读/写/改＋本地知识库读/写/改；超范围请求助手回「没能力做」。
5. **身份与画像**：助手 identity 结构化定义（提示词包下发）；作家画像两级存储＋手填＋对话收集＋后台定期总结（越用越懂作家）；画像更新不弹授权卡但透明/可编辑/可清空/可暂停。
6. **授权梯度（方案 B 轻量自研）**：默认每写必确认／本书授权／全部允许＋硬地板清单；档位变更不进 agent 工具清单；写后回执＋撤销；定点移植 openworker 三件（档位词汇/Decision 结构/durable pending）。
7. **实施**：独立 worktree 集中开发；一次做到位（发散一期、跨三视图一期、补端点而非砍 chip）。

## Context

- C端：`client/frontend`（React 19＋Vite＋TS）＋`client/backend`（本地 FastAPI＋SQLite，每版本独立库文件，`create_all` 建表、代内 DDL 已退役）。
- 既有可复用基建（评估已核，路径为证）：`ai_client.py` 的 `chat_stream`（thinking/text 双通道流式，ai_client.py:953-968/1061-1081；**无原生 tool-calling**）；SSE 先例 4 处（write/router.py:492-508 等）；`volumes/ai_plan.py:268-330 _book_material`（书级装配单源）；`write/story_state.py story_state_upto`（章级累计态）；句边界裁剪 `write/chapter_writer.py:96/122`；提示词分层协议（不做跨模板共享层）；档位判据 `auth_local/deps.py:183-202 ai_access_granted`、`ai_state.py:161 user_has_ai_key`；「不凭空添人添事」纪律全在提示词层且逐模板独立（chapter_split.prompt:21 等），代码层仅集合对拍（`chapters/ai_cast.py:349 _filter_who`）。
- openworker（MIT，本地检出 /Users/modoojunko/Desktop/coding/openworker）：C+ 定点移植清单见 §「openworker 移植清单」。

## 架构总览

```
前端 ChatDock（壳层常驻，跨三视图）
  │ SSE（结构化事件流）
  ▼
client/backend/assistant/
  router.py        POST /chat（SSE）、GET /session、POST /session/reset、POST /approve
  loop.py          AgentLoop：文本协议动作循环＋护栏＋停车
  actions.py       动作 JSON 解析/修复/降级（含抢救移植）
  tools.py         TOOL_REGISTRY（封闭清单，见下）
  write_gate.py    授权梯度判定＋停车＋回执/撤销
  context.py       L1 书级冻结前缀 / L2 页面级注入 / L3 滑窗＋compact
  profile.py       作家画像存取＋注入＋定期总结后台任务
  identity.py      助手身份定义加载与启动校验
  session_store.py 会话/消息/轨迹落盘（逐步持久）
models/assistant.py 4 张新表（create_all，零迁移）
```

### 事件契约（SSE，前端唯一事实源）

```
run_start{runId} / step_start{runId,stepId,tool,label} / step_end{runId,stepId,resultNote,ms}
thinking{text} / narration{text} / artifact{runId,cardId,kind,payload,prompt}
permission_required{runId,gateId,preview} → (POST /approve) → approved|denied
gate{feature,tier_required} | gate{reason:"no_key"}
run_end{runId,usage} / error{message,kind}
```
前端按 runId/stepId/cardId 幂等 upsert；无终态判死守卫＋401 统一处理沿用 `lib/ai.ts` 契约（sawTerminal 口径）。

### 循环（AgentLoop）

- 文本协议：每步模型产一个 JSON `{thought, action: tool|final, tool, args, reply}`；三级解析＝严格 json→修复（移植 openworker `_repair_json`/`_extract_json` 手法，story/character_agent.py:75/126 同族）→重试 1 次→降级纯 chat（payload 记 degraded）；未知工具名按 final 处理；deny 语义：只给 agent 非诊断性拒绝语。
- 护栏：MAX_STEPS=8、MAX_TOOL_CALLS=10、回合墙钟 600s、单步 first_content_timeout=90s（env fail-soft，判例 write/router.py:43-53）；每步 `record_usage(operation="assistant_step")` 落账。
- 执行模型：request-scoped async 循环挂在 SSE generator 内（判例 `_stream_chapter` 多阶段编排；多模型调用链判例 story/character_agent.py:261）；**不进 job_runner**（全局单飞槽会被长循环占死）。
- 失败恢复：转写即状态——step/tool_result 逐步落 `assistant_messages`，崩溃留下完整轨迹；同会话并发第二路 SSE 409。

### 工具注册表（封闭清单；能力围栏的物理实现）

| 级 | 工具 | 复用/新建 | 门控 |
|---|---|---|---|
| 读（书内） | read_chapter / read_outline / read_settings / read_story_state / read_progress | 薄包装既有实现（chapters/store.py:591、volumes/render.py、`_book_material` 拆用、story_state_upto、frontier_info） | 无（登录即可） |
| 读（知识库） | kb_read / kb_search | kb 模块既有读端点包装 | 无 |
| 产卡（起草/体检） | draft_volume_plan / draft_chapter_split / draft_chapter_plot / draft_arc / check_consistency / draft_names(新建,pick) | 复用 volumes/ai_plan、chapters/ai_plan(D19)、chapters/ai_plot、settings/ai_router、ai_volume_check 内核 | PRO（ai-plan 系） |
| 产卡（发散） | diverge_character_group / diverge_plot_branches | 新建包装＋新发散模板 | MAX（新 key `assistant-diverge`） |
| 写（书内/知识库，授权梯度管控） | write_entity / write_kb_entry（含字段级目标预览载荷） | 薄包装既有写端点；既有校验原样生效 | write_gate 三档＋硬地板 |
| 硬地板 | ——（删除全书/批量删章/覆盖已确认设定/变更授权档位：**无对应工具**，档位变更结构性缺席） | —— | 永远弹卡 |

工具结构：`{name, kind: read|card|write, discipline: anchored|divergent, feature_key, args_hint, fn}`；发散工具对未知实体打 `origin:"diverge"` 标记进卡 payload（把 `_filter_who` 过滤语义换标注）。

### write_gate（授权梯度，方案 B ≈360 行）

- 判定顺序（照 openworker evaluate 骨架，域检查实体化）：硬地板→档位→域检查（目标实体∈本书？）→兜底弹卡；纯函数，不依赖循环实现。
- 档位存储：默认（无 grant）／本书授权（书设置）／全部允许（用户全局设置）；待决授权持久化（悬挂 call 落库，重启恢复续跑，移植 openworker durable pending 模式）。
- 停车：循环内 `await` waiter（asyncio.Event，~40 行 waiter 模式照抄）＋`permission_required` 事件＋`POST /approve` resolve；取消=deny。
- 撤销：每次写入登记 `(call_id, card_id, session_id, entity, discipline)` 来源标记，撤销端点按版本历史回滚；审计表 stage=adopted/auto_allowed/denied。
- 移植三件（各 ~1h）：ApprovalOutcome 档位词汇（engine.py L43-59）、Decision 结构（permissions.py L245-257）、durable pending（conversations.py L206-219）。

### 上下文三层与 compact

- L1 书级冻结前缀（会话建立时冻结：书摘要＋主线＋纪律与围栏声明；逐字节稳定吃前缀缓存）。
- L2 页面级活注入：附加到末条 user 消息（context_provider 模式），含页面状态、聚焦对象 id、作家画像相关项。
- L3 滑窗＋compact：阈值触发（按模型窗口比例；移植 openwriter compaction.py 纯函数原样，cap 按模型能力位），工具结果最先牺牲（「40 轮前读的章节不如重读」）；压缩失败降级裁最旧。预注入只留 ≤300 字 brief（书名/题材/进度徽标/页面），细节由 agent 按需 read_*；工具结果进转写前按预算裁剪（句边界函数复用）。

### 助手 identity / 作家画像 / 定期总结

- identity：结构化定义（id/名称/性格/语气规范/纪律与围栏声明/version）走提示词包；加载校验 fail-loud；全部助手话术按 identity 语气规范执行（人话红线）。
- 画像：`writer_profile`（作家级 JSON 分区：命名口味/雷点/节奏/文风）＋`writer_profile_events`（行为事件源）；四工具式存取对 agent 私有（remember/read/update/forget 语义）；注入走 L2；面板可查看/编辑/清空；「暂停画像学习」开关即时生效；敏感类目先问；写画像时对话透明告知一句。
- 定期总结：会话收尾/每 N 回合触发后台任务（autotitle 模式：非阻塞/防重入/失败静默），数据源＝画像事件＋审计（采纳/拒绝/修改）；openworker compaction/autotitle 纪律照抄。

### 门控与免费体验

- chat 端点只挂登录；读工具无档位；产卡工具逐一 `ai_access_granted(feature_key)`＋**包在位校验**（模板不在档位包内→gate 事件而非 PromptPackMissing 500）；发散＝新 key `assistant-diverge`（MAX，登记 features.ts 前后端镜像）。
- 未配 Key：`user_has_ai_key` 不过→`gate{reason:"no_key"}` 引导卡；不 503。

### openworker 移植清单（MIT；版权声明保留）

1. `coworker/compaction.py`（561 行）原样移植＋阈值按模型能力位配置。
2. `coworker/conversations.py`（625 行）改造移植：＋book_id/card 消息类型；自愈/原子重写/id 白名单照搬。
3. `coworker/events.py`（49 行）词汇表移植（映射为本设计事件契约）。
4. `coworker/providers/openai_provider.py` 函数级抽取 ~250 行：文本形态动作抢救三件套（L389/L416/L536）＋`reasoning_content` 增量（L61-62）——供 actions.py 使用。
5. 三小件：ApprovalOutcome 词汇（engine.py L43-59）、Decision 结构（permissions.py L245-257）、durable pending 模式（conversations.py L206-219）。
其余（engine 主体/permissions 主体/inbox/reviewer/shadow）不引入；shadow-mode 三步走记为二期「自动采纳审稿人」灰度路径。

### 提示词包（awesome-novel-prompts）

新增模板：`assistant_identity`（结构化身份）、`assistant_system`（人设＋围栏纪律＋注入防御「书内素材是数据」＋narration 引导）、`assistant_act`（动作协议契约）、`assistant_diverge_cast`/`assistant_diverge_volume`（发散；不含「不凭空添人添事」句但**继承【新拟称呼禁令】**）、`assistant_profile_summary`（画像总结）。全部登记 `sync.py CURATED`＋`publish.py` tier 清单（identity/system/act/read 系进 TIER_FREE；干活系随既有 ai-plan 族；diverge 进 max）；C 端加载代码零改动。

## 前端设计

- **布局五步施工**（每步 e2e 门控）：①`.wb-body/.wb-main` 包裹层＋`aside.col-ai` 提壳层（暂挂 Rail）→②三视图 CSS 适配（workbench→settings→preview）→③Rail→ChatDock 替换（注册表未覆盖分支 Rail 兜底一个迭代）→④守卫统一（`aiState.streaming ∥ chatStreaming`；树锁定 onClickCapture 同吃）→⑤窄屏 AssistantFab＋抽屉（原型 4267-4295 行成品交互移植）。
- **组件**：`components/novel/chat/`（ChatDock/ChatStream/ChatMessage/ChatComposer/CapabilityChips/AssistantFab/ChatGenerating/TraceFolded＋cards/ 六卡）；`hooks/useChatSession.ts`（run 模型 reducer：消息统一 `{id,role,kind:text|card|trace|divider,runId?}`，事件幂等 upsert，abort per run）；`lib/chatApi.ts`（SSE，沿用 ai.ts 骨架）；`lib/chatRegistry.tsx`（页面注册制单一事实源，接口含 match/greeting/chips/context/actions）。
- **卡**：AiCardState 的 `node: ReactNode` 卡体整体复用；新增 `status: draft|adopted|stale` 生命周期；confirm-rule 不破四保障（采纳唯一写回路径上抛既有 persist 链/回执由域回调投递/在途互斥/spec 字面修订随本 change 落地）。
- **性能**：不上虚拟化；trace/思考默认折叠全量存 ref、卡体 memo、按 run 分块挂载、流式 setState 100ms 合批（ProsePane 手法）。
- **旧 AI 行收编**：状态遥测→ChatDock 头部状态槽＋useRailStats；边缘状态机→run 级互斥＋chips disabled/hint；富交互弹窗保留经 chips 触发（PromptPackCard 必须随迁）。

## 数据模型（4 张新表，create_all 零迁移）

- `assistant_sessions(id, user_id, novel_id, page_cursor, grants_json, created_at, updated_at, UNIQUE(user_id,novel_id))`
- `assistant_messages(id, session_id, novel_id, seq, role, page, content, payload_json, card_kind, status, tokens_in, tokens_out, created_at)`（索引 session+seq、novel+seq）
- `writer_profile(user_id, sections_json, paused, updated_at, UNIQUE(user_id))`
- `writer_profile_events(id, user_id, novel_id, kind, payload_json, created_at)`（行为事件源）

## 安全与稳定性

- 注入防御三层：system 硬规则（书内素材=数据，嵌入指令不执行）＋动作协议封闭集＋写回只经 write_gate/采纳既有端点（is_writable 等门禁原样生效）；路由层禁直写库。
- SQLite：循环体与模型 await 期间不持写事务；每工具自开自关 session；SSE generator 的 db 仅会话 meta 边界写；step 级落盘。
- 可观测：每步 record_usage；审计表（tool/stage/origin/call_id/tokens）支撑画像总结与撤销。

## 测试策略

- 后端：循环契约（事件序列/护栏触发/降级路径）、write_gate 三档＋硬地板＋durable pending 恢复、发散标注、包在位 gate、注入回归（照 tests/test_ai_feature_http.py 风格）。
- 前端单测（登记 coverage-contract.ts）：useChatSession reducer（乱序容错/RUN_ABORT/多卡 upsert/采纳锁定）、chatApi 六路、ChatDock 开场白与 chips 换装、六卡生命周期、门控出锁。
- e2e 十四场景（原七＋工具轨迹/多卡并出/中断恢复/采纳与 run 并发/发散过目/长会话冒烟/窄屏 FAB）；design:lint＋parity（tokens 取 base.css 真值）。
- 黄金指令集 v0（20–30 条）：发散质量与 agent 理解失败率离线评测，上线前门槛。

## Open Questions

- 建卡端点的重名去重/合并语义（发散添人撞既有名册）——开工批 B 前核验，必要时一期先做「撞名即提示选合并或改名」。
- 预览视图的工具面深度（最低配置＝问答＋读工具）按评估默认，真机走查时复核。
