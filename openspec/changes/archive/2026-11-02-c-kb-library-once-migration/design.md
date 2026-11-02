# Design: c-kb-library-once-migration

## 触发器选型（为何读面触达而非 boot / 迁移引擎）

| 方案 | 赢 | 输 | 判 |
|---|---|---|---|
| boot lifespan 钩子 | 全账号无差别覆盖 | **boss 拍板否**（一次性事情不该常驻）；每次启动都背 | ✗ |
| 迁移引擎（老库搬新库时） | 字面意义的「升级时刻」 | 引擎是 sync sqlite3 裸搬运，卡→payload 映射要重写一份；**已升级的机器（本次实锤机）窗口已过，覆盖不到** | ✗ |
| **读面触达自迁** | 一个机制覆盖未来升级者＋已升级者；不碰引擎不碰 boot；幂等自熄 | 读路径首次多一次写（可接受：幂等＋失败降级） | ✓ |

## 语义细节

- **快路判据**＝该账号存在 `src_kind="character_library_migration"` 条目 → 迁移恒整账号进行，见过条目即整账号完成。备份恢复带来的新 legacy 行不走本路径（importer.py 恢复链路本来就自调 `migrate_character_library` 镜像）。
- **软删不复活**：`migrate_character_library` 的 per-card 存在性检查不过滤 status——用户删掉的迁移卡（软删行仍在）天然跳过，不会因重跑而复活。
- **自熄**：character_library 表已停写（deprecated，仅迁移/备份恢复镜像写），存量只减不增；全部账号触达后各账号快路点查即返，永久 O(1)。
- **失败降级**：ensure 内部吞异常落 warning 日志；读面照常返回现有数据，下次触达重试（照 blob 迁移「失败不挡」先例，但触发点在读面非 boot）。
- **迁移提交语义**：`migrate_character_library` 末尾单次 commit，失败即整体回滚，无半迁移态。

## 挂点

1. `kb/router.py::list_entries_api`（GET /api/kb/entries）——知识库页条目列表（含角色设定页签）。
2. `library/service.py::list_cards`（GET /api/character-library）——角色库页卡列表。

两处都是账号级读面的最外层入口；organize/graph 等内部读直连 db 不挂（迁移完成后自然可见）。
