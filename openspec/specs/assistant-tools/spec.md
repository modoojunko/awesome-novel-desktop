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
