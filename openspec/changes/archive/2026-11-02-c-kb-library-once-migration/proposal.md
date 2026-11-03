# Proposal: c-kb-library-once-migration

## Why

c-kb-character-migration 批6 切了数据源（角色库 UI 读写 kb_entries、character_library 表 deprecated），但存量卡的迁移触发器没接线：

- `migrate_character_library` 端点（POST /api/kb/migrate-library）存在且幂等，但**前端零调用、boot 不跑**，唯一自动路径是备份恢复镜像（importer.py）。
- 实锤（2026-11-02 真机库）：老版本升级用户的 39 张卡全躺 `character_library`，`kb_entries` 0 行——知识库和角色库页面都看不见这批卡。

## What Changes

- 新增 `ensure_legacy_migrated(db, user_id)`：幂等自熄的一次性迁移入口（无 legacy 行 O(1) 点查即返；已迁移过按 migration 来源条目快路跳过；否则整账号迁移）。
- 两个库域读面挂点：知识库条目列表（GET /api/kb/entries）＋角色库卡列表（GET /api/character-library）——升级用户首次触达任一面即完成整账号迁移。
- 迁移失败不阻断读面（降级返回现有数据，下次触达重试）。

## 拍板（boss 2026-11-02）

**不挂 boot**。「这是老版本角色库到新版本迁移一次的事情」——一次性升级迁移，不是例行自愈；SHALL NOT 以常驻启动钩子形式运行（防后人好心改回 boot 挂钩）。

## Impact

- specs: knowledge-base（ADDED Requirement：角色库存量一次性迁移）
- 代码：kb/migrate_library.py（+ensure_legacy_migrated）、kb/router.py、library/service.py（各一处挂点）
- 测试：test_kb_migrate_library.py 增触达自迁／二次自熄／软删不复活／无存量零写／失败降级 五钉
