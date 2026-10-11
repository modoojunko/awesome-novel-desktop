## ADDED Requirements

### Requirement: JSON 响应模式调用必须自证满足供应商前置约束

以 JSON 响应模式（response_format 为 json_object）向 OpenAI 兼容供应商发出的调用，其生效提示词——system 段与用户消息的合并全文——SHALL 含「json」字样（大小写不限）；不满足时 DeepSeek 等供应商以 400 invalid_request_error 整单拒收。该约束 SHALL 由提示词仓测试链的仓库不变量守卫强制：除显式登记的「成品文本类」例外名单（散文正文、提示词成品等非 JSON 输出模板）与注入片段资产外，一切对外调用模板剥除注释后的有效文本缺「json」字样即守卫失败并指名模板；例外名单的每次增删 SHALL 逐条有据并在变更 diff 中可审。例句提炼调用点另 SHALL 有行为钉：桩化客户端捕获实发提示词，断言含「json」字样且模板声明了 JSON 输出契约。

#### Scenario: 例句提炼不再被供应商拒收
- **WHEN** 用户在文风面板触发例句提炼且本书存在已归档章节
- **THEN** 实发请求的提示词含「json」字样，且模板给出 `{"lines": [...]}` 输出契约（1–3 条原文摘录）；供应商正常返回时端点解析 lines 并返回例句列表，不再出现 invalid_request_error

#### Scenario: 模板迁移丢失 json 字样时守卫拦截
- **WHEN** 任一例外名单外的调用模板，其剥除注释后的有效文本不再含「json」字样
- **THEN** 提示词仓守卫测试失败，报告指名该模板

#### Scenario: 新调用模板默认受守卫覆盖
- **WHEN** 提示词仓新增一个对外调用模板而未登记进例外名单
- **THEN** 该模板缺「json」字样时守卫测试失败——默认必须带 JSON 输出契约，豁免必须显式登记并有据
