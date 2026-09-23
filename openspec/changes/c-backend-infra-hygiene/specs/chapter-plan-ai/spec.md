## ADDED Requirements

### Requirement: 非法卷引用必须 400

章域 AI 端点对 `vol_ref` 的解析 SHALL 显式校验：非法引用（非 `vol-{数字}` 形态）返回 400 与可读文案，MUST NOT 以未捕获 ValueError 形成未处理异常（500）。

#### Scenario: 非法 vol_ref 返回 400

- **WHEN** 以 `vol-abc`、空串等非法引用调用章域 AI 端点
- **THEN** 返回 400 与可读文案，服务端日志无未处理异常栈

#### Scenario: 合法引用行为不变

- **WHEN** 以合法 `vol-{N}` 引用调用同端点
- **THEN** 行为与既有口径一致
