## ADDED Requirements

### Requirement: 角色页的状态与体检行词汇

角色设定页 SHALL 只使用既有状态语言与组件词汇，新增的状态与行型 SHALL 按下述口径登记：

- 角色类型（主角 / 配角 / 反派 / 路人）SHALL 作为可点击胶囊复用既有 chip 家族（`.chip` + `.chip.on`），SHALL NOT 另造胶囊类名。
- 人物关系的类型标签 SHALL 复用既有状态胶囊（`.pill` + 既有语气档），SHALL NOT 另造胶囊类名。
- 徽标 SHALL 只用既有档位 `ok / warn / prog / empty`；「已确认」SHALL 用 `ok`（绿）且其文案 SHALL NOT 与其他状态混用。
- 保存态 SHALL 复用既有四态（saving / saved / dirty / failed），失败态 SHALL 给可点击的重试出口。
- 体检（一致性检查）逐项行在角色页 SHALL 使用独立类名（`.chk-row`：名称与结论一行、依据一行），SHALL NOT 覆盖既有 `.chk-line` 的样式作用域；结果区 SHALL 落在 `.ai-sink` 内。
- 体检结论的第四个取值 SHALL 命名为 `conflict`（矛盾），渲染走 err 色；该取值 SHALL NOT 加入既有世界页的结论白名单（避免把「矛盾」在世界页显示成「缺失」）。
- 「内容有变 · 待重新确认」这一状态的文案 SHALL NOT 含「已确认」字样（依据 §5 状态语言 S-R2 与「已确认 → ok 软底徽标」条目；状态措辞以标准正文为准，不在 spec 里另行转述）。
- 「草稿」这类**常态化**状态 SHALL NOT 用 warn 徽标（依据 §5 的 S-R3：警示性徽标不得常态化）；未确认只是常态属性，SHALL 用中性档位表达。

#### Scenario: 只复用既有胶囊与徽标
- **WHEN** 查看角色页的类型胶囊、关系标签与徽标
- **THEN** 它们分别来自既有 chip / pill / badge 档位，页面样式表内不出现新的胶囊类名

#### Scenario: 体检行与既有体检互不影响
- **WHEN** 角色页渲染体检逐项，且世界页/主线页的体检行也存在于同一应用
- **THEN** 角色页的逐项样式只作用于 `.chk-row`，既有 `.chk-line` 的显示不变

#### Scenario: 第四态不污染世界页
- **WHEN** 角色页体检返回 `conflict`
- **THEN** 世界页体检的取值集合仍只含既有三态（不出现 `conflict`）

#### Scenario: 第三态文案合规
- **WHEN** 角色项因内容变动退回未完成
- **THEN** 徽标文案为「内容有变 · 待重新确认」，不含「已确认」字样
