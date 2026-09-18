# s-payments Specification (Delta)

## MODIFIED Requirements

### Requirement: 到货-激活两段式

支付确认后系统 SHALL 立即落权益台账行（codes，状态 pending_activation），用户 SHALL 在「我的套餐」点「激活」才开始计时（起点=当前最远到期日，顺延衔接）。未激活行不计时、不占设备额度、退款全额、永不过期。tier 归属 SHALL 按已激活行中等级最高者。台账行插入（支付发货与管理员发放两条路径）SHALL 显式写入 UTC 口径的 created_at，MUST NOT 依赖数据库列默认值求值时区（生产曾致上海本地时间裸值被按 UTC 读、比订单时间快 8h）；存量行的历史偏差不回填（无计算依赖，仅治理增量）。激活动作 SHALL 校验订单属主：请求的订单不属于当前登录用户时 MUST 按订单不存在处理（与存在性不可区分），MUST NOT 推进他人订单的台账行。

#### Scenario: 囤套餐

- **WHEN** 用户购买包年后选择"先存着"
- **THEN** 该行保持 pending_activation（不计时/不占额度）；用户随时可激活进入排队

#### Scenario: 发货台账行与订单时间同口径

- **WHEN** 支付回调完成发货插入台账行
- **THEN** 该行 created_at 与订单 paid_at 为同一 UTC 口径（秒级差），后续按北京时间展示两者一致

#### Scenario: 激活他人订单被拒

- **WHEN** 已登录用户以他人订单号请求 `POST /api/pay/codes/activate`
- **THEN** 返回与「订单不存在」一致的错误（不可区分存在性），他人台账行状态不变、不起算

#### Scenario: 属主正常激活不受影响

- **WHEN** 用户以自己的到货态订单请求激活
- **THEN** 台账行 pending_activation→active，起算与到期按既有顺延口径，响应字段不变
