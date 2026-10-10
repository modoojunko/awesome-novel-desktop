# c-carry-modal-reshow — 迁移完成后告知卡复弹根治（指纹数据件化＋清单零接触）

## Why

真机升级现场（v0.30.x → 测试同学实拍）：客户端升级后迁移正常完成，回到「我的作品」
告知卡（迁移上一版的作品与模型配置）再次弹出——且在这台机器上会**永远复弹**。

根因链（实勘钉死）：

1. 旧版库是 WAL 模式；旧版应用被安装器强杀（或哪怕干净退出——候选扫描自己会就地
   创建 `-shm`），盘上出现 `-wal`/`-shm` 边车。
2. `candidate_manifest`（告知卡「作品＋模型配置」两块清单）在**每次候选扫描**对
   recommended 候选就地主开只读连接——同文件 `probe_library`/`migration_probe` 早已
   实勘注明「只读连接会就地创建/改写 `-shm`」，本函数是漏网的违例。
3. 完成记录指纹 `candidate_stamp` ＝名字＋**三件套** max(mtime)＋体积，把 `-shm`
   算了进去。于是：完成时记的指纹 → 下一次扫描 `-shm` 被顶新 → 指纹永不相等 →
   `candidates` 的 `carried` 恒 false → 前端自动弹卡条件（`!carried && !suppressed`）
   每次进入书架都成立。

实证（本机 /tmp 复现）：子进程对带边车的 WAL 库开一次只读连接，`-shm` 的 sha256 与
mtime 即变；主文件与 `-wal` 全程稳定。

## What Changes

- **指纹数据件化**：`candidate_stamp` 只由数据件（主文件＋`-wal`）的 mtime/体积构成；
  `-shm`（读者会就地改写的临时索引）退出指纹与排序。无边车时新旧公式同串——干净
  退出的机器零迁移成本。
- **存量记录兼容对拍**：升级前写入的完成/抑制记录可能是旧三件套形态。扫描项带
  `stamp`（现行）＋`stamp_legacy`（旧形态）两串，完成态/抑制态按「任一命中即同一源」
  对拍；清理白名单在数据件未变时把旧形态记录换算成现行指纹。数据件变了两者都不命中，
  「dismiss 不吞新数据」不放宽。
- **只读清单零接触**：`candidate_manifest` 对 WAL 库一律走暂存复检（与
  `probe_library`/`migration_probe` 同口径）——顺手兑现「旧文件一个字不动」的卡面
  承诺：修复前告知卡扫描本身就会在用户数据目录里创建 `-shm` 文件。
- 前端零改动（`carried`/`suppressed` 两布尔语义不变，新增载荷字段前端不消费）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `db-generation`：「迁入候选与只读清单」——排序口径三件套→数据件（WAL 算数、
  `-shm` 不算）；新增身份指纹构成、存量记录兼容对拍、只读体检/清单零接触三条 SHALL
  与三个场景（边车漂移不破已迁移判定／只读清单零接触／旧形态完成记录兼容对拍）。

## Impact

- `client/backend/schema_version.py`（指纹函数族）、`client/backend/db_lifecycle.py`
  （扫描载荷＋manifest 暂存）、`client/backend/migration/router.py`（双形态对拍＋
  白名单换算）。
- 回归测试三针：带边车全链 start→done→漂移→carried 仍真；manifest 跨进程零接触；
  双形态对拍单测。修复前代码三针全红（回退基线自证）。
- 已被咬的机器装上修复版后**无需重迁**：旧形态 `migration.last` 按兼容规则命中，
  carried 立即为真、不再弹卡，清理入口照常可达。
