## Purpose

档位目录数据驱动：tiers 表是档位的唯一事实源（rank/entitlement/display_name/设备数/时长），S端 下发目录投影、C端 缓存兜底；销售侧一切变化（调档、加档、退役、试用时长、设备数）改库即生效，零代码。

## ADDED Requirements

### Requirement: 档位目录单一事实源

tiers 表 SHALL 是档位定义的唯一事实源，每行至少承载：`key`（档位键）、`rank`（等级序整数）、`display_name`（展示名）、`entitlement`（features/limits JSON）、`device_limit`、`duration_days`（试用类档时长）、`status`（live/planned/retired）。**BREAKING**：`server/app/config.py` 的 `TIER_POLICY` 代码表 SHALL 整体退役（device_limit/duration_days 升为 tiers 表列，代码仅保留 DB 不可用时已知档兜底常量）。

#### Scenario: 新增档位零代码

- **WHEN** 运营在 tiers 表插入一行新档位（key/rank/display_name/entitlement/device_limit/status=live）
- **THEN** S端 下发与判定链自动认识该档位（check-auth/目录/rank 比较），C端 经档位目录投影自动认识，无任何代码发布

#### Scenario: 试用时长改库生效

- **WHEN** 运营把 trial 行 duration_days 从 7 改为 30
- **THEN** 新注册用户的试用时长为 30 天，无代码发布（注册逻辑从行内取时长，散落文案随宣传物料同批人工核对）

### Requirement: 档位等级序以 DB 为源

tier 归属（已激活权益行中等级最高者）所依赖的 rank SHALL 从 tiers 表 `rank` 列读取；`server/app/domain/payments/pricing.py` 的 `_TIER_RANK` 代码常量 SHALL 退役为 DB 不可用时的已知档兜底。DB 缺某档 rank 行时 SHALL 显式告警而非静默归并为 none。

#### Scenario: standard 码正确归属

- **WHEN** 用户激活一张 standard 码（rank=15）且 tiers 表含该行
- **THEN** resolve_effective_tier 返回 standard（而非 none），check-auth 下发 tier=standard

#### Scenario: 缺行告警

- **WHEN** 权益行引用的档位键在 tiers 表无对应行
- **THEN** 归属计算记告警日志并按保守规则处理（不静默升档/清零）

### Requirement: S端 档位目录投影下发

check-auth（及 /api/pair/exchange）成功响应 SHALL 附带档位目录投影 `tier_catalog`：活跃档位（live/planned）每档的 `{key, rank, display_name, features}` 精简投影，供 C端 兜底判定与档位名渲染。投影体积 SHALL 受控（不含 retired 档与售卖字段）。

#### Scenario: 目录投影随快照下发

- **WHEN** check-auth 返回 code 0
- **THEN** 响应含 tier_catalog 数组，standard/pro/max/trial 各行含 rank 与 display_name

### Requirement: C端 档位目录缓存兜底

C端 SHALL 缓存最近一次成功响应的 tier_catalog，作为快照缺失/不完整时的档位权益兜底（替代按档名写死的 STANDARD_FALLBACK 枚举）：无快照时按「本地 tier 在目录中匹配行」取 features/limits；目录与快照皆无时退免费基线。缓存随登出/换号失效（与权益快照同口径）。

#### Scenario: 无快照按目录兜底

- **WHEN** 本地无权益快照但缓存目录含 standard 行、本地 tier=standard
- **THEN** 兜底判定按目录 standard 行的 features 合成，标准档功能可用

#### Scenario: 目录快照皆无退免费

- **WHEN** 本地既无快照也无目录缓存
- **THEN** 判定退免费基线（features 空、max_projects=1），不因未知档名崩溃
