# assistant-tools Specification

## Purpose
agent 工具面：后端既有能力封装为封闭注册表的 agent 工具——作家在对话里一句话完成结构管理与世界观起草，写类走授权梯度。

## Requirements

### Requirement: 结构管理动作收编

agent SHALL 提供书结构管理写工具（封闭注册表，写类，走授权梯度默认每写必确认）：确认章纲/撤回章纲确认、章节归档/取消归档、新增一卷、新增一章。写授权卡 SHALL 携带人话预览（作家批前看得见改什么）；拒绝则不执行。结构动作 SHALL 复用既有后端服务（与面板同源），SHALL NOT 新建平行写路径。

#### Scenario: 一句话确认章纲
- **WHEN** 作家说「确认第七章的章纲」
- **THEN** 助手经写工具执行确认（授权卡批复后），回执告知确认完成

#### Scenario: 新增一卷一章
- **WHEN** 作家说「开第二卷，加第一章」
- **THEN** 授权后建卷建章，回执带卷/章定位，左侧目录即时可见

### Requirement: 世界观能力收编

agent SHALL 提供世界观三读/产卡工具：世界观起草（按设定出世界观候选卡）、世界观校验（找设定冲突）、传说建议（lore 候选）——与设定·世界观面板同源（同一后端能力），产物过目采纳，SHALL NOT 自动写回设定。

#### Scenario: 起草世界观
- **WHEN** 作家在设定语境说「帮我起草这个世界的设定」
- **THEN** 助手产世界观候选卡（含锚点标注），过目后由作家采纳；不自动写回

### Requirement: 域挂账与启动校验

新工具 SHALL 挂入 scopes 域（结构动作全域共享；世界观挂设定域）并通过启动校验（registry ⊆ 域∪共享）；未挂账工具拒绝加载。

#### Scenario: 启动校验覆盖
- **WHEN** 应用启动装配工具注册表
- **THEN** 校验通过（无表外工具），新工具在全页签可被意图命中

### Requirement: 页面操作工具族——导航与字段级写

注册表 SHALL 新增页面操作工具（除写正文外——对话不代笔纪律不变）：

- `navigate`（kind=read，全域共享，免授权）：跨大视图（书架/写作/设定/预览）与跨章＋章内页签的真跳转，走既有 navigate effect 通道；target 编码 `view[:章ref[:页签]]`，工具层校验视图/页签白名单；
- `write_chapter_fields`（kind=write）：章纲字段 patch 写（概要/出场角色/挑战/阶段/章末落点/剧情条目/必须完成的变化/禁则/主情绪/目标字数），白名单外字段拒绝；落库走 `save_chapter` patch-gates（缺键保现值）；
- `write_settings_field`（kind=write）：设定字段写，按面板分派（genre 四字段现卡合并后整卡校验落库、story synopsis 单键、world v2 键合并），SHALL NOT 覆盖未提及字段。

字段级写工具 SHALL 走能力核（caps 字段写族：读现值→合并→既有服务链），SHALL NOT 直调路由 handler 或伪造表单快照；SHALL 抓取写入前值构造「字段：写入前 → 写入后」对比（授权卡 preview 与 write_log 撤销数据源同源）；SHALL 无 feature_key（作家编辑自己的字段不吃付费档位闸）；作用域 SHALL 按编辑面挂域（章纲字段写→章纲域、设定字段写→设定域）并过启动校验。

#### Scenario: 字段级写只动给定字段
- **WHEN** agent 调 write_chapter_fields 只写「碰到的挑战」
- **THEN** 该章其他章纲字段保持现值（patch-gates），changes 携带「写入前 → 写入后」

#### Scenario: genre 单字段写不覆盖他字段
- **WHEN** agent 调 write_settings_field 写 genre.battlefield
- **THEN** 现卡整体合并后整卡校验落库，core_promise/promise_note/forbidden_list 保持现值

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
