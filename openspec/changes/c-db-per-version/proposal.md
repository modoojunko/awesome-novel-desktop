## Why

库文件名现在承载的是**代数计数器**（`novel-v{SCHEMA_VERSION}.db`，`SCHEMA_VERSION = 1` → 用户机上恒为 `novel-v1.db`），与 C端 版本号毫无关系；由此派生出的两条分支——破坏性升代＝新库＋找回、加表加列（additive）＝**同一个库文件原地 ALTER 补列**——让「一次升级是怎么完成的」有两套语义。用户 2026-09-21 拍板要**单一方案**：库文件名＝C端 版本，每版首启新建自己的库，旧库只读留存、靠「找回」把书带过来，**不区分破坏性改字段与小改字段**。

additive 那条原地改的路还带着一个无守卫的洞：`ADDITIVE_COLUMNS` 靠人工登记，漏登记不报错，而「补列后刷新指纹戳」会把该库永久判成 current，此后**再发版修也救不回来**（指纹匹配→不再计算补列计划），只在业务用到该列时炸 `no such column`。单一方案让整条补列链退役，这个洞随之消失。

## What Changes

- **库文件名＝C端 版本**：`novel-v{app_version}.db`（如 `novel-v0.24.db`）；版本号沿用既有单一来源（打包期烘入的 `client_version`，`v*` 标签构建＝去前缀真实版本，PR/手动构建＝`dev`）。`SCHEMA_VERSION` 不再决定文件名。
- **形态钉死「拷贝前进」**：新版首启若自己的库不存在 → 建空库；**旧版库 SHALL NOT 被改名、写入或删除**（沿用迁入引擎「源只读、副本搬运、幂等」的既有语义）。回滚装回旧版即直接可用（它自己的库名还在），无「改名非原子／文件锁」问题。
- **`ADDITIVE_COLUMNS` 代内补列链退役**（再无就地 ALTER）；`tolerant` 超集放行退为不需要——新方案下不存在「同库跨 build」的形态。
- **候选与排序**：候选扫描按**白名单形状枚举**（语义化版本名、遗留全数字名、第 0 代 `novel.db`/`.legacy-*`、dev 哨兵、`.mismatch-*` 件），**禁止 `novel*` 前缀通配**（磁盘残件会被卷进来）；**活跃库按路径排除**，不靠版本比较判定「哪份是当前库」（版本相等 `0.24`/`0.24.0` 与全数字 tag `v1` 都不得让无主库不可达）；排序按版本语义逐段数值比较，**新于当前版本的候选列出但不推荐**，`recommended` 由后端单源给出；同族按三件套 `max(mtime)` 排序（只看主文件会被 WAL 滞后骗到）。`dev`/PR 构建使用**固定哨兵名**。
- **形状不符与损坏分流（不得让数据在产品内不可达）**：自己版本库存在但**可读而异形**（同 tag 重打包、删 tag 重打、dev 连续开发）→ 改名为 `novel-v{X}.db.mismatch-<stamp>` 并**作为候选可带回**；**不可读**才隔离为 `.corrupt-<stamp>`（不进候选，但在只读诊断面可见，该 UI 面本 change 一并做真）。空壳文件（0 表且无 `schema_id`）判 `fresh_boot` 复用，不积隔离件；隔离改名失败不抛异常（重试一次后给可展示状态）。
- **引擎快照与守卫**：暂存拷贝改「拷 `db`＋`-wal`（**不拷 `-shm`**）→ 暂存可写打开 → `wal_checkpoint(TRUNCATE)`＋`integrity_check`」（同一把钥匙同时修掉「WAL 头缺 `-shm` 被误判不可读」）；拷贝前后比对源三件套 `(size, mtime_ns)`，变化则重试一次、仍变化即拒绝并提示先关闭旧版本应用（防静默搬入陈旧快照）。
- **升级仪式口径**：空库首启且存在紧邻上一版候选时，走**一键（或首启自动）搬运＋结果提示**；五步向导保留给多候选／异常场景。用户可见文案从「救火·找回了丢的数据」改为「把上一版的作品带过来」。
- **旧库留存与清理**：默认**永不自动删**；新增**后端承载**的盘点/删除端点，硬约束＝只允许删「本次成功带回」的件（stamp 命中）、默认保留最近 2 份、路径过候选白名单＋`resolve()` 收敛在数据目录内＋非活跃库/非哨兵；部分失败（有书未带回）时不出清理入口；一键清理走既有 L2 盘点确认。
- **空书架空态并列两条出路**：「找回我的书」（本机旧版本数据）与「从备份包恢复」——换安装目录/换机的用户看不到任何候选，必须第二条出口可达（数据目录布局维持便携式，此为既定裁定，本 change 不做数据目录迁移）。
- **BOM（缩水保留）**：打包期 `release.json` 增 `components` 块（`db_filename`、`backup_format_version`，版本**显式传入**后 import 后端单源取值）；启动期把 C端 版本与组件快照写进库内 `app_meta`（键名钉死 `app_version`/`app_components`）→ 库文件被拷走或改名后仍可自证。
- **测试与演练**：`upgrade_drill` 全阶段改**单一库名派生辅助**取路径（并显式设 `CLIENT_VERSION`），`gen-bump` 改为 `version-chain`（覆盖 N-2 → N，摘要打印实际版本对）；新增版本升级验收用例矩阵（16 条，见 tasks §8）。
- **死面同批清理**：`legacy-db/status`（旧留档机制）与 `LoginPage` 消费点改指新候选端点或退役；`dismiss` 端点补路径校验。
- 顺手清理（#453 收编未尽）：`client/backend/main.py` 重复的 `apply_additive_columns` 调用块、其无人消费的 `ADDITIVE_COLUMNS`/`ADDITIVE_VOLUME_COLS` 副本，以及 `schema_version.py` 两个死常量。
- **Non-goals**：不迁移数据目录（便携式布局＝设计意图）；不改备份包格式契约；不改 S端 任何行为。

