## Why

作家在设定页说「这个/这格/这里」时，助手应该知道当前面板有哪些字段、现在填的是什么。但这件事**不能靠把字段值自动拼进提示词**：会每轮灌上下文、与未保存输入混淆，而且当前 #1119/#1120 两套自动注入在题材页重复给模型两份真值。

## What Changes

- 新增后端只读工具 `read_page_fields`（零参数）：按当前请求的 `thread`（`set:<panel>`）读当前设定面板的字段清单与**已保存**现值；只挂 `set:*` 域，不读章节正文/章纲。
- 删除自动字段注入：#1120 的 `build_page_field_note` 路由注入与 #1119 的 `build_genre_panel_note` 路由注入一并撤掉；只保留「当前页面/面板」身份行。
- 工具由 agent 自己决定何时调；不做宽 prime。触发条件写进工具描述与设定纪律：指代词没点名字段、要按现值改/补、问本页填没填全、写前字段不唯一。
- 题材字段复用 `genres/service.py::build_genre_truth_segments` 单源渲染；工具结果头标注「已保存值」与未保存提醒；值裁短、总预算 800 字。
- 前端零改动（原有 `thread/page` 已足够定位面板）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `assistant-tools`: 新增「当前设定页字段按需查询」要求（工具契约、触发/非触发、去重、结果契约）。
- `assistant-chat-ui`: 从「页面字段自动注入」改为「页面身份可注入、字段值只走工具」。

## Impact

- 后端：`assistant/page_context.py`（工具实现层）、`assistant/tools_settings.py`（注册）、`assistant/scopes.py`（域/纪律）、`assistant/router.py`（撤注入、ToolContext 带未保存标记）、`assistant/context.py`（撤 `build_genre_panel_note`）。
- 前端：无新增；`page_state` 恢复为只带未保存标记。
- 测试：工具单测、作用域、路由不再注入、旧自动注入测试移除。
