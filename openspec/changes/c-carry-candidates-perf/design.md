## Context

真机实测（0.49.1，43 槽/1.16GB）：`candidates` 端点单次 1.7~3.3s 且在事件循环线程上同步执行；app.log 中多端点完成时刻毫秒级重合（排队指纹）。相关现状：

- `migration/router.py` 的 `candidates()`/`retention()` 在 `async def` 内直接调用同步的 `scan_migration_candidates`（db_lifecycle.py）——快路径仅 stat，慢路径是 43 次 sqlite 探活＋逐库全字节 sha256。
- `schema_version.py` 的 `candidate_stamp_hash` 只有**单槽**缓存（全局一个元组），多候选扫描形同无缓存；注释里的设计假设「最大候选 35MB」已被现实击穿一个量级。
- 每个槽的 `app_meta.migration.last` 记录「本槽由哪个源迁来」；`migration.history` 只在本槽内，**跨槽不可见**——现行 retention（`_migrated_stamps` 仅认 `migration.last`）在活跃槽里最多只能看到一个可删源，43 槽无法靠既有清理收敛。
- 线程池惯例：`update_check.py` 全线 `asyncio.to_thread`（含 sha256 复验），本仓已有先例。

## Goals / Non-Goals

**Goals:**

- 书架打开不再受候选盘点拖累：扫描期间其他请求照常响应。
- 数据件未变时重复盘点成本降到 stat 级。
- 给 43 槽这种历史积压一条**可逆**的收敛出路（归档不删除），保住「旧库只读留存/回滚/找回」承诺。
- 前端不再为「无待办」的快照反复拉取。

**Non-Goals:**

- 不放宽删除规则（待删清单仍仅限 `migration.last` 完整源）。
- 不做候选盘点的完全异步化重写（aiosqlite 化）——收益不成比例。
- 不为归档件提供恢复 UI（真机需要时手工移回 `data/` 即可，登记在文案与走查记录）。
- 不改迁移引擎六步与完整性判定本身。

## Decisions

**D1 扫描 offload＝`asyncio.to_thread`**（沿用 update_check 惯例）。备选：aiosqlite 全异步重写（侵入大、迁移端点全家都要动，弃）；只加缓存不 offload（首扫仍阻塞事件循环，弃）。范围：`candidates`/`retention` 两个盘点入口；`gaps`/`preview` 本就低频暂不动（后续可顺手）。

**D2 缓存＝按数据件身份的多槽 LRU＋锁**。键＝`(路径, 主文件 mtime_ns, size, -wal mtime_ns, size)`，值＝stamp_hash / probe 结果（书数、unreadable、chain 信息）；容量 64、`threading.Lock` 护读写（线程池并发安全）。命中语义与现行单槽缓存同一假设（mtime/size 未变＝字节未变），判定语义零变化。备选：持久化缓存（跨进程）——收益仅首启一次，不值得引入失效复杂度，弃。

**D3 链上溯源＝沿 `app_meta.migration.last` 回溯**。`trace_carry_chain(active)`：从活跃槽读 `migration.last.source_filename`（＋内嵌 report 完整性）→ 打开该源槽读**它自己的** `migration.last` → 逐跳回溯。槽 X 属「链上可归档」当且仅当：X 出现在链上、且从活跃槽到 X 的**每一跳**完整性「完整达成」（单源判定函数），且 X 的数据件三形态指纹对拍命中跳记录的 `source_stamp`（数据件被复写即断）。候选槽的 `migration.last` 读取与探活合并为同一次 ro 开库（进 D2 缓存）。

**D4 归档＝`shutil.move` 到 `data/archive/`，绝不删除**。扫描端天然排除：`scan_migration_candidates`/隔离/待删清单均只枚举数据目录**文件**（`iterdir` 过滤 `is_file`），子目录自动出局；`validate_candidate_filename` 因「文件名禁含路径分隔＋resolve 收敛在数据目录根」天然拒绝归档路径——端点侧再加「仅链上白名单」服务端收口。备选：直接删除（破坏回滚承诺，弃）；改扩展名软删（污染白名单形状解析，弃）。

**D5 前端降频＝carryStore 会话级「无待办」标记**。`refreshCarry({ auto })`：书架挂载传 `auto:true`——若上次快照无可搬运待办（无 `!carried && !suppressed` 的可读候选）则直接返回；`force`（账户入口、搬运终局回填、显式刷新）绕过并清标记。新进程＝新会话，升级换版不受影响。手放旧库文件这类旁路操作靠账户入口/重启发现，登记为已知边界。

**D6 整理入口＝LegacyMigrateModal 清理区扩为两出口**。快照里候选新增只读字段 `chain_carried`（是否链上可归档）；UI 归档列表读它（前端只展示，判定在后端——同一纪律）；「归档旧版数据」为主出口、「删除旧版数据」维持原状（retention 原清单＋原确认形态）。确认弹层复用既有二步确认结构＋「先备份一份」出口；按钮词动词（归档/删除），语气 warn。

## Risks / Trade-offs

- [链回溯逐槽开库的成本] → 与探活同次开库＋进 D2 缓存；仅 candidates 调用触发，offload 后不阻塞请求面。
- [源槽被复写导致链证据失真] → 每跳三形态指纹对拍，不命中即断链保守排除（少归档优于误归档）。
- [WAL mtime 被读者触碰造成缓存抖动] → 与现行单槽缓存同假设；抖动＝退化为重算一次，正确性不受影响。
- [回滚到旧版 App 后看不到归档槽] → 链上槽数据已完整在现行库，回滚后迁移卡走最新未归档源即可全量找回；边界登记进走查记录。
- [降频吞掉「手工放入旧库」的发现时机] → 账户入口挂载强制拉新＋重启兜底；登记为已知边界。
- [线程池并发扫描竞态] → 缓存加锁；扫描函数本身无共享可变态（纯读＋局部变量）。

## Migration Plan

PR → CI（后端 pytest＋前端 vitest/coverage＋design 门禁）→ 发版随灰度；真机走查顺序：装新版 → 记录 43 槽基线耗时（书架打开＋candidates 时延）→ 走整理入口归档链上槽（先「备份一份」）→ 复测耗时回亚秒级。回滚：旧版安装包对归档目录无感知（扫描天然跳过子目录），行为等同「候选变少」，无数据风险。

## Open Questions

（无）
