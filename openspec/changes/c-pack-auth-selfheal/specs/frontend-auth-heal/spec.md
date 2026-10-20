# frontend-auth-heal Delta — 静默自愈不得沿用过期令牌

## ADDED Requirements

### Requirement: 静默自愈不得沿用过期令牌

C端 静默自愈（`check-auth` 返回 code 0 且响应不含令牌时的本地令牌沿用分支）SHALL 在沿用前解析本地 JWT payload 并校验 `exp`：已过期、缺失 `exp` 或不可解析的令牌 SHALL 视为无效会话材料，SHALL NOT 原样沿用（2026-10-20 真机实锤：无条件沿用使用户完成浏览器重授权后仍无法自愈）。本地令牌无效时 SHALL 经 pair/exchange（本机配对密钥）换新令牌——换新成功 SHALL 落盘新令牌并刷新会话字段（与既有静默刷新同口径），后续写作能力同步钩子照常触发；换得令牌仍过期（S 端未重签过渡期）SHALL 照常落盘但不得视作自愈成功——认证类失败按写作能力弹窗既有失败面诚实呈现。S 端不可达（envelope code -1 或网络错误）SHALL 静默保留现态，等待下次自愈。pair/exchange 明确判败（配对失败，非不可达）时 SHALL 清空本地登录凭据（与既有失效清理全集同口径）并返回带**独立结构化标志（`pairing_broken`，与既有 `session_invalid` 区分）**的失效信号，附用户可读提示（登录状态需要重新验证；本地作品不受影响）；前端 SHALL 为该标志提供与 `session_invalid` 同语义的对称消费分支（清凭据、持久化提示、回登录页——本场景清凭据后本地无令牌，登录页静默自动登录不满足触发条件，无弹回问题）。以上清理与导航 MUST NOT 形成请求循环（与既有失效出口防循环语义一致）。

#### Scenario: 过期令牌经配对通道换新
- **WHEN** 本地 JWT 已过期、`check-auth` 返回 code 0 且该设备配对记录有效
- **THEN** 客户端经 pair/exchange 换得新令牌并落盘，界面保持登录态；写作能力同步随后自动恢复，全程无需用户操作

#### Scenario: 有效令牌不额外换新
- **WHEN** 本地 JWT `exp` 未到且 `check-auth` 返回 code 0
- **THEN** 沿用本地令牌，不发起 pair/exchange（避免无谓轮换与 S 端压力）

#### Scenario: S 端不可达静默保留
- **WHEN** 本地令牌已过期且 pair/exchange 因 S 端不可达返回 code -1
- **THEN** 本地凭据原样保留、无导航无弹扰，下次自愈按既有节奏重试

#### Scenario: 配对失败清凭据回登录页
- **WHEN** 本地令牌已过期且 pair/exchange 明确判败（配对失败）
- **THEN** 以 `pairing_broken` 标志清空本地登录凭据、回登录页并展示「登录状态需要重新验证；本地作品不受影响」类提示（与注销失效提示可分辨）；用户重新登录后一切功能恢复

#### Scenario: 重登信号不循环
- **WHEN** 配对失败信号反复到达（如停留在登录页期间自愈重跑）
- **THEN** 清理与导航行为幂等，不形成请求循环、无重挂风暴（与既有失效出口口径一致）
