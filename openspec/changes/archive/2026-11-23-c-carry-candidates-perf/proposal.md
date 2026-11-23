## Why

真机实锤（2026-11-22，0.49.1）：书架每次打开都触发 `GET /api/backup/db-migration/candidates`，该端点在**事件循环线程上同步**扫描数据目录全部历史库并逐库做内容哈希——本机积了 43 个槽共约 1.16GB，单次调用 1.7~3.3 秒，期间 `/api/novels`、`check-auth` 等全部请求被排队拖到 2~3.6 秒（app.log 中多端点完成时刻毫秒级重合为铁证）。且该成本随发版数线性增长（每版一个 80MB+ 槽），是慢性累积病；用户报障为「书列表打开明显卡顿」。

## What Changes

- **P0 后端·扫描去阻塞**：`candidates`/`retention` 等端点的候选扫描（`scan_migration_candidates`＋指纹＋探活）改为 `asyncio.to_thread` 执行，不再阻塞事件循环（沿用 `update_check.py` 的既有线程池惯例）。
- **P0 后端·指纹与探活多槽缓存**：`candidate_stamp_hash` 由**单槽**缓存改为按「路径＋主文件 mtime_ns/size＋wal mtime_ns/size」键的多槽 LRU 缓存（加上锁，适配线程池并发）；`probe_library` 的书数探活结果按同键缓存。缓存命中条件＝数据件字节未变（与现行单槽缓存同一假设），判定语义不变。
- **P1 后端·链上带回溯源＋旧槽归档**：扫描时沿各候选槽自身 `app_meta.migration.last` 回溯「迁移链」，标注哪些旧槽的数据已随链完整带到现行库（每跳完整性用既有单源判定）；新增**归档端点**把「链上且完整达成」的旧槽移入 `data/archive/`（移动而非删除，回滚/找回承诺不破）；归档件不再出现在候选/待删/隔离清单。清理（删除）规则不变，仍是仅 `migration.last` 可删。
- **P1 前端·整理入口**：`LegacyMigrateModal` 的清理区扩展为「整理旧版数据」：归档可清理件（复用既有列表＋二步确认形态，按钮词为动词）；删除入口维持原状。
- **P2 前端·候选快照降频**：`carryStore` 记住「快照无待办」（无未带回且未抑制的可搬运候选）态；书架挂载的自动刷新命中该态即跳过（会话级）；用户动作（账户菜单打开、搬运终局、强制刷新）照旧拉新。升级换版＝新进程＝新会话，不影响新候选发现。
- **真机清池**：随本版安装后，在受影响真机走查通过后执行一次归档，把 43 槽收敛到活跃槽＋链尾，验证书架打开耗时恢复亚秒级。

## Capabilities

### New Capabilities

（无——全部落在既有 `db-generation` capability 内）

### Modified Capabilities

- `db-generation`：
  - ADD「候选扫描不得阻塞请求面」：扫描/指纹/探活在 Worker 线程执行＋多槽缓存（字节未变即命中，语义不变）。
  - ADD「链上带回溯源与旧槽归档」：沿槽 `app_meta.migration.last` 回溯标注链上带回态；归档端点只收「链上且完整达成」的槽；归档＝移动到 `data/archive/` 不删除；归档件退出候选/待删/隔离清单；链外件（从未带回的源，如 dev 槽）SHALL NOT 归档。
  - MODIFIED「清理候选必须通过完整性校验」：「完整达成」单源判定的消费面从三处扩到四处（新增链上归档白名单逐跳消费）；删除规则不放宽（更早源仍不可删，退出盘点走归档）。
  - ADD「候选快照按需刷新」：前端会话内快照无待办时，挂载自动刷新可跳过；用户动作与搬运终局强制拉新。

## Impact

- 后端：`client/backend/migration/router.py`（candidates/retention/新 archive 端点）、`client/backend/db_lifecycle.py`（`scan_migration_candidates` 链上标注、归档目录跳过）、`client/backend/schema_version.py`（`candidate_stamp_hash` 多槽缓存＋锁）。
- 前端：`client/frontend/src/lib/carryStore.ts`（降频＋归档动作）、`client/frontend/src/hooks/useLegacyDb.ts`（薄壳透传）、`client/frontend/src/components/LegacyMigrateModal.tsx`（整理区）。
- 无数据库 schema 变更；`data/archive/` 为新增目录约定，无迁移。
- 性能验收：本机 43 槽场景下 `/api/novels` 与 `candidates` 并发不再出现排队拖长；重复拉取 candidates 命中缓存后呈毫秒级。

## Design Impact

- 受影响端：**C端 only**（S端无迁移弹层）。
- 受影响屏/弹层：`LegacyMigrateModal`（书架迁移弹层）清理区——由「清理旧版数据」扩展为「整理旧版数据」（归档＋删除两出口），复用既有列表、确认弹层与按钮形态，无新增组件形态。
- 对象状态：新增数据态「已归档」（不出现在任何清单，无界面态）；界面语气词沿用 info/warn，不新增档位。
- 共享段：不触碰（改动限于业务弹层与 store，无 base.css/语义类变更）。
- 原型先行：需要——`docs/design-c/prototypes/upgrade-carry.html` 增补整理区两出口形态＋`ADJUSTMENTS.md` 登记；由实现侧自查产出（复用既有组件词汇，无新形态）。
- 文案：遵循 §13（按钮动词：「归档」「删除」；不出现内部术语）。
