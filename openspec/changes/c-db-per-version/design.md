## Context

见 `proposal.md` 的 Why。设计上真正要吃住的现状事实（逐处实测；**评审已校正两处事实**）：

- 库文件名由 `client/backend/schema_version.py` 的 `SCHEMA_VERSION` 派生，`config.py` 拼 `DATABASE_URL`；`db_lifecycle.generation_of()` 用 `^novel-v(\d+)\.db$` 解析代数，`scan_migration_candidates()` 以「代数 < 当前」入选、代数降序＋mtime 降序排序，且以 `data_root.glob("novel*")` **前缀通配**取文件。
- `boot_lifecycle()` 四态（current/additive/tolerant/quarantined）；`quarantine_corrupt()` 逐件 `replace` 且无异常保护，`main.py` 调用处无 try。
- 迁入引擎（`migration/engine.py`）六步齐备：第 1 步**逐件 `copy2` db/-wal/-shm**，第 2 步在**副本**上 checkpoint+integrity_check；源只读、单事务、中断幂等。`migration/` 下**没有** `converters/`。`migration-staging/` 只在 `finally` 里 rmtree。
- 只读探针（`inspect_library` 的 `mode=ro`）**打不开「WAL 模式头 + 缺 `-shm`」的库**（本机实测 `.docker-data/client/novel.db.recovered-20260917-052608` 被误判不可读，拷到可写环境 checkpoint 后 integrity_check=ok、1 本书）。
- 版本比较实现在 `update_check.py`（`_VERSION_RE = ^\d+(\.\d+)*$` ＋ 逐段数值比较），**非纯数字段抛 ValueError**，`get_update_state` 调用处无 try（装 `v0.24-rc1` 的包点更新即 500）。
- **已发布客户端从未写过 `novel-v1.db`**：`novel-v1.db` 需要 #453 的代码（2026-09-20 合入），而最后一个发布 tag 早于它 → 存量形态是**第 0 代 `novel.db`**（本机 `client/backend/data/novel.db`＝1 本、无 `novels` 表；开发栈 `.docker-data/client/novel-v1.db`＝1213 本＝dev 形态）。
- `docker-compose.yml` 的 client-backend **不注入 `CLIENT_VERSION`** → 容器/ e2e 栈在新语义下是 dev 哨兵。
- 前端 `useLegacyDb.ts` 读 `generation`/`schema_version`；`NovelListPage.tsx` 首启出口行**条件渲染**；`quarantined` 字段**全前端无渲染点**（诊断面是空的）；前端无 ConfirmGuard（前序 change 声称的清理 UI 从未落地）。
- 规格文本仍在**未归档**的 `c-db-generation-migration`（`openspec validate` 实测：目标 spec 不存在，归档会拒绝 MODIFIED/RENAMED）。

## Goals / Non-Goals

**Goals**

- 库文件身份与 C端 版本一一对应；升级只有一条路径（新库＋带回），回滚无代价（旧库原位）。
- 消掉「就地 ALTER 用户唯一正本」这条路径，并消掉随之而来的无守卫登记洞。
- 任何形态的存量数据（第 0 代、遗留代数名、同名不同构建、损坏件）在产品内**都有可达路径或只读可见**，不存在静默不可达。

**Non-Goals**

- 不做数据目录迁移（便携式布局为既定裁定）；不改备份包格式契约；不给 S端 任何改动；不预造版本间语义转换器；不做「自动删除旧库」。

## Decisions

**D1 · 库名派生单源留在后端叶子模块；BOM 只作断言锚。** `schema_version.py` 改为：`app_version()`、`db_filename_for(version)`、`parse_db_filename(name)`（返回带 kind 的判别结果：semver / legacy-generation / gen0 / sentinel / mismatch / 非候选）、`version_sort_key(version)`。运行时真源是后端模块；`release.json.components.db_filename` 由 CI **显式传入版本**后 import 同一模块取值（用 env 推断会自检同源同错），且 **MUST NOT** 进 `RELEASE_OVERRIDE_KEYS`。
替代：运行时读 `release.json`（否决：dev/源码运行没有该文件，会出现两套真源）。

