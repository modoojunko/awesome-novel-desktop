## ADDED Requirements

### Requirement: 页面态可携带屏上正文文本

前端 `page_state` MAY 额外携带当前章屏上正文全文 `prose_text`，用于只读工具 `read_prose_checks` 现算：

- 取值 SHALL 在发送时刻从正文编辑器取（与自动保存同一序列化单源），SHALL NOT 在装载时缓存。
- `prose_text` SHALL 只进入后端工具上下文（`ToolContext.page_prose`），SHALL NOT 拼进 system/user 提示词，SHALL NOT 落库。
- SHALL 仅在章视图提供（getter 缺失时不带该键）；空串 SHALL NOT 带键。
- 后端 SHALL 对超长文本设上限（50000 字）丢弃并以已保存正文兜底。
- 本字段不属于页面字段值：与「页面身份与字段注入边界」中页面字段禁令不冲突，`panel`/`chapter_tab` 仍 SHALL NOT 新增。

#### Scenario: 章视图发送消息
- **WHEN** 作家在正文页发送消息
- **THEN** 请求 `page_state` 带 `prose_text`（编辑器当前全文）；提示词中不出现正文全文

#### Scenario: 非章视图
- **WHEN** 作家在卷纲页/设定页发送消息
- **THEN** 请求不带 `prose_text`
