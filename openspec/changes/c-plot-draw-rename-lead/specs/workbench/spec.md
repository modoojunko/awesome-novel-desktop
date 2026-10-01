## RENAMED Requirements

- FROM: `### Requirement: 右栏「AI 帮写剧情」动作`
- TO: `### Requirement: 右栏「剧情抽卡」动作`

## MODIFIED Requirements

### Requirement: 右栏「剧情抽卡」动作

- 右栏「AI 辅助」面板章纲页签动作区 SHALL 提供「剧情抽卡」动作（生成类归 PRO；免费态以既有 locked 口径置灰禁点、不隐藏；归档章禁用），点击打开三版选一弹层（口径见 `chapter-plot-items`）；动作 SHALL 为真实链路按钮（无占位）。
- 章纲页签动作行排序（c-plot-draw-rename-lead）：「剧情抽卡」 SHALL 为第 1 行、「盘点出场人物」 SHALL 为第 2 行；其余动作行（剧情推演/补全缺失字段/与卷纲冲突检测）排于两者之后。
- 中栏剧情区 SHALL NOT 出现与「剧情抽卡」同链路的第二入口。

#### Scenario: 免费态锁定卡

- **WHEN** 免费档用户查看章纲页签右栏
- **THEN** 「剧情抽卡」以 locked 口径呈现（置灰禁点、不隐藏），带升级出口

#### Scenario: PRO 打开三版弹层

- **WHEN** PRO 用户在右栏点「剧情抽卡」
- **THEN** 打开三版选一弹层（口径见 chapter-plot-items），中栏无第二入口

#### Scenario: 动作行排序

- **WHEN** 选中一章停在章纲页签查看右栏动作区
- **THEN** 第 1 行为「剧情抽卡」、第 2 行为「盘点出场人物」，其余行为剧情推演/补全缺失字段/与卷纲冲突检测
