## ADDED Requirements

### Requirement: 章纲页签剧情区

- 章纲页签 SHALL 在既有格子之后提供「剧情」区（条目列表编辑，契约见 `chapter-plot-items`），全档可编辑（免费手写不锁）；空态 SHALL 直接呈现输入框＋引导 placeholder（无引导卡、无「写第一条」按钮）。
- 剧情条目 SHALL NOT 参与「AI 起草」的已有内容覆盖判定（起草只回填章纲格子，不改剧情条目）；剧情区 SHALL NOT 出现任何 AI 按钮（AI 入口唯一化右栏，与既有口径同）。

#### Scenario: 剧情区随章纲页签呈现

- **WHEN** 打开某章章纲页签
- **THEN** 剧情区可见且可直接编辑（空态为直接输入框＋引导 placeholder），区内无 AI 按钮

#### Scenario: AI 起草不动剧情

- **WHEN** 章纲格子全空但已有剧情条目时发起 AI 起草
- **THEN** 不弹覆盖确认（判定只看章纲格子），起草回填只落章纲格子，剧情条目保持不变

### Requirement: 右栏「AI 帮写剧情」动作

- 右栏「AI 辅助」面板章纲页签动作区 SHALL 提供「AI 帮写剧情」动作（生成类归 PRO；免费态以既有 locked 口径置灰禁点、不隐藏；归档章禁用），点击打开三版选一弹层（口径见 `chapter-plot-items`）；动作 SHALL 为真实链路按钮（无占位）。
- 中栏剧情区 SHALL NOT 出现与「AI 帮写剧情」同链路的第二入口。

#### Scenario: 免费态锁定卡

- **WHEN** 免费档用户查看章纲页签右栏
- **THEN** 「AI 帮写剧情」以 locked 口径呈现（置灰禁点、不隐藏），带升级出口

#### Scenario: PRO 打开三版弹层

- **WHEN** PRO 用户在右栏点「AI 帮写剧情」
- **THEN** 打开三版选一弹层（口径见 chapter-plot-items），中栏无第二入口