**D2 · dev 哨兵名 `novel-dev.db`，垫底列出。** dev/PR 构建无版本语义：哨兵**自身**不入候选（按路径排除＝它是活跃库）；**别人写的哨兵**（release.json 被清理、装了 PR 包）垫底列出且永不进推荐位——否则该库在产品内零入口（列表呈现只有时间+计数，不泄露文件名）。dev 构建不做「新于当前」的推荐门槛（无版本语义），但仍排除活跃库路径。
替代：dev 当 `0.0.0` 参与比较（否决：把全部 release 库判成更新）；哨兵彻底不入候选（否决：见上）。

**D3 · 遗留代数名显式白名单 + 活跃库按路径排除。** 全数字名（`novel-v1.db`）在版本比较下是 `1 > 0.25`，按「≥ 当前不收」会被**静默排除**（拍板人本机 1213 本、开发栈 35 MB 都在这个形态里）。故：`parse_db_filename` 把全数字名识别为**遗留代际**（第 0 代之上、任何语义化版本之下）。**并且**：候选集合一律以**活跃库路径**（`DATABASE_URL` 解析结果）排除自身，SHALL NOT 用版本比较判定「哪份是当前库」——否则版本相等（`0.24` vs `0.24.0`）与全数字 tag（`v1`）会各制造一类不可达。
替代：把 `novel-v1.db` 当版本 `0.1`（否决：与 `0.1` 版本的库名同空间）；靠版本比较排除当前库（否决：两类不可达）。

**D4 · 首启状态机三态 + 「形状不符」与「不可读」分流。**
- `current`（指纹匹配）/ `fresh_boot`（不存在，或存在但 0 表且无 `schema_id`）/ 分流改名。
- **可读但指纹不符** → `novel-v{X}.db.mismatch-<stamp>` 且**进候选**（列交集搬运能带回其内容；这是同 tag 重打包、删 tag 重打、dev 连续开发三种事故的唯一出口）。
- **不可读** → `.corrupt-<stamp>` 隔离，不进候选，但**只读诊断面可见**（P1-7 的 UI 面必须真做，否则这句是空的）。
- **迁移前先尽力 `wal_checkpoint(TRUNCATE)`** 把 WAL 落进主文件（失败不阻断）→ 主文件一次 `replace` 为 `novel-v{X}.db.{mismatch|corrupt}-<stamp>`，边车随后同前缀改名（内容已在主文件，边车失败不丢已提交数据）。失败重试一次后记日志并返回可展示状态，**不抛到 lifespan**；形态与 `parse_db_filename` 白名单一致（旧版留下的单文件隔离件同样可识别、可在只读面列出）。
替代：保留 tolerant 放行同名超集（否决：让「指纹不符必须分流」这条可测断言失效）；新旧一律隔离（否决：制造 P0 静默不可达）。

**D5 · 搬运的常态入口 = 单次确认，且「紧邻上一版」覆盖遗留族。** 单候选（含唯一一份遗留代数名/第 0 代）→ 空态出口行一次确认；多候选/非相邻/异常 → 五步向导。搬运期间锁写入口（复用 locked 态）。替代：首启全自动（否决：用户对数据去哪没有认知与选择权）。

**D6 · 候选白名单按形状枚举、推荐位由后端给。** 形状＝`novel-v{semver}.db`／`novel-v{纯数字}.db`／恰为 `novel.db`／`novel.db.legacy-*`／`novel-dev.db`／`novel-v{X}.db.mismatch-*`。**禁止** `novel*` 前缀通配（本机真实存在 `.e2e-*`/`.fresh-*`/`.recovered-*`/`novels.db` 等残件会被卷进来）。排序：semver 降序（逐段数值）→ 遗留数字降序 → 第 0 代 → 哨兵；同族内按**三件套 `max(mtime)`** 降序（WAL 会让主文件 mtime 滞后 11 小时量级）。`recommended`＝第一个**不新于当前版本**的候选，由后端单源给出，前端不得按列表序猜。**新于当前版本的候选列出但不推荐**（不再排除——排除会让它们彻底不可达）。
替代：前端算推荐（否决：产品语义必须单源）；按版本过滤排除（否决：D3 的两类不可达）。

