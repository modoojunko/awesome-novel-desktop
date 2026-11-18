# c-agent-chat-memory：对话前端定版（@agentscope-ai/chat 全量）＋助手分层记忆

## Why

一期对话前端是自研 ChatDock：Markdown 渲染、流式拼装、消息状态机全是手搓，逐字流式只覆盖原生 FC 模型（GLM），文本协议模型（deepseek 等）仍是整段到达；助手侧记忆只有「会话（按页签）＋作家画像（按用户）」两层，AI 助手自身对一本书积累的写作规矩与项目决策无处安放——换页签就忘、换会话就丢。

boss 拍板（2026-11-17）：前端组件全面采用 @agentscope-ai/chat（阿里 Spark Chat）定版——「前端组件能全部用阿里的么」「为什么不用呢」；记忆按四层 scope 管理（全局／按用户／按书／按页签），并补齐缺的「按书」两层——AI 自身写作规矩（agent 记忆）与项目决策记录。

## What Changes

### 前端架构定版

- **ChatAnywhere 成唯一 dock**：本分支已实装 Aui2Dock 默认＋`?aui=0` 遗留开关——本 change 收口：移除 `?aui=0` 开关与 ChatDock/AuiDock（assistant-ui spike）退役，`ChatDock.tsx`/`AuiDock.tsx`/`useChatSession` 自研链退役
- **卡面体系迁移**：产物卡/授权卡/轨迹行从文本占位（`● tool ✓`、`[产物卡已生成]`）升级为 ChatAnywhere customCards 真卡面——复用既有 CardBody 卡面组件与授权卡 approve/deny 按钮，视觉走既有 chat.css 语义类
- **逐字流式全模型**：文本协议模型（deepseek 等）补 narration_delta 流式路径——协议 JSON 不裸流（deepseek 裸 JSON 回复教训），用流式解析从协议壳中增量抽取 narration 段交付；原生 FC 模型已有 delta 不动
- **崩溃兜底**：AuiErrorBoundary 常驻（已实装），ChatAnywhere 渲染异常降级为错误提示不白屏
- **授权模式芯片带过**：ChatDock 已有的输入区授权档位芯片（每写必确认／本书内自动放行／全部自动放行三档，boss 11-15 拍板形态）在 ChatAnywhere 输入区重挂——当前档常显＋下拉切换＋即时生效＋对话流回执；硬地板不受档位影响、agent 结构性不能自改档（既有 write_gate 语义零变化）

### 助手分层记忆（四层 scope 定版）

- **四层 scope 规格化**（既有层盘点入 spec，新增层落库）：
  - **全局**（全 C 端共享）：提示词包模板（身份/系统/协议）、工具注册表——发版控制，零改动
  - **按用户**（跨书共享）：作家人格覆盖（assistant_personas）、作家画像（writer_profiles/writer_profile_events）、知识库（kb_entries）——已有，零改动
  - **按书**（跨页签共享）：书内数据（设定/章纲/正文，工具实时查）、书级偏好（已有）——已有；**新增两层**：
    - **书级 agent 记忆**（book_agent_memory）：AI 助手自身对这本书积累的写作规矩与特化知识（如「本书避免血腥」「第一人称」「结尾留钩子」）——等价 agent.md 按书一份
    - **书级项目决策**（book_decisions）：协作中定下的方向性结论（否了什么方向/定了什么调子），按时间留痕
  - **按页签**（线程隔离）：会话消息（assistant_messages）、压缩摘要（compaction_json）、工具步轨迹——已有，零改动
- **记忆注入链**：book_agent_memory＋book_decisions 拼进 L1 系统提示词（prompts.py 既有拼装点，身份段之后、域纪律段之前），按书装载——切书即换、删书即删
- **记忆自维护工具**：助手获 recall_book_memory（查）＋remember_book_memory / remember_decision（写）三个封闭工具，agent 自主维护；写类受授权梯度管控（记忆写入默认免授权——只影响后续提示词，不碰书稿）
- **删除联动**：删书时 book_agent_memory/book_decisions 随书清理（级联），不留孤儿

## Capabilities

### 新增
- `assistant-chat-ui`——对话前端：ChatAnywhere 定版、卡面体系、逐字流式全模型、崩溃兜底
- `assistant-memory`——助手分层记忆：四层 scope、书级 agent 记忆与项目决策、注入链、自维护工具

### 修改
- `writing-assistant`——助手身份定义 requirement 增补：身份拼装序加入书级记忆段（身份→书级记忆→域纪律）；会话 requirement 增补：记忆跨页签可见性口径

## Design Impact

- 受影响端：**C端 only**（S端 零改动）
- 受影响屏/弹层：写作工作台右栏助手 dock（唯一受影响区域）——卡面从文本占位升级为真卡面、输入区重挂授权档位芯片（ChatDock 既有形态平移，非新增设计）；无新增屏/弹层
- 对象状态：消息态沿用 ChatAnywhere generating/finished/error 三态（组件内置）；新增卡面形态＝产物卡/授权卡（复用既有卡面，无新形态）
- 两端共享段：**不触碰**（chat.css 为 C端 业务层）
- 原型先行：**不需要**——dock 布局零变化，卡面复用既有 ChatDock 卡面组件与视觉（chat.css 语义类），无新布局决策
- 设计工件：实现侧自查（卡面即既有组件重挂，无设计新增）

## Impact

- **前端**：`client/frontend/src/components/novel/chat/`——Aui2Dock 升级卡面＋delta 流式；退役 ChatDock.tsx/AuiDock.tsx/SseChatAdapter.ts/useChatSession；NovelWorkspace 移除 `?aui=0` 分支
- **后端**：`client/backend/`——models/assistant.py 增 BookAgentMemory/BookDecision 两表＋迁移；assistant/prompts.py 注入链；assistant/tools.py 增三记忆工具；assistant/scopes.py 域声明挂账；assistant/router.py 删书级联
- **依赖**：@agentscope-ai/chat 1.1.72 / @agentscope-ai/design / antd 5.27.6（已在 package.json，零新增）
- **不破坏**：会话/消息表结构零迁移（记忆是新表）；SSE 事件契约增项不删项（text 协议 delta 是新增 narration_delta 事件，前端已消费该事件类型）
