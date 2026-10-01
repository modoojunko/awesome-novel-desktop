## ADDED Requirements

### Requirement: 激活码兑换

已登录用户 SHALL 能凭激活码字符串（管理端发放的 unused 码）直接开通对应档位权益：`POST /api/pay/codes/redeem`（body `{code}`），与订单激活（`/codes/activate` 只认订单号）互不替代。兑换 SHALL 按码行自带 tier 与 duration_days 起算，起点沿用既有顺延口径（该用户现有 active/frozen 行最远到期日与今天取大）；兑换成功 SHALL 写入 activated_at/grant_start/expires_at 并将码行转为 active，SHALL 记一条 trade event（`codes.redeemed`）留痕。兑换绑定 MUST 以「状态仍为 unused」为条件原子完成，同一码并发兑换/重复兑换 MUST 只成功一次。激活码不关联订单，MUST NOT 走退款路径。该端点属凭据校验类入口，MUST 纳入限流清单（与登录同桶按来源限速）。

#### Scenario: 兑换未用码成功

- **WHEN** 已登录用户以有效的 unused 激活码请求 `POST /api/pay/codes/redeem`
- **THEN** 该码行转为 active 并绑定当前用户，grant_start=顺延起点、expires_at=起点＋码行 duration_days，响应返回 `{code_id, tier, grant_start, expires_at}`
- **AND** 同一响应内 trade event 新增一条 `codes.redeemed`

#### Scenario: 顺延衔接既有套餐

- **WHEN** 用户名下已有生效中套餐（最远到期日 D）且 D 晚于今天，再兑换一枚码
- **THEN** 新行 grant_start=D、expires_at=D＋duration_days，不与既有套餐并行计时

#### Scenario: 重复兑换与并发双兑只成一次

- **WHEN** 同一枚码被兑换第二次（无论同账号还是他人、无论串行还是并发）
- **THEN** 仅第一次兑换生效；后续请求报「激活码已被使用」，码行归属与到期时间不被改写

#### Scenario: 无效码不可区分存在性细节

- **WHEN** 用户以不存在的码或格式非法的字符串请求兑换
- **THEN** 返回统一的「无效的激活码」错误，不泄露码表形态信息

#### Scenario: 未登录拒绝

- **WHEN** 未携带有效令牌请求兑换
- **THEN** 返回 `code=4001`（与既有支付端点同口径）

#### Scenario: 兑换行自动进入权益聚合

- **WHEN** 兑换成功后客户端请求 `GET /api/check-auth`
- **THEN** 聚合结果纳入该 active 行：effective_tier 至少为码行 tier，到期时间与剩余天数按兑换行计算

#### Scenario: 兑换端点限流

- **WHEN** 同一来源对兑换端点的请求超过限流阈值（凭据校验类同桶）
- **THEN** 超额请求被限流拒绝并留痕，防止激活码爆破
