# s-api-ratelimit Specification

## Purpose

S端 API 速率限制的容量口径：登录类敏感端点的 IP 限流保护，阈值可经环境变量按部署形态配置——生产保持默认容量防爆破，本地测试栈注入高容量吸收 e2e 登录突发。窗口语义、路径清单与响应形状不随配置变化。

## Requirements

### Requirement: 登录限流阈值可配置

S端 对登录类敏感端点（`POST /api/web/login` 等认证入口）的 IP 限流阈值 SHALL 支持通过环境变量（`RATE_LIMIT_LOGIN_PER_MIN`）在进程启动时配置；环境变量缺省、为空或非法（非正整数）时 MUST 回落到默认值 30 次/60 秒/IP，与既有生产行为完全一致。限流命中判定 SHALL 在路径归一化之后进行：剥 `/api` 前缀形态（如 `/web/login`）与带前缀形态（`/api/web/login`）SHALL 计入同一配额桶，MUST NOT 出现任一形态绕过限流。

#### Scenario: 默认阈值不变

- **WHEN** 进程启动时未设置 `RATE_LIMIT_LOGIN_PER_MIN`
- **THEN** 同一 IP 在 60 秒窗口内对敏感端点的第 31 次 POST 收到 429（`{"code":2,"msg":"请求过于频繁，请稍后再试"}`），行为与历史版本一致

#### Scenario: 测试栈注入高阈值

- **WHEN** 本地 docker 测试栈设置 `RATE_LIMIT_LOGIN_PER_MIN=600`
- **THEN** 同一 IP 60 秒内 100 次登录全部放行，不触发 429

#### Scenario: 非法值兜底

- **WHEN** `RATE_LIMIT_LOGIN_PER_MIN` 设置为 `abc`、`0` 或 `-5`
- **THEN** 阈值回落为默认 30，进程正常启动不崩溃

#### Scenario: 窗口语义不变

- **WHEN** 阈值无论取何值
- **THEN** 滑动窗口口径（60 秒）、仅命中 POST、超限响应形状均保持不变

#### Scenario: 剥前缀形态与带前缀形态同桶

- **WHEN** 同一 IP 先后以 `/api/web/login` 与 `/web/login` 两种路径形态各提交若干次登录
- **THEN** 两种形态合计计数，合并达到阈值后两种形态均收到 429；不存在任一形态无限放行

### Requirement: 敏感端点清单覆盖全部凭据入口

限流敏感路径清单 SHALL 覆盖全部凭据校验类端点：`/api/web/login`、`/api/web/register`、
`/api/authorize`、`/api/reset_password`（密保答案校验）、`/api/user/password`（旧密码校验）、
`/api/user/deletion`（密码二次确认）、`/api/user/deletion/revoke`（免令牌的密码校验）、
`/api/pair/exchange`（配对密钥校验）。上述清单外的新增凭据校验端点上线时 MUST 同步加入清单，
并 SHALL 有一条"路由 × 凭据校验"对拍测试防止再漏。清单匹配 SHALL 使用归一化后的路径
（补回 `/api` 前缀形态），MUST NOT 因调用方书写形态不同而漏网。

#### Scenario: 找回密码受限流保护

- **WHEN** 同一 IP 60 秒内对 `/api/reset_password` 提交超过阈值次数
- **THEN** 后续请求收到 429，密保答案无法被无限次猜测

#### Scenario: 免令牌密码端点受限流保护

- **WHEN** 同一 IP 60 秒内对 `/api/user/deletion/revoke` 提交超过阈值次数
- **THEN** 后续请求收到 429

#### Scenario: 注册受限流保护

- **WHEN** 同一 IP 60 秒内对 `/api/web/register` 提交超过阈值次数
- **THEN** 后续请求收到 429，无法被用于批量刷号或用户名枚举

#### Scenario: 配对交换受限流保护

- **WHEN** 同一 IP 60 秒内对 `/api/pair/exchange` 提交超过阈值次数
- **THEN** 后续请求收到 429，且合法客户端随后按正常节奏重试可成功（不得因一次 429 永久失效）
