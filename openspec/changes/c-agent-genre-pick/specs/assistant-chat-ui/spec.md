## ADDED Requirements

### Requirement: 题材推荐采纳卡

助手产物卡 SHALL 正确呈现「01 题材目录」推荐，不得把程序字段名直接上屏：

- `payload.stype="genre"` 且 `field="catalog"` 时，卡面 SHALL 以中文行标签显示「题材」「子类」「理由」；`sub_genre` 为空时显示「（只定大类）」或省略该行，SHALL NOT 显示 `value`/`theme`/`sub_genre` 等裸键。
- 题材推荐卡 SHALL 可采纳：点「采纳 · 写入」后读取当前题材设置，写入 `theme`/`sub_genre` 并整包保存，其余题材四格、简介、世界等字段 SHALL NOT 被清空或覆盖。
- 设定字段卡（`stype`/`field` 存在，如 `core_promise`）SHALL 使用字段中文名（主要看什么/绝对禁止/吃苦指数/本小说斗什么/简介/世界各格）作为行标签；对象形 `{value,note}` SHALL 拆成主值与「备注」两行，SHALL NOT 显示裸 `value`。
- 写回成功回执 SHALL 说人话（如「已写进 01 题材：都市 / 都市职场」），并触发设定域刷新。

#### Scenario: 题材卡显示人话
- **WHEN** 助手产出 `field="catalog"`、`value={theme:"都市", sub_genre:"都市职场", note:"书名带城市夜班与职场冲突"}` 的卡
- **THEN** 卡面显示「题材：都市」「子类：都市职场」「理由：书名带城市夜班与职场冲突」，且没有 `value` 字样

#### Scenario: 爽点字段卡也不再露裸键
- **WHEN** 助手产出 `core_promise` 卡，value 为 `{value:"以弱破强的痛快", note:"…"}`
- **THEN** 卡面显示「主要看什么」与「备注」两行，不显示 `value`

#### Scenario: 采纳不破坏其它设定
- **WHEN** 当前书已有 forbidden_list/cost_ratio/battlefield 与简介，作家采纳题材卡
- **THEN** 只更新 theme/sub_genre，其余字段保持原值，回执说明写到 01 题材
