# Design: entitlement-sync-prod-ddl

## Context

见 proposal。执行通道：本机 MCP `managePgDatabase`（execute 需 confirm=true）/ 控制台，与 #335 前的生产勘察同通道（queryPgDatabase 只读已验证连通）。

## Goals / Non-Goals

**Goals:** 生产 tiers 表具备新代码所需的 entitlement 列与 pro 种子，pg_gate 下一轮部署可直接通过。
**Non-Goals:** S端 部署、C端 发版（DDL 完成后另行拍板）；max 档种子（planned，留 '{}' 走 DEFAULTS）。

## Decisions

1. **DDL 先行于部署**（顺序铁律）：新代码 REQUIRED 登记 tiers.entitlement，pg_gate/启动自检缺列即拦；先加列对旧代码零影响（SELECT * 多一列无感）。
2. **单列 JSON + server_default '{}'**：与 #335 代码一致；PG11+ fast default 不触发表重写，tiers 仅 2 行，锁窗口毫秒级。
3. **种子只配 pro**：max 仍 planned，留空走 ENTITLEMENT_DEFAULTS（与 c-s-entitlement-sync §6.4 一致）；内容取自 docs/contracts/entitlement-defaults.json 的 pro 节点。
4. **验证四道**：information_schema 列存在 → 默认值 '{}' 对拍 → pro 行内容与共享 JSON 对拍 → JSON 可解析（python 侧）。

## Risks / Trade-offs

- [ALTER 失败/锁] → 表 2 行，毫秒级；失败即回滚无副作用
- [种子 JSON 手误] → 对拍测试同源文件逐字比对 + json.loads 验证
- [执行通道权限] → managePgDatabase execute 需 confirm=true；失败退控制台手工执行（SQL 已在 rollout 文档）

## Migration Plan

预检 → ALTER → 种子 → 四道验证 → 勾任务入库。回滚见 proposal。

## Open Questions

无。
