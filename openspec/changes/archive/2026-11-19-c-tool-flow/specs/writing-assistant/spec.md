# c-tool-flow 变更：对话式触发调用工具的流程整理

## MODIFIED Requirements

### Requirement: agent 循环为多步工具调用且受护栏约束

助手由 agent 循环驱动：解析作家输入为一次多步执行（读书→调工具→再思考→产出）。工具执行函数 SHALL 返回 dict 契约——成功 `{"<内容键>": …}`、失败 `{"error": str, "error_type": str}`，SHALL NOT 以异常穿透执行层；循环 SHALL 兜异常归一为 error 结果回填。给模型看的结果摘要与给人看的产物卡 SHALL 职责分离，用户可见侧车元数据 SHALL 走 `_display` 键（模型不可见）。生成类工具的结果摘要 SHALL 含「已交付＋任务完成」收口语义；循环 SHALL 对连续同工具同参数的调用去重劝退（不执行、回喂）。

#### Scenario: 执行异常归一
- **WHEN** 工具执行抛出异常
- **THEN** 循环归一为 `{"error", "error_type"}` 结果回填，SHALL NOT 断流

#### Scenario: 生成工具摘要收口
- **WHEN** 抽卡/推演/盘点类工具完成
- **THEN** 摘要带「已交付＋本轮完成」，SHALL NOT 诱导模型原地重跑

#### Scenario: 连续同参调用劝退
- **WHEN** 模型连续发起同工具同参数的调用
- **THEN** 第二次不执行，回喂去重话术（产物已交付——收口或换做法）

## ADDED Requirements

### Requirement: 能力核层——端点与工具同源

大模型能力管线 SHALL 抽取为能力核（caps 纯函数层：业务语义 dataclass 入参、结构化结果出参、模型调用/解析/重试/门槛校验私有在核内）；HTTP 端点（面板）与 agent 工具 SHALL 同调一层能力核，SHALL NOT 出现工具直调路由 handler 或伪造面板表单快照。域映射 SHALL 启动校验：注册表每个工具恰属「共享读 ∪ 至少一个域」。

#### Scenario: 工具不再伪造面板表单
- **WHEN** agent 调用人物盘点能力
- **THEN** 走 caps 能力核（业务语义入参），SHALL NOT 构造盘点面板的表单快照 body

#### Scenario: 面板与对话同核
- **WHEN** 作家在盘点面板与在对话里分别触发人物盘点
- **THEN** 两者调同一能力核，结果同源

### Requirement: chips 结构化触发

页签 chips SHALL 以结构化意图声明（label 人话意图句＋tool＋args）；点击后 SHALL 发「意图句＋tool_hint」——循环首步确定性执行该工具（域校验、授权梯度、去重守卫照走），结果回填后模型接管解读与续做；作家自由输入 SHALL 无 hint 全 agentic。tool_hint SHALL NOT 绕过任何护栏。

#### Scenario: 点 chip 确定性首步
- **WHEN** 作家点击「剧情抽卡」chip
- **THEN** 首步直接执行 draw 工具（不经模型猜话术），产物卡回对话后模型接管收口

#### Scenario: 自由输入不受影响
- **WHEN** 作家自由输入与某 chip 同义的话
- **THEN** 走全 agentic 路径（模型按域收敛目录自选工具），行为与 chip 点击同源同核
