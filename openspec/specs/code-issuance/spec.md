## Purpose
发码运营通道：运营以本地脚本按批次生成短时套餐激活码（卡密），预算制约束发放总量，批次单据（三态）提供发放/激活/作废全程台账。发码面不在 S端 公网 API 上。

## Requirements


### Requirement: 发码面退出 S端 公网 API

S端 SHALL NOT 提供任何发码/查码管理端点（generate_code/query_codes 退役）；发码唯一路径为运营脚本直连数据库。激活码的兑换 SHALL 只依据码行自身状态（status=unused），与批次单据的发放记录解耦——兑换不校验、不回写批次台账。

#### Scenario: S端 无发码端点

- **WHEN** 任意调用方请求已退役的 `/api/generate_code` 或 `/api/query_codes`
- **THEN** 返回 404（路由不存在），码表不发生任何写入

#### Scenario: 兑换与单据解耦

- **WHEN** 用户兑换一枚码
- **THEN** 兑换结果只由码行状态决定，批次台账（code_batches/trade_events）不被兑换动作修改

### Requirement: 发码批次单据（三态台账）

每次发码 SHALL 生成一张批次单（code_batches：tier/duration_days/count/channel/note/created_by/budget_consumed/created_at），批内每枚码 SHALL 携带 batch_id，并 SHALL 记一条发放留痕事件（trade_events，payload 含本批全部码号）。批次码 SHALL 只有三种状态：未兑换（unused）、已激活（active）、已作废（revoked）；生成即视为发放，channel 字段即发放记录，MUST NOT 引入独立的「出库标记」动作。历史无批次的存量码归入「历史存量桶」口径，台账统计 SHALL 显式呈现该桶。

#### Scenario: 发一批码生成一张单

- **WHEN** 运营以 --tier pro --days 30 --count 10 --channel 「渠道A」 发码
- **THEN** 生成一张批次单（含渠道与天数）＋10 枚携带 batch_id 的 unused 码＋一条 codes.issued 留痕（payload 含 10 个码号）

#### Scenario: 单内三态统计与存量桶

- **WHEN** 运营查看某批次明细
- **THEN** 输出未兑换/已激活/已作废三态计数与明细；未指定批次的统计中，batch_id 为空的存量码单独列示，总数与码表对得上

### Requirement: 发码预算制

发码总量 SHALL 受预算约束：`global_config` 键 `codes.issue.budget`（剩余可发张数）为唯一额度事实源。发码 SHALL 按批原子占额——先插码、后以条件更新（CAS）扣减预算，扣减失败 SHALL 当场回收本批刚插入的码并整体失败；加预算 SHALL 是显式的运营动作。批次作废 MUST NOT 退回预算。台账 SHALL 保证对账不变式：单内 count＝budget_consumed＝该批实插码行数，每次查看批次时校验。

#### Scenario: 预算足够时发码成功

- **WHEN** 预算剩余 ≥ 申请张数，运营发一批码
- **THEN** 码行与批次单落库，预算按张数扣减，留痕事件写入

#### Scenario: 预算不足整批拒绝

- **WHEN** 预算剩余小于申请张数（或预算被并发改动致 CAS 失配）
- **THEN** 本批一枚码都不留下（已插入的当场回收），预算值不变，脚本明确报预算不足

#### Scenario: 作废不退预算

- **WHEN** 运营作废一批未兑换的码
- **THEN** 码转已作废，预算值不变（补发=显式加预算）

### Requirement: 档位取 tiers 表、时长显式（码行即合同）

发码档位 SHALL 对数据库 tiers 表校验（仅 status=live 的档位可发），MUST NOT 依赖代码内硬编码套餐字典；每枚码的时长 SHALL 以发码时显式指定的天数为准并落批次与码行（duration_days），兑换按码行天数起算。天数 SHALL 限 1–365，超出须显式越权参数（发码通道定位为短时套餐，年卡/永久走正式购买）。

#### Scenario: 档位校验与购买同源

- **WHEN** 运营以 tiers 表中不存在或非 live 的档位发码
- **THEN** 整批拒绝并提示可发档位清单，码表零写入

#### Scenario: 天数显式且受护栏

- **WHEN** 运营发码未指定天数，或指定天数 >365 且未带越权参数
- **THEN** 整批拒绝；指定 1–365 内天数时，批次与每枚码行写入该天数

### Requirement: 作废只对未兑换码

脚本作废 SHALL 只接受未兑换（unused）的码并 SHALL 记录作废原因；对已激活码的作废请求 MUST 拒绝（已激活权益的收回仅限系统链如账号注销，或人工数据库操作留痕）。

#### Scenario: 作废未兑换码留原因

- **WHEN** 运营作废一枚 unused 码并附原因
- **THEN** 该码转已作废、原因落库、批次明细三态随之更新

#### Scenario: 拒绝作废已激活码

- **WHEN** 运营对已激活码执行作废
- **THEN** 拒绝并说明该码已绑定用户；码行状态与用户权益不变
