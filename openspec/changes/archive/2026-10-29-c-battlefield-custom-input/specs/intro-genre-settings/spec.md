## ADDED Requirements

### Requirement: 05「本小说斗什么」＝预设胶囊 + 回车自定义（设计原型「＋自定义」落实现）

- 05 格 SHALL 在预设胶囊排下提供**回车自定义输入框**（同 03 绝对禁止的手填形态）：作者可输入候选之外的战场词，回车即落为一颗可 × 移除的自定义胶囊；输入 SHALL 以 `battlefieldTextMax`（20 字）为长度上限。自定义战场与 AI 采纳的自定义文本走**同一存储通道**（`novel_genre_battlefield.custom_text`），保存契约不变（battlefield 数组，文本项为合法载荷）。
- 输入词与候选**同名或同 id** SHALL 落为**预设勾选**（不另造重复胶囊）；输入词已存在（预设已勾或自定义已在）SHALL 提示且不重复添加。
- 自定义战场与勾选**共用 `battlefieldMax`（10 个）上限**，到顶 SHALL 提示不新增；「建议 1-2 个，第 3 个出软提示不禁止」口径不变（勾选＋自定义合并计数）。
- 添加动作本身 SHALL NOT 出回执（同 03 自定义禁区：回执只覆盖勾选／取消与 AI 采纳）。
- 形如 `kind:slug`（`promise:`／`forbidden:`／`battlefield:` 前缀）的词汇引用样输入 SHALL 拒收并提示、不清空输入——后端保存按前缀把这类值落成词汇引用，手造 id 不在候选源里会使保存 FK 违例（500）；「像机器标识的值 SHALL NOT 落成自定义文本」同款口径，AI 采纳路径有归一化拦，手填路径在录入端拦截。

#### Scenario: 回车自定义战场
- Given 题材面板 05 格，作者未勾任何预设
- When 在输入框输入「抢天道机缘」并回车
- Then 胶囊排出现「抢天道机缘 ×」自定义胶囊，点击 × 可移除
- And 保存报文仍为 battlefield 数组（文本项原样入列，custom_text 通道）

#### Scenario: 与预设同名落勾选不重复
- Given 预设胶囊含「查真相」
- When 作者输入「查真相」并回车
- Then 预设「查真相」变为勾选态，SHALL NOT 出现「查真相 ×」自定义胶囊

#### Scenario: 上限与软提示口径不变
- When 勾选＋自定义合计已有 3 个战场
- Then 出现「战场越多，主线越难聚焦」软提示且不禁止继续添加
- And 到 10 个上限后再回车 SHALL 提示不新增

#### Scenario: 词汇引用样输入拒收
- Given 05 格自定义输入框
- When 作者输入「battlefield:hack」并回车
- Then 出现拒收提示、不出胶囊、输入保留待改
- And 保存不再有 vocab 引用误落（FK 违例面消除）
