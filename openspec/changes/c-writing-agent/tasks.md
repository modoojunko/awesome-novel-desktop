# c-writing-agent 实施任务

> 依赖顺序：批A（后端地基）→批B（工具与授权）可与批E（前端壳）并行；批C/批D 随批A/B 插入；批F 依赖批E 壳与批B 契约；批G 收口。事件契约在批A 完成即冻结，前端批E 按契约开发。

## 1. 批A · 后端地基（≈6 人日）

- [x] 1.1 移植 openwriter 会话层：conversations.py 改造（＋novel_id/card 消息/自愈/原子重写/id 白名单）为 assistant/session_store.py；登记 MIT 版权注记
- [x] 1.2 models/assistant.py 四张表（assistant_sessions/assistant_messages/writer_profile/writer_profile_events）＋create_all 验证（新库首启自动建表）
- [x] 1.3 assistant/router.py：POST /chat（SSE）、GET /session、POST /session/reset、POST /approve；事件契约按 design（run_start/step_start/step_end/thinking/narration/artifact/permission_required/gate/run_end/error）；同会话并发 409
- [x] 1.4 assistant/actions.py：动作协议解析三级兜底（严格 json→修复→重试→降级 chat 记 degraded）＋openwriter 抢救函数移植（文本形态 tool call 抢救三件套）
- [x] 1.5 assistant/loop.py：AgentLoop（MAX_STEPS=8/MAX_TOOL_CALLS=10/墙钟 600s/单步 90s first_content_timeout，env fail-soft）＋narration 透传＋逐步落盘 assistant_messages
- [x] 1.6 assistant/context.py：L1 书级冻结前缀（≤300 字 brief＋纪律围栏声明）＋L2 末条 user 消息注入＋L3 滑窗；工具结果裁剪（句边界函数复用）
- [x] 1.7 compact 一期实现：移植 compaction.py 纯函数＋按模型窗口阈值触发＋失败降级裁最旧；单测覆盖触发/降级两路
- [x] 1.8 record_usage 逐步落账（operation=assistant_step）＋done 汇总

## 2. 批B · 工具注册表与授权梯度（≈8 人日）

- [x] 2.1 assistant/tools.py：Tool 结构（name/kind/discipline/feature_key/args_hint/fn）＋TOOL_REGISTRY 封闭清单；未知能力 id fail-loud 校验
- [x] 2.2 读类工具 7 个：read_chapter/read_outline/read_settings/read_story_state/read_progress/kb_read/kb_search（薄包装既有实现，输出按预算裁剪）
- [x] 2.3 产卡工具 8 个：draft_volume_plan/draft_chapter_split/draft_chapter_plot/draft_arc/check_consistency/draft_names(新)/diverge_character_group(新)/diverge_plot_branches(新)；发散打 origin:"diverge" 标记（_filter_who 过滤换标注）；发散卡强制体检前置
- [x] 2.4 核验建卡端点重名去重/合并语义（发散撞名册），落「撞名提示选合并或改名」最小方案
- [x] 2.5 assistant/write_gate.py：硬地板清单→档位→实体域检查→兜底弹卡；三档存储（默认/本书授权/全部允许）＋deny 非诊断性语义
- [x] 2.6 停车-恢复：permission_required 事件＋waiter（asyncio.Event）＋POST /approve resolve＋durable pending（重启恢复续跑）
- [x] 2.7 写类工具 write_entity/write_kb_entry：目标预览载荷＋来源标记（call_id/card_id/session_id/discipline）＋撤销端点（按版本历史回滚）＋审计 stage=adopted/auto_allowed/denied
- [x] 2.8 门控接线：ai_access_granted＋包在位校验（缺包→gate 事件）；no_key→gate{reason:"no_key"} 引导事件；发散 key `assistant-diverge` 后端登记（MAX）

## 3. 批C · 身份/画像/总结（≈4 人日）

- [x] 3.1 assistant/identity.py：身份定义加载＋必需字段校验（fail-loud）＋围栏声明注入 L1
- [x] 3.2 assistant/profile.py：writer_profile 读写＋四式存取（agent 私有 remember/read/update/forget 语义）＋透明告知事件＋敏感类目先问＋暂停学习开关（即时生效）
- [x] 3.3 画像注入：L2 装配吃画像相关项（起草/发散工具提示词注入口味/雷点）
- [x] 3.4 定期总结后台任务：会话收尾/每 N 回合触发（非阻塞/防重入/失败静默）；数据源＝画像事件＋审计；总结写入走透明告知
- [x] 3.5 前端画像页入口：查看/编辑/一键清空/暂停开关（设置域新面板，文案过人话红线）

## 4. 批D · 提示词包（≈2.5 人日，跨仓 awesome-novel-prompts）

