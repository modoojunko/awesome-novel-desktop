## ADDED Requirements

### Requirement: 页面身份与字段注入边界

助手 SHALL 保留最小的页面身份上下文，但页面字段值 SHALL NOT 自动拼进 system/user 提示词：

- 页面身份（当前页面名、`set:*` 面板名、`ch:*` 页签）MAY 继续随轮注入，用于让模型知道「作家在哪一页」。
- 页面字段清单与当前值 SHALL NOT 自动注入；模型需要时 SHALL 调只读工具 `read_page_fields`（见 `assistant-tools`「当前设定页字段按需查询」）。
- 前端 `page_state` SHALL 只带未保存标记；SHALL NOT 为页面字段新增 `panel`/`chapter_tab` 请求字段（当前面板由 `thread` 决定）。
- 同一字段的自动注入与工具结果 SHALL NOT 同时存在（去重），避免模型看到两份口径不同的值。
- 工具结果 SHALL 明确标注「已保存值」；页面有未保存修改时 SHALL 如实提醒，避免把落库值当成屏幕值。

#### Scenario: 调工具前没有字段值
- **WHEN** 作家在题材页发消息，助手尚未调 `read_page_fields`
- **THEN** 当轮 system/user 提示词里只有页面身份，没有 01-05 的字段值；模型需要时自己调工具

#### Scenario: 页面身份仍可用
- **WHEN** 作家在 `set:world` 线程说话
- **THEN** 提示词可含「当前页签：设定·世界」，但不含世界八格的当前值

#### Scenario: 重复注入已移除
- **WHEN** 作家在题材页说话
- **THEN** 提示词中不再出现自动生成的五格字段真值；字段值只出现在 `read_page_fields` 的工具结果里

#### Scenario: 前端不新增页面字段
- **WHEN** 前端提交助手消息
- **THEN** `page_state` 只带未保存标记；不因本能力新增 panel/chapter_tab 字段
