# assistant-tools Delta

## ADDED Requirements

### Requirement: 设定读面——五格与简介真值

`read_settings` 工具 SHALL 在既有 premise/world/cast/hooks 之外新增两个共享读分区，使模型按需可读设定页现值（与 `read_page_fields` 分工：本工具给全量/全文按需细读，`read_page_fields` 给当前面板字段＋已保存现值；两者都不自动注入提示词）：

- `genre` 分区：返回题材五格现值与未填点名（未填字段逐格点名「未填」，已填给值；题材含大类＋子类；禁忌/战场为中文词汇 label）——与题材目录工具（读 36 类封闭目录的「可选值」）分工明确：本分区读「这本书现在填了什么」。
- `intro` 分区：返回简介现值；无简介时返回「（简介还没有内容）」。
- 两分区 SHALL 保持共享读属性（全域页签可读、免授权），并随注册表过启动校验。

#### Scenario: 读五格现值

- **WHEN** 模型在任意页签调 read_settings(area="genre")，五格已部分填写
- **THEN** 返回已填字段现值＋未填字段逐格点名（非整段空白或异常）

#### Scenario: 读简介

- **WHEN** 模型调 read_settings(area="intro") 且简介已写
- **THEN** 返回简介全文（预算截断内）；未写时返回「（简介还没有内容）」

#### Scenario: 全域可读

- **WHEN** 作家在章纲页签让助手「看看题材定了没」
- **THEN** read_settings 在共享读集内可被调用，模型如实报五格状态

## MODIFIED Requirements

### Requirement: 页面操作工具族——导航与字段级写

注册表 SHALL 新增页面操作工具（除写正文外——对话不代笔纪律不变）：

- `navigate`（kind=read，全域共享，免授权）：跨大视图（书架/写作/设定/预览）与跨章＋章内页签的真跳转，走既有 navigate effect 通道；target 编码 `view[:章ref[:页签]]`，工具层校验视图/页签白名单；
- `write_chapter_fields`（kind=write）：章纲字段 patch 写（概要/出场角色/挑战/阶段/章末落点/剧情条目/必须完成的变化/禁则/主情绪/目标字数），白名单外字段拒绝；落库走 `save_chapter` patch-gates（缺键保现值）；
- `write_settings_field`（kind=write）：设定字段写，按面板分派（genre 五字段 core_promise/promise_note/forbidden_list/cost_ratio/battlefield 现卡合并后整卡校验落库、story synopsis 单键、world v2 键合并），SHALL NOT 覆盖未提及字段；题材目录（theme/sub_genre）SHALL NOT 进本白名单——题材写走题材目录采纳卡单一通道，SHALL NOT 出现双写路径。

字段级写工具 SHALL 走能力核（caps 字段写族：读现值→合并→既有服务链），SHALL NOT 直调路由 handler 或伪造表单快照；SHALL 抓取写入前值构造「字段：写入前 → 写入后」对比（授权卡 preview 与 write_log 撤销数据源同源）；SHALL 无 feature_key（作家编辑自己的字段不吃付费档位闸）；作用域 SHALL 按编辑面挂域（章纲字段写→章纲域、设定字段写→设定域）并过启动校验。

#### Scenario: 字段级写只动给定字段
- **WHEN** agent 调 write_chapter_fields 只写「碰到的挑战」
- **THEN** 该章其他章纲字段保持现值（patch-gates），changes 携带「写入前 → 写入后」

#### Scenario: genre 单字段写不覆盖他字段
- **WHEN** agent 调 write_settings_field 写 genre.battlefield
- **THEN** 现卡整体合并后整卡校验落库，core_promise/promise_note/forbidden_list 保持现值

#### Scenario: 口述转写主要看什么
- **WHEN** 作家说「把我刚说的这段写进主要看什么」，授权卡批复
- **THEN** write_settings_field 写 genre.promise_note 成功落库（超长/非法值被人话报错拦下）；授权卡 preview 显示「主要看什么：写入前 → 写入后」

#### Scenario: 题材不走字段级写
- **WHEN** agent 被要求写 01 题材
- **THEN** write_settings_field 拒绝 theme/sub_genre（白名单外）；题材经题材目录采纳卡成对写入
