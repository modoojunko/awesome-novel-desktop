# prose-writing 变更（增量）

## ADDED Requirements

### Requirement: 选区变换（润色/扩写/压缩）

- 系统 SHALL 提供三个选区变换端点（PRO＋本书模型双门控）：`/write/polish`（净表达）、`/write/expand`（场景扩写）、`/write/compress`（压缩啰嗦段落，保留关键信息与情绪落点，篇幅约原文 50%-70%）；三者共用请求形状（`selected_text`＋`context_before/after`）与对照预览流（接受替换），响应分别返回 `polished_text`/`expanded_text`/`compressed_text`。
- 缺 `selected_text` SHALL 400；调用已发生而失败（超时/异常）SHALL 记 `*_fail` 账并可重试（502），成功 SHALL 按各自 operation 记账。
- 右栏「AI 辅助·正文」的「压缩啰嗦段落」SHALL 为真按钮：正文有选中才可点，进行中显示进行态；润色/扩写仍由页内工具卡提供。

#### Scenario: 压缩成功返回文本并记账
- **WHEN** PRO 用户选中一段啰嗦文字并触发压缩
- **THEN** 返回压缩后的文本（对照预览可接受替换），TokenLog 记 operation=compress

#### Scenario: 未选中不可点
- **WHEN** 正文没有选中文字
- **THEN** 「压缩啰嗦段落」按钮禁用

#### Scenario: 失败可重试
- **WHEN** 模型超时
- **THEN** 502 且记 compress_fail，正文不动，可重试
