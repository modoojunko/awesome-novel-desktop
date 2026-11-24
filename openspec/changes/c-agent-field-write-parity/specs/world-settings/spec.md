## MODIFIED Requirements

### Requirement: 契约 v2 与读写归一化
- PUT /settings/world SHALL 校验 WorldIn 契约：stage/power/cost ≤300 字、条目 value ≤200 字、key ≤20 字、factions ≤6 条、constraints ≤10 条、extra ≤50 条、history ≤100 条、拒绝控制字符；违规 SHALL 返回 400 并指明字段。
- 唯一键口径（架构稿 §2.1 幂等键表【拍板】）：constraints 名目 SHALL 唯一（铁律是硬边界）；factions 仅对已命名势力查重（迁移映射的无名有注行豁免）；history/extra 名目 SHALL NOT 强制唯一（幂等靠 (key, origin)，同 key 不同来源合法并存）。
- GET /settings/world SHALL 永远返回归一化 v2 形状并剥离 `_legacy`；v1 旧数据在读边界自动归一化，原值 SHALL 存入 `_legacy` 供回滚（保留一个版本周期）。
- 旧十字段 SHALL 按映射表搬入且不丢字：geography.scenes→stage 段落并入；geography.climate/limits→extra「地理与风物」；politics.rule→extra「律法与刑罚」；politics.factions（自由文本）→factions[0]{name:"",note:原文}；politics.social→extra「社会与信仰」；politics.cost→extra「律法与刑罚」；rules.world→power；rules.society→extra「律法与刑罚」；rules.personal→cost。
- **agent 字段级写 SHALL 与 PUT 走同一 WorldIn 契约**：`no_power` SHALL 以布尔落库，`history`/`factions`/`constraints`/`extra` SHALL 以条目数组落库；SHALL NOT 以 `str()` 字符串化后写入（字符串形态会让开关恒为开、列表读回为空）。授权卡 preview SHALL 按同一契约预校验，写不进去的值 SHALL NOT 弹卡。

#### Scenario: 旧书升级不丢字
- Given 一本旧书的世界 KV 为旧十字段
- When 打开世界面板
- Then 面板显示归一化后的 v2 内容，原文完整保留在 `_legacy`（可回滚）

#### Scenario: 违规条目被拒绝
- Given 一条铁律 value 超过 200 字
- When PUT /settings/world
- Then 返回 400 且错误指明该条目

#### Scenario: 铁律重复名目被拒绝
- Given constraints 里已有一条「不可推翻的事」
- When PUT 时 constraints 再带一条同名目
- Then 返回 400 且错误指明重复的名目

#### Scenario: 历史允许同名目并存
- Given history 已有「大战与灾变」一条
- When PUT 追加另一条同名目（不同经过）
- Then 保存成功（200），两条并存；lore 幂等合并仍按 (key, origin)
- Given extra 中两条同名目条目
- When PUT /settings/world
- Then 返回 400 且错误指明重复的名目

#### Scenario: agent 写开关与列表保留页面形态
- Given 世界面板现实向开关当前为开、history 已有条目
- When agent 经字段级写把 `no_power` 设为 false，并把 `history` 写成条目数组
- Then 开关变关并保持关（不得因字符串 `"False"` 被归一为开）；GET 读回 history 为同一批条目（不得为空数组）；授权卡前后对比按「开/关」与条目行显示