**D7 · 引擎第 1/2 步改「拷 db＋-wal → 暂存可写 checkpoint」＋拷贝一致性守卫。**
- **不拷 `-shm`**（SQLite 明确不建议；易失共享内存索引）。拷 db 与 `-wal` 后在暂存上可写打开 → 自动重建 `-shm` → `wal_checkpoint(TRUNCATE)` → 这一步同时让「WAL 模式头但缺 `-shm`」的库可被打开（同一把钥匙同时修掉只读探针误判）。
- **一致性守卫**：拷贝前后快照源三件套 `(size, mtime_ns)`；变化则重试一次，仍变化则拒绝搬运并提示「请先关闭旧版本应用」——这是唯一一条会**静默搬入陈旧快照**的路径（源在跑，自动 checkpoint 与拷贝交错）。
- 体检（候选扫描/precheck）与引擎同口径：只读打不开时先落暂存复检，再判可读性。
替代：`VACUUM INTO` 只读快照（暂缓：只读连接在 WAL 模式仍需 `-shm`，且需另建一套体检口径；现方案的守卫已能识别竞态）。

**D8 · app_meta 版本戳 + 组件快照（键名在此钉死）。** 键：`app_version`（字符串）＋`app_components`（JSON：`{"db_filename": …, "backup_format_version": …}`）。写入时机：首启（含 `current`/`fresh_boot`）、搬运收尾；版本不同则按「最后写入方」刷新。**只写当前库**。

**D9 · 清理＝新端点，且只允许删「本次成功带回」的件。** `GET /backup/db-migration/retention`（待删清单）＋`POST …/cleanup`（执行）。硬约束：仅 `stamp == migration.last.source_stamp`；路径过 D6 白名单＋`resolve()` 收敛在数据目录内＋非活跃库＋非哨兵；默认保留最近 2（三件套 max mtime）；无用户动作永不删；部分失败不出清理入口。**中间件/路由层的路径拼装 SHALL 复用候选校验函数**（`dismiss` 现有实现直接 `DATA_ROOT / filename`，无校验，本次一并收紧）。
替代：把清理段从本 change 删除（否决：用户已拍板要「保留最近 N＋一键清理」，且不做则磁盘随版本线性增长无出口）。

**D10 · 版本比较：全域全序、永不抛异常、单一实现。** 把 `update_check` 的比较抽为共享叶子实现（`app_version()` 委托它，`update_check` 反向 import，避免两份漂移）：数值段逐段比较；同前缀「**有后缀 < 无后缀**」（`0.24-rc1 < 0.24`，预发布早于正式版——更新检测靠它不误报）；后缀按 `-`/`_`/`.` 分段、数字段 < 字母段；非法串降最低且**不抛**；调用点（含更新检测）一律不抛（既有 `0.11-beta` 抛 ValueError 的用例随本次改判为「合法输入，比较得确定序」）。CI 增断言：tag 清洗后 SHALL 匹配 `^[0-9]+(\.[0-9]+)+([-._][A-Za-z0-9._-]+)?$` 且 **MUST NOT 为纯数字**（纯数字 tag 会与遗留代数名同形）。

**D11 · 落地前置：先归档 `c-db-generation-migration`**（工具已实测拒绝 MODIFIED/RENAMED），归档后手改 `specs/db-generation/spec.md` 的 Purpose 段（代数→版本）。

**D12 · 死面处理（本 change 同批）。** `backup/router.py` 的 `legacy-db/status`（扫 `.legacy-*` 的旧留档机制）与 `LoginPage.tsx` 的消费点：改为指向新候选端点（或退役并删消费），SHALL NOT 留一个恒 `present:false` 的死面。`legacy_archive.py` 薄层保留（`backup/router.py` 仍 import），但不得再被新代码依赖。

