# assistant-tools 增量

## ADDED Requirements

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
