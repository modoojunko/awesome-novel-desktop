# assistant-chat-ui Delta

## ADDED Requirements

### Requirement: 对话前端以 @agentscope-ai/chat 定版

写作助手对话前端 SHALL 以 @agentscope-ai/chat（ChatAnywhere）为唯一实现（Aui2Dock），自研 ChatDock 与 assistant-ui spike（AuiDock）SHALL 退役删除，`?aui` 遗留切换参数 SHALL 移除；既有自研会话链（useChatSession 手搓状态机）SHALL 一并退役，历史装载与流式交付 SHALL 走 ChatAnywhere ref 直控（updateMessage）＋后端 SSE 事件桥。每页签独立会话（独立上下文/历史/流程）SHALL 不变。

#### Scenario: 旧前端退役
- **WHEN** 作家不带任何 URL 参数打开任一页签的助手
- **THEN** 渲染的是 ChatAnywhere 版 dock，`?aui=0` 不再有任何效果；代码库中 ChatDock.tsx、AuiDock.tsx、SseChatAdapter.ts、useChatSession 均已删除

#### Scenario: 页签会话隔离不变
- **WHEN** 作家在章纲页签对话后切换到正文页签再切回
- **THEN** 两页签各自的历史与上下文互不串扰，切回接续原对话（既有页签线程语义零变化）

### Requirement: 产物卡与授权卡以真卡面呈现

产物卡与授权卡 SHALL 以 ChatAnywhere 自定义卡片（customCards）渲染真实卡面：产物卡复用既有 CardBody 卡面组件按 kind 渲染，授权卡 SHALL 含变更预览与「允许」「拒绝」两个可点按钮，点击直接驱动授权端点并在流内更新卡面状态；SHALL NOT 再以文本占位（「产物卡已生成」「● tool ✓」）替代卡面。卡面视觉 SHALL 沿用既有 chat.css 语义类，不新增设计形态。

#### Scenario: 产物卡卡面
- **WHEN** 助手起草一段章纲并交付产物
- **THEN** 对话流内出现结构化产物卡（按 kind 渲染既有卡面），作家可直接读稿并继续对话改稿

#### Scenario: 授权卡流内决策
- **WHEN** 助手请求写回授权
- **THEN** 授权卡含变更预览与允许/拒绝按钮，点击后卡面立即更新为已授权/已拒绝态，流程继续无需刷新

### Requirement: 全模型逐字流式

所有模型的助手回复 SHALL 逐字流式呈现：原生 FC 模型走既有 narration_delta 增量链；文本协议模型的回复 SHALL 经流式解析增量抽取叙述段逐字交付，SHALL NOT 整段等待完成后一次性显示；协议 JSON 壳 SHALL NOT 裸露给作家（deepseek 裸 JSON 回复教训）。流式路径解析失败 SHALL 静默降级为整段交付（narration 兜底事件已消费），SHALL NOT 白屏或重复拼接。

#### Scenario: 文本协议模型逐字出字
- **WHEN** 作家选用 deepseek 等文本协议模型发起对话
- **THEN** 回复随生成逐字上屏，全程看不到协议 JSON 片段

#### Scenario: 流式解析失败降级
- **WHEN** 文本协议流式解析中途失败
- **THEN** 该回合降级为整段交付一次显示，已流出内容不重复拼接

### Requirement: 换前端功能契约保持

换用 ChatAnywhere 后，既有对话功能契约 SHALL 全部保持：斜杠命令（/new 清线程、/compact 手动压缩）、工具步轨迹行（步开始→步结束呈现、完成后可回看）、思考增量呈现与完成后折叠回看、能力盘 chips 结构化触发（tool_hint 随下一次发送携带）、页签切换分隔标记、断流保底与错误卡收尾、容量条（≥80% 警示并提示 /compact）。缺失项 SHALL 在新前端补齐实现，SHALL NOT 以「换前端」为由静默缩水。

#### Scenario: 斜杠命令在新前端可用
- **WHEN** 作家在 ChatAnywhere 输入框输入 /compact
- **THEN** 命令不进入对话历史，压缩执行后收到前后规模对比回执

#### Scenario: 思考回看不丢
- **WHEN** 一轮含思考增量的对话完成
- **THEN** 思考内容折叠回挂本回合气泡，展开可回看

### Requirement: 授权模式在对话框常显可切

dock 输入区 SHALL 常显当前授权档位芯片（当前档常显＋点击下拉切换），提供三档：每写必确认（默认）、本书内自动放行、全部自动放行；切换 SHALL 即时生效并持久化（会话级 grants），SHALL NOT 需要重开会话。硬地板（须作家亲自确认类）写操作 SHALL 不受档位影响、始终停车弹授权卡。助手自身 SHALL NOT 能变更档位（档位变更不进工具注册表——结构性缺席）；作家询问当前授权模式时助手 SHALL 能如实答出（只读）。档位切换 SHALL 在对话流留一行回执。

#### Scenario: 切到本书自动放行
- **WHEN** 作家点授权芯片选「本书内自动放行」
- **THEN** 对话流出现切换回执，后续本书实体写自动执行并带回执＋撤销 chip；硬地板类写仍弹授权卡确认

#### Scenario: 助手不可自改档位
- **WHEN** 作家让助手「给自己开自动放行」
- **THEN** 助手无档位变更工具可调，档位不变，并说明需要作家自己在授权芯片上切换

#### Scenario: 档位持久接续
- **WHEN** 作家切到「本书内自动放行」后关闭应用重开、切页签再切回
- **THEN** 授权芯片仍显示该档位，行为一致

### Requirement: 停止与打断（openwriter/coding agent 必备）

生成进行中作家 SHALL 能随时停止：dock 停止钮/发送区停止钮 SHALL 调服务端停止端点（POST /assistant/stop），后端以**协同取消**收口当前 run（最近检查点自停——步界＋模型流 chunk 级＋授权停车等待），已产出内容保留并落库，流内收到收口话术后停止钮退场；SHALL NOT 出现「只能干等跑满墙钟」的假停止。作家在生成进行中发送新消息 SHALL 打断当前 run（服务端等旧 run 收口后处理新消息，openworker 打断语义），SHALL NOT 以「生成中」为由拒绝新消息；等待收口超时（>4s）才明确提示稍候再试。客户端断开连接 SHALL 尽力置位取消（服务端收尾落库照常）。同一会话并发拒绝语义由打断语义取代。

#### Scenario: 生成中点停止
- **WHEN** 助手正在逐字输出长回复，作家点停止
- **THEN** 流在最近检查点收口并收到「已产出保留」收口话术，停止钮退场，半截内容完整保留可继续对话

#### Scenario: 授权等待中点停止
- **WHEN** run 正停车等待授权批复，作家点停止
- **THEN** 该步骤标记「已停止——这一步没有执行」，run 收口，不产生幽灵授权卡

#### Scenario: 生成中发新消息打断
- **WHEN** 生成进行中作家直接输入新指令发送
- **THEN** 当前 run 被打断收口（半截保留），新指令随即被处理，SHALL NOT 被并发拒绝

### Requirement: 渲染崩溃兜底

ChatAnywhere 渲染异常 SHALL 被 React 错误边界捕获（AuiErrorBoundary 常驻包裹），降级为对话内错误提示与重试入口，SHALL NOT 白屏拖垮整个工作台；错误边界恢复后既有对话历史 SHALL 重新装载。

#### Scenario: 组件渲染异常
- **WHEN** ChatAnywhere 内部渲染抛错
- **THEN** dock 区域显示错误提示与重试入口，工作台其余区域正常可用；点重试后历史重新装载
