# c-agent-fleet 变更：总调度＋域 agent 舰队

## MODIFIED Requirements

### Requirement: 助手身份结构化定义

助手 SHALL 有一份结构化身份定义（identifier/名称/性格/语气规范/纪律边界/能力围栏声明/版本），经提示词包管线分发，所有页面所有场景共用；身份定义 SHALL 通过启动校验（缺失必需字段即拒绝加载）。助手全部用户可见话术 SHALL 符合身份定义中的语气规范（人话红线：短句、口语、禁报表腔）。作家 SHALL 可在顶栏控制中心菜单查看并编辑助手人格（名称/性格/说话规矩/能力边界四字段，缺失即拒绝保存；保存下一轮对话生效；可一键恢复默认＝删除覆盖回到提示词包/内置）；用户覆盖残缺时 SHALL 静默回落提示词包/内置，SHALL NOT 拒载。作家画像与助手人格的查看/编辑入口 SHALL 收敛在顶栏控制中心菜单（工作台语境），dock 脚部不再保留画像入口。

**域 agent persona SHALL 自身份定义单源派生**：每个域 agent 的提示词＝身份定义＋该域专属纪律段，SHALL NOT 维护与身份定义独立的第二份人格源；身份定义更新时全部域 agent persona SHALL 自动跟随。作家自定义人格覆盖 SHALL 作用于总调度与全部域 agent（单一人格源原则）。

#### Scenario: 作家自定义助手人格
- **WHEN** 作家在顶栏控制中心「助手人格」修改搭档性格并保存
- **THEN** 缺字段的保存被拒绝并明确提示；保存成功后下一轮对话按新人设说话，总调度与全部域 agent 同步生效；「恢复默认」立即回到提示词包/内置版本

#### Scenario: 身份定义缺失拒载
- **WHEN** 提示词包中助手身份定义缺失必需字段
- **THEN** 助手能力按缺包降级处理并明确报错，SHALL NOT 以残缺身份上线

#### Scenario: 域 persona 单源派生
- **WHEN** 提示词包更新身份定义（语气规范收紧）
- **THEN** 全部域 agent 的 persona 随新身份定义自动更新，SHALL NOT 出现某个域沿用旧人格

## ADDED Requirements

### Requirement: 总调度路由——每条消息先进总调度

助手 SHALL 采用总调度路由形态：作家消息 SHALL 全部先经总调度 agent 分类；总调度识别任务域后委派对应域 agent 执行，域外请求、闲聊、跨域综合任务由总调度自己承接。总调度 SHALL NOT 持有域写工具（生成/写回/建卡执行类）——写操作 SHALL 物理上只经委派到域 agent 执行。当前 tab SHALL 作为路由先验注入总调度，但 SHALL NOT 硬性决定路由（设定页问正文章节 SHALL 委派正文域而非拒绝）。

#### Scenario: 域内任务委派
- **WHEN** 作家在设定页说「帮我补全力量体系」
- **THEN** 总调度识别为设定域任务，委派设定 agent 执行，产物卡回同一对话

#### Scenario: 跨页路由先验不锁死
- **WHEN** 作家在设定页说「把第 3 章的章纲缺的字段补了」
- **THEN** 总调度识别为章纲域任务并委派章纲 agent，SHALL NOT 因当前在设定页而拒绝或自答冒充

#### Scenario: 域外任务总调度自答
- **WHEN** 作家问「我这本书整体节奏怎么样」
- **THEN** 总调度读进度/卷纲自行分析回答，SHALL NOT 空委派

### Requirement: 域 agent 注册表——AgentSpec 封封闭

域 agent SHALL 以 AgentSpec 封闭注册：name/title/persona/domain_hint（委派判据）/tool_scope（全量工具注册表的子集）。注册表 SHALL 启动校验：tool_scope ⊆ 全量注册表、总调度 tool_scope 不含域写工具、注册表外的域 SHALL NOT 出现。读类工具 SHALL 全域共享；域写工具 SHALL 只进本域 tool_scope。域 agent SHALL NOT 再委派（嵌套一层封顶，总调度唯一）。

#### Scenario: 域写工具越域拒绝
- **WHEN** 总调度被要求直接执行设定字段生成（不委派）
- **THEN** 该调用因总调度 tool_scope 不含此工具而不可发生，任务走向为委派设定 agent

#### Scenario: 注册表启动校验
- **WHEN** AgentSpec 注册了 tool_scope 含未知工具或总调度持有域写工具
- **THEN** 启动校验失败并明确报错，SHALL NOT 以残缺舰队上线

#### Scenario: 域 agent 不得再委派
- **WHEN** 域 agent 执行中试图调用委派工具
- **THEN** 调用被拒绝并提示向总调度返回结果，由总调度决定后续

### Requirement: 委派执行——嵌套循环与纪律继承

总调度委派 SHALL 以原生工具调用形式执行：内嵌运行域 agent 循环（读域上下文→调域工具→产物卡），域循环的步事件 SHALL 带 agent 身份标签流入同一线程，dock 轨迹组 SHALL 标明当前执行域（作家感知仍为「AI 助手」单对话）。纪律 SHALL 逐级继承：单回合墙钟由总调度持有、委派消耗共享预算（委派前 SHALL 检查剩余预算，不足拒派并收口）；作家停止 SHALL 穿透域循环干净关闭；域循环内写工具照常过授权梯度且 gate 事件透传；域循环转写用后即弃（SHALL NOT 写入线程历史），线程压缩口径不变。

#### Scenario: 轨迹带域身份
- **WHEN** 总调度委派设定 agent 补全字段（两步执行）
- **THEN** 运行轨迹逐行点亮并标注「设定助手」，产物卡落同一对话流

#### Scenario: 墙钟预算切分
- **WHEN** 单回合剩余预算不足以完成一次委派
- **THEN** 总调度拒派并以收尾话术结束，已产出卡保留

#### Scenario: 停止穿透域循环
- **WHEN** 作家在域 agent 执行中点停止
- **THEN** 域循环 GeneratorExit 干净关闭，半截产物按停止落库语义处理，总调度循环同步退出

#### Scenario: 授权梯度透传
- **WHEN** 域 agent 执行写类工具需授权
- **THEN** gate 事件照常发出，作家看到的授权请求标明来自对应域任务
