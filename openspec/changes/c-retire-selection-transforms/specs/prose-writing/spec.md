## REMOVED Requirements

### Requirement: 选区变换（去AI味/扩写/压缩）

**Reason**：场景扩写与压缩啰嗦段落退役（c-retire-selection-transforms）——扩写新场景可由整章生成覆盖、压缩冗余为去AI味删冗余子能力；三端点条款随两功能退役。

**Migration**：去AI味（polish）全链由本 delta 的 ADDED「选区变换（去AI味）」原样承接（端点/口径/对照预览/记账全不变）；`operation=expand/compress` 历史计量行留存。

## ADDED Requirements

### Requirement: 选区变换（去AI味）

- 系统 SHALL 提供选区变换端点（PRO＋本书模型双门控）：`/write/polish`（去AI味）；请求形状（`selected_text`＋`context_before/after`）与对照预览流（接受替换）不变，响应返回 `polished_text`。
- **去AI味口径（c-prose-deai，原「净表达」段落润色整体换目标）**：`/write/polish` SHALL 以「去 AI 腔」为唯一目标——system 层挂恒定检查清单逐句执行（无命中的句子原样保留、不为改而改；拆四字词堆叠、对仗式解释句保后半改直陈、空泛「仿佛/宛如」删而具体比喻留、段尾总结升华句整句删、段内做长短错落不动段落边界、明显错别字顺手修）；SHALL 保持画面/事实/动作/人物关系等信息不变（空转总结与填充词不算信息量）、人称时态专名不动；篇幅为单向上限＝原文 110%（删冗余缩至约 70% 属正常，不得为凑长度保留该删词句）；输出 SHALL 保持原段落划分与换行、对话引号内字句原样、不用引号/代码块包裹；选区 SHALL 以边界标记包裹、上下文语境标注「仅供理解衔接、禁止改写输出」；提示词 SHALL 注入文风禁用词/句式单源（`anti_ai_rules`，未配置渲染「（无）」；文风未配置时以原文自身文风为准），优先级＝禁止规则＞检查清单＞文风参考。
- 缺 `selected_text` SHALL 400；调用已发生而失败（超时/异常）SHALL 记 `polish_fail` 账并可重试（502），成功 SHALL 记账（operation=polish，端点/请求/响应字段全不变）。
- 右栏「AI 辅助·正文」的「去AI味」SHALL 为真按钮：正文有选中才可点，进行中显示进行态。

#### Scenario: 去AI味成功返回文本并记账

- **WHEN** PRO 用户选中一段机器腔文字并触发「去AI味」
- **THEN** 返回去味后的文本（对照预览可接受替换；system 含「AI 腔」角色定位与检查清单、user 含边界标记与文风禁用词句），TokenLog 记 operation=polish

#### Scenario: 未选中不可点

- **WHEN** 正文没有选中文字
- **THEN** 「去AI味」按钮禁用

#### Scenario: 失败可重试

- **WHEN** 模型超时
- **THEN** 502 且记 polish_fail，正文不动，可重试
