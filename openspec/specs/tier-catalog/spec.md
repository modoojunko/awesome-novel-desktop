# tier-catalog Specification

## Purpose

档位目录的 C端 侧语义：缓存 S端 check-auth 下发的 `tier_catalog` 投影，作为权益快照缺失/不完整时的档位兜底（替代按档名写死的枚举）。S端 侧（tiers 表事实源／rank／投影下发）见 awesome-novel-server 仓。

## Requirements

### Requirement: C端 档位目录缓存兜底

C端 SHALL 缓存最近一次成功响应的 tier_catalog，作为快照缺失/不完整时的档位权益兜底（替代按档名写死的 STANDARD_FALLBACK 枚举）：无快照时按「本地 tier 在目录中匹配行」取 features/limits；目录与快照皆无时退免费基线。缓存随登出/换号失效（与权益快照同口径）。

#### Scenario: 无快照按目录兜底

- **WHEN** 本地无权益快照但缓存目录含 standard 行、本地 tier=standard
- **THEN** 兜底判定按目录 standard 行的 features 合成，标准档功能可用

#### Scenario: 目录快照皆无退免费

- **WHEN** 本地既无快照也无目录缓存
- **THEN** 判定退免费基线（features 空、max_projects=1），不因未知档名崩溃