## Capabilities

### New Capabilities
<!-- 无：命名轴治理属既有 db-generation 能力的改写，不新立能力 -->

### Modified Capabilities
- `db-generation`: 命名轴由「代数计数器」改为「C端 版本」；首启状态机四态收敛（去 additive/tolerant）；候选扫描与排序改按版本；升级仪式（一键/自动搬运 + 文案口径）与旧库留存清理；转换器链与 gen-bump 演练改锚到版本跳；`SCHEMA_VERSION` 退役。
- `installer-release`: 打包期 `release.json` 的键集合新增 `components` 块（组件版本 BOM），CI 从单源读取并烘入产物；既有三键契约不变。

## Impact

- **后端（`client/backend`）**：`schema_version.py`（文件名派生改自版本）、`config.py`（`DATABASE_URL` 拼装）、`db_lifecycle.py`（命名解析/候选扫描/排序/`ADDITIVE_COLUMNS` 与 tolerant 退役）、`main.py`（lifespan 打戳段＋重复块清理）、`migration/engine.py`＋`router.py`（generation→version 语义、候选载荷）、`update_check.py`（复用其版本比较）、`tests/*`（`conftest.py` 测试库命名、`test_db_lifecycle`、`test_migration_engine`、`test_legacy_archive`）、`scripts/upgrade_drill.py`。
- **前端（`client/frontend`）**：`hooks/useLegacyDb.ts`（候选类型 `generation`/`schema_version` → 版本字段）、`components/LegacyMigrateModal.tsx`（文案口径与单候选一键路径）、`pages/NovelListPage.tsx`（首启空态出口行）、`components/AcctMenu.tsx`、`components/RestoreModal.tsx`（第二出口接线）。
- **打包/发布**：`.github/workflows/client-package.yml`（`release.json` 增 `components`）；`client/packaging/build/pywebview_app.py` 既有 `CLIENT_VERSION` 注入链不变；`installer.iss` 不动。
- **原型**：`docs/design-c/prototypes/list.html`（首启空态 `fr-note` 出口行）＋ `backup-restore.html`（屏 8 向导文案口径）＋ `ADJUSTMENTS.md` 登记。
- **规格前置**：`db-generation` 与 `backup-restore` 的 #453 delta 仍留在**未归档**的 `openspec/changes/c-db-generation-migration/`（`specs/` 里尚无 `db-generation`，`specs/backup-restore/spec.md` 仍是换代前措辞）→ 本 change 落地前的第一步是**先归档该 change**，本 change 的 delta 方能对齐到已落地的规格文本。
- **数据与兼容（存量形态已校正）**：**已发布客户端从未写过 `novel-v1.db`**——版本化命名需要 #453 的代码（2026-09-20 合入），而最后一个发布 tag 早于它；**线上存量形态是第 0 代 `novel.db`**。`novel-v1.db` 只出现在开发/内测栈（本机 `.docker-data/client/novel-v1.db`＝1213 本，`client/backend/data/novel.db`＝1 本）。两种形态都必须可带回，且**不得被版本比较误排除**（`1 > 0.25`）。无历史版本兼容包袱（无用户，2026-09-18 确认）。
- **平台差异（分开写）**：Windows 安装目录固定（`{autopf}\AI Novel`，安装器不删数据）→ 原地覆盖升级时数据原地；macOS 数据固定在 Application Support → 跨版本稳定。「每次升级带走一次」是版本命名的固有节奏，**与目录无关**；只有用户自己换了安装目录时才额外需要备份包往返。

## Design Impact

- **受影响端**：仅 C端（S端 无任何改动）。
- **受影响屏/弹层**：书架首启空态（出口行 `fr-note`）、找回向导 Modal（五步/四态）、控制中心「备份与恢复」行（徽标态）、账户菜单（回到「找回旧书」入口）、恢复导入弹窗（作为空态第二出口被唤起的路径）。
- **对象状态**：进度＝既有过程态；「已找回」＝pill `ok`；「待带回」＝pill `warn`（沿用既有）；语气词仅用 `info`/`ok`/`warn`/`err`，**不新增**第四种胶囊形态或 `.b`/`.strip` 形态。
- **共享段**：不触碰两端共享段（`base.css` 令牌与 `pill`/`notice`/`sk`/`panel`/`f-err` 家族）→ 无需 `design-cross`；C端 内部 `design:check` 照跑。
- **原型先行**：**需要**。`list.html` 首启空态出口行对齐 `backup-restore.html` 屏 4 既有的「有备份文件？从备份恢复 · 没有备份？查看找回办法」模式（把原本只在紧急态出现的双出口变成常驻），`backup-restore.html` 屏 8 向导文案由「找回」口径改为「把上一版的作品带过来」；逐条登记 `ADJUSTMENTS.md`。
- **设计工件产出方**：实现侧自查（复用既有原型模式与 `fr-note`/`link` 组件，不新造视觉，不需要设计侧会话）。
