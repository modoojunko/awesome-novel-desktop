# Tasks: entitlement-sync-prod-ddl

## 1. 预检

- [x] 1.1 生产 tiers 现状确认：无 entitlement 列、行清单（应为 pro/max 两行），验证：information_schema 查询输出在案

## 2. DDL 实施

- [x] 2.1 `ALTER TABLE tiers ADD COLUMN entitlement TEXT NOT NULL DEFAULT '{}'`，验证：语句执行成功、无长时间锁

## 3. 种子

- [x] 3.1 `UPDATE tiers SET entitlement='{...五 AI key, max_projects:null...}' WHERE key='pro'`，验证：UPDATE 影响 1 行

## 4. 验证（四道）

- [x] 4.1 列存在 + 默认值对拍：information_schema.columns 的 column_default == `'{}'`
- [x] 4.2 pro 行内容与 docs/contracts/entitlement-defaults.json pro 节点逐字对拍
- [x] 4.3 max 行仍为 '{}'（走 DEFAULTS 口径确认）
- [x] 4.4 JSON 可解析（python json.loads 通过）

## 5b. 执行实录（2026-09-07）

- 1.1 预检：information_schema 确认 8 列无 entitlement（对列查询 42703 报错即前置铁证）；行=pro/max 两行
- 2.1 ALTER 经 managePgDatabase execute 成功（classification=schema_change，2 行小表瞬时）
- 3.1 UPDATE rowCount=1（仅 pro）
- 4.x 四道验证全过（默认值 `'{ }'::text` / pro 与共享契约逐字一致 / max='{}' / JSON 可解析）
- 生产 S端 仍为旧代码：不读该列，行为零变化——下一棒 5.1 部署后才生效

## 5. 交接（范围外，勾给下一棒）

- [ ] 5.1 S端 部署（tag/dispatch；部署时 pg_gate 应绿——列已就位）
- [ ] 5.2 C端 打包发版（闭环必要条件）
