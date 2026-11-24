## MODIFIED Requirements

### Requirement: 页面操作工具族——导航与字段级写

注册表 SHALL 新增页面操作工具（除写正文外——对话不代笔纪律不变）：

- `navigate`（kind=read，全域共享，免授权）：跨大视图（书架/写作/设定/预览）与跨章＋章内页签的真跳转，走既有 navigate effect 通道；target 编码 `view[:章ref[:页签]]`，工具层校验视图/页签白名单；
- `write_chapter_fields`（kind=write）：章纲字段 patch 写（章纲概要/出场角色/碰到的挑战/阶段/章末落点/剧情/必须完成的变化/禁止事项/主情绪/本章目标字数），白名单外字段拒绝；落库走 `save_chapter` patch-gates（缺键保现值）。一次传多个字段时 SHALL 按字段族合并（`outline`/`memo`/`emotional_design` 族内互不覆盖），所有 provided 字段 SHALL 全部进入 patch；
- `write_settings_field`（kind=write）：设定字段写，按面板分派（genre 四字段现卡合并后整卡校验落库、story synopsis 单键、world v2 键合并），SHALL NOT 覆盖未提及字段。02 短标签 `core_promise` SHALL NOT 进入 agent 可写集（标签走 `settings_genre_core_promise` 采纳卡；主句写 `promise_note`）。world 字段 SHALL 保留页面契约的原生类型：`no_power` 为布尔、`history`/`factions`/`constraints`/`extra` 为条目数组；SHALL NOT 以字符串化形态落库。
- `write_volume_fields`（kind=write）：卷纲字段 patch 写（卷名/本卷主旨/主要冲突/卷末收在哪里/章数目标/坎的类型/坎的一句话），白名单外字段拒绝；授权卡 preview SHALL 按页面名呈现字段前后，且与 `VolumeUpdate` 同源校验（闭集/上限），写不进去的卡 SHALL NOT 弹出。

字段级写工具 SHALL 走既有服务链（章纲 `save_chapter` patch-gates、设定 caps、卷纲 `volumes.service`），SHALL NOT 直调路由 handler 或伪造表单快照；SHALL 抓取写入前值构造「字段：写入前 → 写入后」对比（授权卡 preview 与 write_log 撤销数据源同源）；SHALL 无 feature_key（作家编辑自己的字段不吃付费档位闸）；作用域 SHALL 按编辑面挂域（章纲字段写→章纲域、设定字段写→设定域、卷纲字段写→卷纲域）并过启动校验。

字段级写工具的参数说明 SHALL 与页面可见字段名和实际值形态一致；跨字段同族写入 SHALL NOT 因浅合并丢失（如章纲 `summary`＋`characters`、`required_changes`＋`prohibitions` 同时给出时两条都要落库）。写入链的契约校验（`WorldIn` / `NovelGenreIn` / 章纲字段校验）SHALL 与页面写入口同源，违规值 SHALL 返回人话错误且不落库。

#### Scenario: 字段级写只动给定字段
- **WHEN** agent 调 write_chapter_fields 只写「碰到的挑战」
- **THEN** 该章其他章纲字段保持现值（patch-gates），changes 携带「写入前 → 写入后」

#### Scenario: 章纲一次写同族多字段全部落库
- **WHEN** agent 调 write_chapter_fields 同时写 `summary` 与 `characters`（或同时写 `required_changes` 与 `prohibitions`）
- **THEN** 两个字段都写入并出现在回执 changes 中，SHALL NOT 出现后者覆盖前者导致某一字段静默不落库

#### Scenario: genre 单字段写不覆盖他字段
- **WHEN** agent 调 write_settings_field 写 genre.battlefield
- **THEN** 现卡整体合并后整卡校验落库，core_promise/promise_note/forbidden_list 保持现值

#### Scenario: world 开关与条目保留原生形态
- **WHEN** agent 调 write_settings_field 写 `world.no_power=false` 或写 `world.history` 条目数组
- **THEN** 落库值为布尔 `false` / 条目数组；随后 GET 世界面板读回同一形态（开关为关、条目可见），SHALL NOT 出现字符串 `"False"` 或 Python repr 条目

#### Scenario: 卷纲授权卡按页面名看前后
- **WHEN** agent 调 write_volume_fields 写 `summary`
- **THEN** 授权卡显示「本卷主旨：旧值 → 新值」；未知字段/闭集外值（如 antagonist_type）SHALL NOT 弹卡

## ADDED Requirements

### Requirement: 页面字段说明书（read_page_schema）

agent SHALL 有零参数只读工具 `read_page_schema`，按当前页面（thread）返回字段元数据：页面可见名、别名、字段键、类型/上限、写入口。agent 写改前 SHALL 先用它把作家说法做精确或语义匹配，再按写入口请求授权写入。

- 覆盖有字段级写入口的页面：设定题材/简介/世界、章纲、卷纲；无字段级写入口的页面 SHALL 如实说明并指向现值读取工具，SHALL NOT 编造字段。
- SHALL 只给元数据、不给现值；现值走 `read_page_fields`（设定）/`read_chapter`（章纲，按本表逐格）/`read_outline`（卷纲，按本表逐格）。
- 字段标签 SHALL 与页面小标题一致（复用写核字段名单一源）；类型/上限 SHALL 与写链契约一致。
- 匹配仍不唯一时 agent SHALL 用字段名问一句，SHALL NOT 猜字段。

#### Scenario: 按页面说法找到对应字段
- **WHEN** 作家说「把主要看什么改成……」
- **THEN** agent 先调 `read_page_schema` 得到「主要看什么 → promise_note｜≤200 字｜write_settings_field」，再按该键请求写入；`core_promise` 标为「页面标签，不直接写」并指向「出爽点」采纳卡

#### Scenario: 非字段写页面
- **WHEN** 在角色/主线/文风/正文等没有字段级写入口的页面调用
- **THEN** 工具返回「本页没有字段级写入口」并指向对应面板/AI 卡与现值读取工具，SHALL NOT 列出可写字段
