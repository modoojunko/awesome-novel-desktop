# prose-writing

## RENAMED Requirements

- FROM: `### Requirement: 选区变换（润色/扩写/压缩）`
- TO: `### Requirement: 选区变换（去AI味/扩写/压缩）`

## MODIFIED Requirements

### Requirement: 选区变换（去AI味/扩写/压缩）

- 系统 SHALL 提供三个选区变换端点（PRO＋本书模型双门控）：`/write/polish`（去AI味）、`/write/expand`（场景扩写）、`/write/compress`（压缩啰嗦段落，保留关键信息与情绪落点，篇幅约原文 50%-70%）；三者共用请求形状（`selected_text`＋`context_before/after`）与对照预览流（接受替换），响应分别返回 `polished_text`/`expanded_text`/`compressed_text`。
- **去AI味口径（c-prose-deai，原「净表达」段落润色整体换目标）**：`/write/polish` SHALL 以「去 AI 腔」为唯一目标——拆掉空洞排比与三段式堆叠、改写「不是……而是……」类 AI 高频模板句、删掉替读者总结/点题/升华的句子、句子长短错落；SHALL 保持原意与信息量、人称时态事实专名不变，篇幅与原文大致相当（约 ±20%），SHALL NOT 借改写扩写/缩写/新增剧情设定；提示词 SHALL 注入文风禁用词/句式单源（`anti_ai_rules`，未配置渲染「（无）」）。
- 缺 `selected_text` SHALL 400；调用已发生而失败（超时/异常）SHALL 记 `*_fail` 账并可重试（502），成功 SHALL 按各自 operation 记账（去AI味沿用 operation=polish，端点/请求/响应字段全不变）。
- 右栏「AI 辅助·正文」的「压缩啰嗦段落」SHALL 为真按钮：正文有选中才可点，进行中显示进行态；去AI味/扩写仍由页内工具卡提供。

#### Scenario: 压缩成功返回文本并记账
- **WHEN** PRO 用户选中一段啰嗦文字并触发压缩
- **THEN** 返回压缩后的文本（对照预览可接受替换），TokenLog 记 operation=compress

#### Scenario: 去AI味成功返回文本并记账
- **WHEN** PRO 用户选中一段机器腔文字并触发「去AI味」
- **THEN** 返回去味后的文本（对照预览可接受替换；user 提示词含「去AI味要求」段与文风禁用词句、system 含「AI 腔」角色定位），TokenLog 记 operation=polish

#### Scenario: 未选中不可点
- **WHEN** 正文没有选中文字
- **THEN** 「压缩啰嗦段落」按钮禁用

#### Scenario: 失败可重试
- **WHEN** 模型超时
- **THEN** 502 且记 compress_fail，正文不动，可重试
