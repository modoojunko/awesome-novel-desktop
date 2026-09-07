# Proposal: entitlement-sync-prod-ddl

## Why

c-s-entitlement-sync（#335，已合 main 52746fc）的 S端 新代码读取 `tiers.entitlement` 列下发权益快照。生产 PG 尚无该列——pg_gate/启动自检的 REQUIRED 登记会在部署时拦截缺列。**DDL 必须先于 S端 部署执行**（发版口第一步）。本 change 把生产 DDL 实施的全过程立册跟踪。

## What Changes

- 生产 PG `tiers` 表加列：`entitlement TEXT NOT NULL DEFAULT '{}'`（PG11+ fast default，2 行小表瞬时完成，不锁业务）
- 种子：pro 档位权益配置一行 UPDATE（五 AI key + max_projects=null）；max 保持 `'{}'` 走代码 DEFAULTS
- 验证：列存在、默认值对拍、pro 内容对拍、JSON 可解析
- 明确不在本 change：S端 tag/dispatch 部署、C端 打包发版（DDL 完成后的下一棒，另行拍板）

## Capabilities

### New Capabilities

（无——纯运维变更，skip_specs: true；行为契约已随 c-s-entitlement-sync 入库）

### Modified Capabilities

（无）

## Impact

- 生产 PG（CloudBase）`tiers` 表：+1 列 +1 行 UPDATE
- 回滚：列保留无害（旧代码/新代码都容忍）；如坚持清理 `ALTER TABLE tiers DROP COLUMN entitlement`
- 风险：低——ADD COLUMN 带 DEFAULT 不重写表；UPDATE 仅 1 行
