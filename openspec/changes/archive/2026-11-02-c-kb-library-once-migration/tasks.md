# Tasks: c-kb-library-once-migration

## 1. 一次性迁移入口

- [x] 1.1 `kb/migrate_library.py` 新增 `ensure_legacy_migrated(db, user_id)`：无 legacy 行 O(1) 即返；有 migration 来源条目快路跳过；否则整账号 `migrate_character_library`；全程吞异常降级

## 2. 读面挂点

- [x] 2.1 `kb/router.py::list_entries_api` 挂 ensure（知识库条目列表）
- [x] 2.2 `library/service.py::list_cards` 挂 ensure（角色库卡列表）

## 3. 回归钉（test_kb_migrate_library.py）

- [x] 3.1 触达自迁：list_cards 首调即搬入，卡可见于角色库与知识库两端点
- [x] 3.2 二次自熄：再触达零写入零重复
- [x] 3.3 软删不复活：删掉的迁移卡在再触达后保持删除
- [x] 3.4 无存量零写：无 legacy 行账号点查即返，不产任何 kb 行
- [x] 3.5 失败降级：迁移抛错时读面照常返回、不 500

## 4. 验收与合入

- [x] 4.1 后端全量 pytest 绿＋ruff 绿
- [x] 4.2 openspec validate 绿
- [x] 4.3 真机验证：真机库快照副本实跑四点全过（39 卡首触达整账号回来/二次自熄/读面可见）；装新包后 UI 复核随验收
- [x] 4.4 sync＋归档随实现 PR 走