- [x] 4.1 assistant_identity/assistant_system/assistant_act 三个基础模板（人设＋围栏纪律＋注入防御＋narration 引导＋动作协议契约）
- [x] 4.2 assistant_diverge_cast/assistant_diverge_volume/assistant_names/assistant_profile_summary 模板（发散不含「不凭空添人添事」句、继承【新拟称呼禁令】）
- [x] 4.3 sync.py CURATED 登记＋lint/render 过占位符对拍；publish.py tier 清单（基础组 TIER_FREE；diverge 进 max）；版本发布＋冒烟
- [x] 4.4 后端 assistant 模板加载接线（PROMPT_PACK_DEV_DIR 联调路径验证；缺包→gate 事件口径）

## 5. 批E · 前端壳与 agent 流（≈14 人日）

- [x] 5.1 布局改造步①：.wb-body/.wb-main 包裹＋aside.col-ai 提壳层（暂挂 Rail）；.three-col 改两列；现有测试全绿
- [x] 5.2 布局改造步②：三视图 CSS 适配（workbench→settings→preview 顺序）；design-parity/large-screen/paper-fill e2e 逐个过
- [x] 5.3 lib/chatApi.ts：SSE 客户端（AgentEvent 契约＋sawTerminal 判死＋401 处理；mock ReadableStream 单测六路）
- [x] 5.4 hooks/useChatSession.ts：run 模型 reducer（幂等 upsert/RUN_ABORT/多卡/采纳锁定 status 生命周期）；reducer 直测
- [x] 5.5 chat/ 八组件：ChatDock/ChatStream/ChatMessage/ChatComposer/CapabilityChips/AssistantFab/ChatGenerating/TraceFolded（tokens 全取 base.css 真值）
- [x] 5.6 布局改造步③：Rail→ChatDock 替换（注册表先接 volume/idle 两页；未覆盖分支 Rail 兜底）
- [x] 5.7 布局改造步④：守卫统一（chatStreaming 并入 goTab 确认与树锁定 onClickCapture）；e2e 流中切页签拦截
- [ ] 5.8 布局改造步⑤：窄屏 AssistantFab＋抽屉（原型交互移植）；e2e 窄屏场景
- [x] 5.9 cards/ 六卡组件（struct/text/report/pick/gate/回执撤销）＋ChatArtifactCard 分发＋查看提示词（prompt-panel 档位规则）
- [x] 5.10 lib/chatRegistry.tsx：页面注册制接口＋volume/idle 注册落地（开场白/chips/context/actions 映射既有写回链）

## 6. 批F · 全页面注册与旧行收编（≈12 人日）

- [x] 6.1 设定域 7 面板注册（chars 最重：CharsAiRail 三行收编＋「从简介立主角」＋footNote 免费声明并入 GateCard）
- [ ] 6.2 工作台章级 6 页签注册（og 五能力＋正文生成＋朱雀 chips；状态遥测迁 ChatDock 头部状态槽＋useRailStats）
- [ ] 6.3 知识库/预览页注册（预览最低配置＝问答＋读工具）
- [x] 6.4 旧 AI 行退役：Rail/AiAssistPanel/VolumeAssistPanel/AiWriterAssistant 调用点按页收编移除；PromptPackCard 随迁 ChatDock 壳内
- [x] 6.5 写回信号链逐注册点核验（refresh/refetchTree/goOutlineSeq/pacingRefreshSeq/setRailData）＋actions 单测钉每条信号
- [x] 6.6 e2e/ai-assist.spec.ts 改写为 ChatDock 锚点版；coverage-contract.ts 登记全部新文件

## 7. 批G · 测试收口与验收（≈8 人日）

- [x] 7.1 e2e 十四场景落齐（原七＋工具轨迹/多卡并出/中断恢复/采纳与 run 并发/发散过目/长会话冒烟/窄屏 FAB）
- [x] 7.2 黄金指令集 v0（14 条起步；tests/test_assistant_golden.py 13/13 绿——工具路由/越界拒答/注入不执行/闲聊收口）
- [x] 7.3 注入回归（书内文本嵌指令不执行）＋越界拒答用例＋硬地板全档位用例
- [x] 7.4 全量 npm run test（后端 pytest＋前端 vitest --coverage）＋design:lint＋parity 过
- [x] 7.5 真机走查清单落盘（docs/design-c/drafts/…真机走查清单.md）——真机执行待 boss 上手（A–D 四段矩阵）
- [ ] 7.6 openspec sync＋归档随实现 PR（openspec-archive-in-implementation-pr 惯例）

## 里程碑口径

- **M1（批A+B 完成）**：agent 循环端到端跑通（curl 级 demo：一句指令→读→产卡→授权→写回→撤销），事件契约冻结。
- **M2（批E 完成）**：写作视图 ChatDock 全量可用（两页注册＋六卡＋门控）。
- **M3＝一期完成线**：「一句自然语言→agent 多步执行→一次可撤销的写回」全链路＋发散旗舰链路 demo（主线→派生反派→体检→采纳→撤销）＋护栏/档位闸/围栏全绿＋黄金指令集 v0 达标＋全页面收编。
