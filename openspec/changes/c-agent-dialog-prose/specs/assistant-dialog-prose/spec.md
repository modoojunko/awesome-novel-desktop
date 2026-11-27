# assistant-dialog-prose Specification (Delta)

## Purpose

把「生成正文」编排进 AI 助手对话框：agent 按剧情取材（过程在对话框可见）→ 出结论卡（选中文笔条目＋用户提示词全文）→ 作家点「开始生成」→ write 链用该提示词与挑选条目独立生成正文。

## ADDED Requirements

### Requirement: 对话框三段式编排生成正文

作家在正文页发起生成正文时，agent SHALL 在对话框内完成编排：取材（读章纲/剧情/进展/设定等既有读工具＋`kb_search_craft`）→ 出结论卡（`draft_prose_plan`）→ 作家点卡上「开始生成」后才启动正文流式。取材与思考过程 SHALL 复用对话框既有过程组件（工具步卡/思考泡泡/计划卡）全程可见。

#### Scenario: 取材过程可见

- **WHEN** agent 执行 kb_search_craft 或读工具
- **THEN** 对话框出现对应工具步卡（含结果摘要）；零命中时摘要明确说「未命中」并留在工具历史里

#### Scenario: 结论卡先行

- **WHEN** agent 完成取材
- **THEN** 对话框出现正文方案卡：选中条目清单（概念/标题/理由）＋用户提示词全文（折叠展示，可展开）＋已有正文警示（如本章已有非空正文）
- **AND** 不点「开始生成」就不启动任何正文生成调用

#### Scenario: 已有正文的再生成确认

- **WHEN** 结论卡标明本章已有正文且作家点「开始生成」
- **THEN** 宿主弹既有再生成确认弹窗，确认后才开流

### Requirement: 用户提示词所见即所发

结论卡 SHALL 展示将要发给正文模型的用户提示词全文；该文本以 `read_write_prompt` 返回的服务端组装稿为基底（agent 可把对话中商定的写作提示并入）。点「开始生成」后 SHALL 以该文本作为 write 调用的 user 提示词（prompt 覆盖通道）。

#### Scenario: 提示词基底来自服务端组装稿

- **WHEN** agent 准备结论卡
- **THEN** 先调 read_write_prompt 取服务端组装稿，再展示/调整；不得凭空拼装全文

#### Scenario: 生成调用使用卡上文本

- **WHEN** 作家点「开始生成」
- **THEN** POST /write body 携带卡上提示词全文作为 prompt 覆盖；write 链按既有优先级（覆盖>存稿>组装）生效

### Requirement: 文笔条目按剧情动态匹配且题材内检索

`kb_search_craft` SHALL 在与写法块同源的候选域内检索（书级副本或账号库＋官方基线 merged 视图），SHALL 按本书题材过滤（书级副本已预筛；基线域按题材收窄）；确定性打分按查询词（缺省取本章概要/剧情条目/挑战）与条目标题＋指令的重合度排序。agent 挑选的条目经结论卡呈现理由；正文生成时 write 链只注入这批条目。

#### Scenario: 题材过滤内建

- **WHEN** 本书题材为 X 且候选域为基线层
- **THEN** 检索结果不含其他题材条目（跨题材串味不出现）

#### Scenario: 动态未命中回退文风设定

- **WHEN** 检索零命中或 agent 未挑选任何条目（kb_picks 为空数组）
- **THEN** 结论卡明示「动态未命中，将按本书文风设定生成」；生成时不注入写法块，system 层文风三区照常生效
- **AND** 不回退到规则选择器兜底凑数

### Requirement: 正文生成调用上下文独立

生成正文的 LLM 调用 SHALL 使用独立组装的上下文（write 链既有 system/user 组装＋作家过目的提示词覆盖＋写法块）；assistant 对话的会话历史、思考过程 SHALL NOT 进入正文模型的 prompt。跨边界只允许两个结构化字段：`prompt`（卡上全文）与 `kb_picks`（条目 id＋理由）。

#### Scenario: 对话历史不进正文 prompt

- **WHEN** 任意一次生成正文调用发出
- **THEN** 正文 prompt 中不包含 assistant 会话转写/消息内容（测试以 fake client 抓取实参断言）

### Requirement: 熔断开关回退直开

env `ASSISTANT_PROSE_FLOW=off` 时 SHALL 禁用对话框编排：正文页「生成正文」chip 回退为直开（再生成确认→直接流式生成，规则选择器写法块照旧）；能力端点 `dialog_prose=false` 供前端判定。缺省（未设置）为开启。

#### Scenario: env 关闭直开回退

- **WHEN** ASSISTANT_PROSE_FLOW=off 且作家点「生成正文」
- **THEN** 不进对话框编排，直接走再生成确认与流式生成；行为与改动前的直开路径一致

#### Scenario: 缺省开启

- **WHEN** env 未设置
- **THEN** 能力端点返回 dialog_prose=true，chip 进对话框编排
