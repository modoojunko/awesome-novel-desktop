## MODIFIED Requirements

### Requirement: agent 页面操作——跨视图导航与字段级写

agent SHALL 拥有页面操作能力（除正文写入外——对话不代笔纪律不变）：

- **导航**：`navigate` 工具（kind=read，免授权）SHALL 支持跨大视图（工作台/设定/预览/书架）与跨章跳转，target 含视图＋可选章 ref＋可选章内页签；前端按既有 effect 通道真实翻页，且 SHALL 复用页面切换的未保存修改守卫（有未保存修改时照手点语义拦截/提示，不静默丢弃）。
- **字段级写**：`write_chapter_fields`（章纲字段 patch 写）与 `write_settings_field`（设定字段写，按面板分派）工具（kind=write）SHALL 全部经授权策略管控（write_gate 两档＋硬地板），SHALL 走既有真实写链（章纲 patch-gates 缺键保现值；设定按面板 GET+merge+PUT/单字段端点，SHALL NOT 覆盖未提及字段），SHALL 抓取写入前值进 write_log（撤销数据源口径）。
- **授权卡字段级 preview**：字段级写工具的授权卡 preview SHALL 呈现「字段：写入前 → 写入后」人话行（工具写前读现值构造），SHALL NOT 只给裸参数 JSON。字段名 SHALL 与页面可见字段名一致（设定页 02-05、章纲页各格名）；世界字段的值 SHALL 按页面口径呈现（开关显示开/关、条目显示为条目行），SHALL NOT 显示内部键名、`True`/`False` 或 Python repr。
- **preview 与写链同源校验**：preview SHALL 按真实写链的同一契约预校验（`WorldIn` / `NovelGenreIn` / 章纲字段校验：阶段闭集、数组形状、文本上限、数值范围、开关类型）；注定写不进去的请求 SHALL NOT 弹授权卡，SHALL 以人话拒绝理由回喂模型改对再来。
- **页面状态随行**：前端的未保存修改标记（设定/卷纲/章纲编辑态/正文）SHALL 随消息注入提示词（只进模型，界面零渲染），使模型在写改前知悉未保存状态。

#### Scenario: 跨视图跳转
- **WHEN** 作家说「打开第 3 章的正文」
- **THEN** 助手调 navigate（workbench＋第 3 章＋正文页签），页面真实翻页并在对话流留页面切换标记

#### Scenario: 确认档字段写入弹卡看前后
- **WHEN** 档位为每写必确认，作家说「把主线核心冲突改成 X」
- **THEN** 弹授权卡逐字段呈现「写入前 → 写入后」，字段名与对应页面小标题一致，允许后经既有写链落库并触发面板刷新；拒绝则不执行

#### Scenario: 写不进去的值不弹卡
- **WHEN** agent 想写的值过不了写链契约（如章纲阶段不在六档、列表字段形状不对、题材战场项超 20 字、目标字数非数字、世界开关为字符串）
- **THEN** SHALL NOT 出现授权卡；助手收到人话拒绝理由，改对后再重新请求

#### Scenario: 世界字段按页面口径显示
- **WHEN** 授权卡展示 `world.no_power` 或 `world.history` 的前后对比
- **THEN** 开关显示「开/关」、条目显示为条目行；SHALL NOT 出现 `True`/`False`、Python repr 或内部键名

#### Scenario: 自动档字段写入直执行
- **WHEN** 档位为自动执行·本书内，作家说「把主线核心冲突改成 X」
- **THEN** 写入直执行并在对话流带回执（写入实体与字段），硬地板类操作仍弹卡

#### Scenario: 未保存修改守卫
- **WHEN** 页面存在未保存修改且 agent 触发导航或面板刷新
- **THEN** 照手点同语义守卫处理（拦截/提示手动刷新），SHALL NOT 静默覆盖作家的未保存修改
