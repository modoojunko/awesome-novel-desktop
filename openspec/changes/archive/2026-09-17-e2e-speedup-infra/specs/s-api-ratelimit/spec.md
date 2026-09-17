# s-api-ratelimit 规格（新增能力 delta）

## ADDED Requirements

### Requirement: 登录限流阈值可配置
S端 对登录类敏感端点（`POST /api/web/login` 等认证入口）的 IP 限流阈值 SHALL 支持通过环境变量（`RATE_LIMIT_LOGIN_PER_MIN`）在进程启动时配置；环境变量缺省、为空或非法（非正整数）时 MUST 回落到默认值 30 次/60 秒/IP，与既有生产行为完全一致。

#### Scenario: 默认阈值不变
- **WHEN** 进程启动时未设置 `RATE_LIMIT_LOGIN_PER_MIN`
- **THEN** 同一 IP 在 60 秒窗口内对敏感端点的第 31 次 POST 收到 429（`{"code":2,"msg":"请求过于频繁，请稍后再试"}`），行为与现版本一致

#### Scenario: 测试栈注入高阈值
- **WHEN** 本地 docker 测试栈设置 `RATE_LIMIT_LOGIN_PER_MIN=600`
- **THEN** 同一 IP 60 秒内 100 次登录全部放行，不触发 429

#### Scenario: 非法值兜底
- **WHEN** `RATE_LIMIT_LOGIN_PER_MIN` 设置为 `abc`、`0` 或 `-5`
- **THEN** 阈值回落为默认 30，进程正常启动不崩溃

#### Scenario: 窗口语义不变
- **WHEN** 阈值无论取何值
- **THEN** 滑动窗口口径（60 秒）、仅命中 POST、仅匹配敏感路径清单、超限响应形状均与现版本一致
