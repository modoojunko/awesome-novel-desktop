# c-agent-action-contract 变更：assistant-tools

## ADDED Requirements

### Requirement: 任务计划工具

注册表 SHALL 新增 `update_plan` 工具（kind=read 的会话状态工具，全域共享，免授权）：入参 `items`（每项含稳定 id、人话标题、状态）＋ `mode`（replace/merge，缺省 merge）＋可选 `note`。该工具 SHALL 只写会话内任务计划，SHALL NOT 写书内数据、SHALL NOT 触发授权梯度、SHALL NOT 出现在写类授权卡清单。

工具结果摘要 SHALL 是人话回执（如「计划已更新：3 件，做完 1 件」），SHALL NOT 回显裸 JSON。计划工具 SHALL 挂入共享读集并通过启动校验（registry ⊆ 域∪共享）；连续同工具同参数的调用去重守卫照常生效。

#### Scenario: 建立计划

- **WHEN** 模型在一条多交付物请求的首步调用 `update_plan` 建三项计划
- **THEN** 会话内计划建立，工具回执为人话摘要，不弹授权卡、不写书内数据

#### Scenario: 更新状态

- **WHEN** 模型完成第一项后调用 `update_plan` 把该项置为做完
- **THEN** 计划快照更新，回执说明当前完成件数

#### Scenario: 启动校验与去重

- **WHEN** 应用启动装配注册表且模型连续两次同参调用 `update_plan`
- **THEN** 启动校验通过（工具在共享读集）；第二次调用被去重劝退，不执行

### Requirement: 起草工具入参分层——素材与写法约束

`draft_arc` 的参数 SHALL 拆为两层：`material`（素材——设定、人物、世界观等故事内容）与 `constraints`（写法约束——主题、节奏、文风、披露时机等，只影响怎么写，不是故事内容）；`input` SHALL 保留为兼容别名（`material` 为空时回落 `input`）。

工具层 SHALL 以明确分隔块把两层拼给既有能力核，SHALL NOT 让写法约束混进故事素材被当内容扩写。产物卡 SHALL 回显本次使用的写法约束（人话标签「写法约束」），使作家能核对「按哪条约束校准」。

#### Scenario: 分层入参

- **WHEN** 模型调用 `draft_arc`，`material` 写故事素材、`constraints` 写「真谛前期不点，中期撕开」等写法要求
- **THEN** 能力核收到带分隔的两段文本；写法约束不被扩写成故事内容

#### Scenario: 旧调用兼容

- **WHEN** 旧提示词或旧调用只传 `input`
- **THEN** 工具按 `material` 回落处理，行为与本次变更前一致

#### Scenario: 卡面回显约束

- **WHEN** 带 `constraints` 的 `draft_arc` 返回文本卡
- **THEN** 卡面出现「写法约束」行，列出本次约束；作家过目后可采纳