**D13 · e2e/parity 与 dev 栈的库形态。** `docker-compose.yml` 的 client-backend 不注入 `CLIENT_VERSION` → 新语义下是 dev 哨兵，且 volume 指向 `.docker-data/client`（含 1213 本真实数据与十余份历史件）。e2e/parity 门禁 SHALL 用**干净的会话私有 DATA_ROOT**（或令候选 suppressed），否则候选语义一变，parity 基线与书架断言会漂。

## Risks / Trade-offs

- [每版一次搬运会被当成麻烦] → 常态压到一次点击（D5）＋「带回」文案；空态开口常驻，不做弹窗打断。
- [用户不点搬运就在新库写作] → `INSERT OR IGNORE` ＋「同 PK 当前库获胜」保证幂等合并；清理确认里明写「已带回的内容不受影响」。
- [磁盘随版本线性增长] → D9 保留 2＋手动清理；「不自动删」红线优先于省空间。
- [遗留/相等/纯数字版本造成不可达] → D3 路径排除＋D6 列出但不推荐；专项断言（UP-03/UP-15）。
- [源在跑导致旧快照] → D7 一致性守卫（重试一次后拒绝并给可读原因）。
- [隔离改名被文件锁挡] → D4 checkpoint 先行＋目录级移动＋重试＋不抛异常；退化为「原文件原位 + 可展示状态」。
- [dev 被隔离一次] → 仅影响本地开发（哨兵名下改 schema）；`DATA_ROOT` 可绕，写进 dev 说明。
- [换安装目录扫不到候选] → 空态第二出口「从备份包恢复」恒在；文档写明「老版本导出→新版导入」与「把旧 `data\` 拷进新安装目录」两条人工路径（后者产生的「WAL 头 + 缺 -shm」形态由 D7 的口径兜住）。
- [同 tag 重打包造成同版本异形状] → D4 的 `.mismatch-*` 可带回 + `app_meta` 记版本；`schema_fingerprint` 进 BOM 暂缓（`.mismatch` 件本身就是事故信号）。

## Migration Plan

1. **归档 `c-db-generation-migration`**（D11）——本 change 的 delta 才有可对齐的规格文本。
2. 后端：命名单源与比较（D1/D10）→ 三态与分流（D4）→ 候选白名单/排序/推荐（D2/D3/D6）→ 引擎快照与守卫（D7）→ `app_meta` 版本戳（D8）→ 清理端点（D9）→ 死面（D12）→ 测试与 drill（version-chain，全阶段命名单源）。
3. 前端：候选类型、空态双出口（常态一键 + 备份包恢复）、向导与结果页文案「带回」、清理清单两态、隔离件只读清单。
4. 打包：`components`（显式传版本）＋冒烟正/负例。
5. 原型与登记：`list.html` 出口行、`backup-restore.html` 屏 8 文案、`ADJUSTMENTS.md`。
6. 门禁：pytest / vitest / tsc / design:lint / design:check / e2e（**用干净 DATA_ROOT**，D13）/ drill / 反断言；证据落 `openspec/changes/c-db-per-version/evidence/`。

**首个新版本（如 v0.25）会让所有存量用户走一次「把上一版的作品带过来」——这是设计意图，发布说明必须写明**（旧文件原位保留、可随时装回旧版本）。平台差异要分开写：Windows 安装目录固定（`{autopf}\AI Novel`，安装器不删数据）→ 原地覆盖升级时数据原地；macOS 数据固定在 Application Support → 跨版本稳定。

回滚策略：本 change 不改写任何既有库文件，回滚＝装回旧版本继续用自己的库；新版本期间写入留在新库文件里（同目录可见、可再带回）。

## Open Questions

- 无（评审提出的版本串细则已在 D10 定死为「全域全序、永不抛」，不需要实施期再定）。
