# db-generation Specification

## Purpose
C端 SQLite 库文件**版本治理**：库文件名＝C端 版本（每版首启新建自己的库、旧库只读留存），首启状态机（current / fresh_boot / 形状不符分流 / 损坏隔离）、旧库迁入引擎（副本列交集搬运、源只读、一致性守卫、幂等）、候选与版本门禁（白名单形状＋活跃库按路径排除＋推荐位单源）、旧库留存与清理（只删已成功带回的件）、跨版本转换器链纪律——使升级、回滚、找回在任何组合下数据无损。

## Requirements

### Requirement: 旧库迁入引擎（六步＋预检）

- 迁入 SHALL 依序执行：**第 0 步预检**（磁盘可用≥源体积×2、暂存目录与目标同卷、候选≠当前活跃库）→ 拷贝 `db` 与 `-wal`（**SHALL NOT 拷 `-shm`**——它是易失共享内存索引；源文件此后零接触，含不做 checkpoint）→ 副本上 `wal_checkpoint(TRUNCATE)`＋`integrity_check`（这一步同时构成体检口径：只读打不开的形态先落到暂存再可写打开复检）→ 列交集计划（目标存在 NOT NULL 无默认无回填列的表整表跳过并在预览预告）→ ATTACH 只读副本逐表 `INSERT OR IGNORE`（连接 FK 保持 OFF；`app_meta` 永不搬；预置种子表靠 PK 幂等）→ `foreign_key_check` 只报不删＋书计数对拍 → 写 `migration.source_filename/source_stamp/finished_at`＋删暂存。
- **拷贝一致性守卫**：拷贝前后 SHALL 快照源三件套的 `(size, mtime_ns)`；期间发生变化 SHALL 重试一次，仍变化 SHALL 拒绝搬运并给出可读原因（引导先关闭旧版本应用）——SHALL NOT 静默搬入陈旧快照。
- 迁入 SHALL 幂等：中断（断电/杀进程/用户关闭）后重跑 SHALL 零重复行、源文件无损；重跑经 stamp 与完成记录比对识别「上次已带回」。
- 迁入报告 SHALL 为 v:1 版本化结构且 preview 与 result 同构（skipped/fk_violations 为明细列表非计数；含 `book_count_source`/`book_count_migrated` 可交叉核对，字段名沿用既有前端消费方）；报告与候选载荷中标识来源的字段 SHALL 用版本语义，SHALL NOT 再用代数计数。
- 迁入收尾 SHALL 把 C端 版本写入目标库 `app_meta`（`app_version` ＋ `app_components` 组件快照），使库文件被拷走或改名后仍可自证来源版本。
- 迁入端点全家 SHALL 免登录（复用 loginless-data-exit 防护面）；与导出/下载经 job_runner 跨 kind 单飞互斥。**搬运进行期间 SHALL 锁住书架写入口**（复用向导的 locked 态），避免同库并发写触发 503。
- **版本门禁**：设定存于盘上 yaml 的前 ADR 世代库（按 schema 体检判定，不依赖文件名）SHALL NOT 进入行级迁入，向导 SHALL 引导走资产包导入通道。
- 启动或候选扫描时 SHALL 清理**非本次会话**的 `migration-staging/*` 残留（硬杀/断电遗留的整份副本）。

#### Scenario: 源数据只读

- **WHEN** 迁入全程完成或中途失败
- **THEN** 源库三件套（db/-wal/-shm）字节与 mtime 均不变（不含被确认清理的 `migration-staging`）

#### Scenario: 中断重跑幂等

- **WHEN** 迁入进行到第 4 步某表时进程被杀，用户重开向导再迁
- **THEN** 重跑完成且全库零重复行；预览将已入表行标「上次已带回」默认不勾

#### Scenario: 不可迁世代引走

- **WHEN** 候选为前 ADR 世代旧库（设定在盘上 yaml）
- **THEN** 向导不提供一键搬运，明示走「备份包导入」通道

#### Scenario: 源在搬运中被写入

- **WHEN** 旧版本应用仍在运行并持续写入源库（WAL 自动 checkpoint 与拷贝交错）
- **THEN** 拷贝前后快照检测到变化 → 重试一次 → 仍变化则拒绝并提示先关闭旧版本应用；SHALL NOT 返回「成功但少若干次提交」的报告

### Requirement: 迁入候选与找回向导

- **候选白名单 SHALL 按形状枚举**（不得用 `novel*` 前缀通配）：`novel-v{语义化版本}.db`、`novel-v{全数字}.db`（遗留代数名）、恰为 `novel.db`、`novel.db.legacy-*`、dev 哨兵名、`novel-v{X}.db.mismatch-*`。其余磁盘残件（如 `novel.db.e2e-*`、`novel.db.fresh-*`、`novel.db.recovered-*`、`novels.db`、`migration-staging/*`）SHALL NOT 进候选。
- 候选 SHALL 排除：当前活跃库路径、`-wal`/`-shm` 边车、`.bak*`、`.corrupt*`、book_count=0 的空库、无 `schema_id` 的空壳。
- 每候选只读体检（书数/卷章/字数/可读性/最后使用时间）；**只读打不开**的候选 SHALL 走暂存复检口径（拷 db＋wal 到暂存→可写打开→checkpoint→读计数）后再判定可读性，SHALL NOT 因「WAL 模式头但缺 `-shm`」把可救的库判成不可读。
- **排序与推荐**：语义化版本按**逐段数值比较**降序（`0.9 < 0.10`；禁用字符串字典序；非法版本串降最低且 SHALL NOT 抛异常）→ 遗留代数名按数字降序 → 第 0 代族 → dev 哨兵垫底；同族内按**三件套 `max(mtime)`** 降序（SHALL NOT 只看主文件 mtime——WAL 会让主文件 mtime 滞后）。**`recommended` SHALL 由后端单源给出**（第一个不新于当前版本的候选），前端 SHALL NOT 用列表顺序推断推荐。
- 版本**新于**当前版本的候选 SHALL 列出但 MUST NOT 被推荐（用版本比较排除会让这些库彻底不可达：`0.24` 与 `0.24.0` 相等、遗留全数字名与 tag `v1` 同形）。
- **升级仪式**：空库首启且存在可搬运候选时，常态为**单次确认**完成搬运（首启自动执行＋结果回声亦合规）；**「紧邻上一版」的定义 SHALL 覆盖遗留族**——当不存在任何版本命名候选时，唯一一份遗留代数名/第 0 代候选即视为紧邻上一版，走单次确认。五步向导 SHALL 保留给多候选、非相邻版本与异常场景。
- 向导五步（多候选/异常路径）：发现（首答「没有丢失——在这台电脑上找到了旧版作品」＋计数）→多候选选择（仅 >1 份时；按时间+计数呈现并标「推荐」，**不出文件路径/版本号**）→预览（逐书字数核对；重名行内预告《书名（旧版）》；缺列/整表跳过预告）→进度（locked）→结果（hero「已带回 N 本书」＋与预览同源计数；部分成功=成功主叙事+失败行「重试这本书」；全部失败=回滚声明「这次没有写入任何内容」+解锁可关）。
- **空书架空态 SHALL 并列两条出路**：「把上一版的作品带过来」（存在可搬运候选时）与「从备份包恢复」（恒在，覆盖换安装目录/换机的用户——便携式布局下候选扫描看不到其他目录）。两条出路的补救语句 SHALL 各带一个可点击出口。
- **只读诊断面**：不可读隔离件（`.corrupt-*`）SHALL 在向导发现步或设置·备份与恢复行以只读清单列出（文件名·体积·时间），SHALL NOT 提供带回动作。
- 书架非空时提示条常驻可 dismiss——dismiss 唯一合法形态「保留旧文件，不再提醒」，记忆键绑定候选身份快照（stamp 取三件套 `max(mtime)`＋三件套体积；新候选出现自动重开），设置行留永久路标。
- **清理（后端承载）**：SHALL NOT 自动删除任何旧版库；SHALL 提供**已带回件**的盘点与删除端点，且：仅 `stamp == migration.last.source_stamp`（本次成功带回的源）可删；待删清单默认保留最近 2 份；路径 MUST 通过候选白名单校验、`resolve()` 收敛在数据目录内、且 MUST NOT 是活跃库或哨兵名；删除经 L2 盘点确认（不可逆声明＋「已带回内容不受影响」声明＋「先备份一份」出口，**不要求输入文件名**）；部分失败（有书未带回）时 SHALL NOT 出现清理入口。
- 用户可见文案 SHALL 遵循「带回」口径（「找回我的书」「把上一版的作品带过来」），SHALL NOT 出现「迁入/迁移/数据库/版本号/文件路径」等内部术语。

#### Scenario: 空书架开口

- **WHEN** 新版首启空库且扫描到含 5 本书的上一版库
- **THEN** 书架空态呈现「把上一版的作品带过来」开口并与「从备份包恢复」并列；单次确认即可完成搬运并给出结果回声

#### Scenario: 清理二步确认

- **WHEN** 全部带回且计数核对一致后用户展开清理
- **THEN** ConfirmGuard 呈现盘点 chips（N 本书·M 字·最后使用时间）与不可逆声明，默认保留最近 2 份；确认后才删除；已带回内容不受影响；未成功带回过的候选 SHALL NOT 出现在待删清单

#### Scenario: dismiss 不吞新数据

- **WHEN** 用户 dismiss 某候选后回滚旧版又写了新书再升级
- **THEN** 候选 stamp 变化（三件套 `max(mtime)`/体积）→ 提示自动重开（合并语义 INSERT OR IGNORE：同 PK 行当前库获胜）

#### Scenario: 存量新旧两种形态都可带回

- **WHEN** 盘上是已发布客户端写出的第 0 代 `novel.db`，或开发/内测形态的遗留代数名 `novel-v1.db`
- **THEN** 两者都进入候选（遗留代数名 MUST NOT 被「版本 ≥ 当前」按语义化比较排除）；唯一候选时走单次确认；源文件字节不变

#### Scenario: 换安装目录后无候选

- **WHEN** 用户把程序装到了新目录（便携式布局下数据不跟随）首启
- **THEN** 书架空态不出现候选，但「从备份包恢复」出口照常可达；用户经资产包导入取回作品

#### Scenario: 候选默认不选错

- **WHEN** 同族内多份候选，其中一份主文件 mtime 更早但 WAL 里刚写过
- **THEN** 排序按三件套 `max(mtime)`，推荐位落在真正最近使用的那份；`recommended` 由后端给出

#### Scenario: 部分失败不出清理入口

- **WHEN** 本次搬运有书未成功带回
- **THEN** 结果页 SHALL NOT 出现清理入口，且待删清单不含任何未成功带回的件

### Requirement: 库文件版本命名与首启状态机

- 库文件 SHALL 按 `novel-v{app_version}.db` 命名，`app_version` 取自打包期烘入的 C端 版本（`v*` 标签构建＝去前缀真实版本；PR/手动构建＝`dev`，映射为**固定哨兵文件名**，不随构建变化）。`SCHEMA_VERSION` 与「代数计数器」概念退役：版本号本身即库文件身份，**不存在**「删列要升代、加列不升代」的分叉。
- 每个版本 SHALL 只读写自己版本号的库文件；SHALL NOT 改名、写入或删除任何其他版本库文件与历史文件（**拷贝前进**）。
- **活跃库 SHALL 按路径判定**（`DATABASE_URL` 解析出的文件路径），SHALL NOT 依赖版本比较来区分「哪一份是当前库」——版本相等（`0.24` 与 `0.24.0`）与全数字版本（tag `v1`）都不得导致已无主的库不可达。
- 首启自己版本库不存在 SHALL 以空库启动（`create_all` 兜底建表），并进入候选扫描态；**代内就地补列机制 SHALL 退役**（不再存在对既有库执行 DDL 的路径）。
- 自己版本库存在但 schema 指纹不符时 SHALL 按**可读性分流**，两条路都不得让数据在产品内不可达：
  - **可读而形状不同**（指纹不符但能打开）→ 改名为 `novel-v{X}.db.mismatch-<stamp>`，该件 SHALL 作为候选参与找回（可一键带回其内容）。
  - **不可读/损坏** → 三件套改名为 `novel-v{X}.db.corrupt-<stamp>` 隔离，SHALL NOT 进候选，但 SHALL 在只读诊断面可见（文件名·体积·时间）。
- **空文件豁免**：文件存在但无任何表且无 `schema_id`（中断首启的残壳）SHALL 判为 `fresh_boot` 直接复用，SHALL NOT 隔离——避免每次中断多攒一个隔离件。
- **隔离/改名 SHALL NOT 让应用起不来**：迁移前先尝试把当前库 WAL 落盘（`wal_checkpoint(TRUNCATE)`，失败不阻断）；改名失败（Windows 文件锁/杀软占用）SHALL 重试一次，仍失败则记日志、保持原文件原位并返回可展示的启动状态，SHALL NOT 抛未捕获异常。
- 第 0 代旧库（`novel.db`、`novel.db.legacy-*`）、历史版本库（`novel-v{k}.db`）、遗留代数名（全数字 `novel-v{k}.db`）、`.mismatch-*` 件 SHALL 只读留存、可作候选；`.corrupt-*`、`.bak*`、`-wal`、`-shm`、`migration-staging/` SHALL NOT 进候选。
- 数据目录 SHALL 维持跟随程序安装目录（便携式，既定裁定）；候选扫描 SHALL 只覆盖本机当前数据目录。

#### Scenario: 每版新建自己的库

- **WHEN** v0.25 首启且盘上只有 v0.24 的库（`novel-v0.24.db`）
- **THEN** 建 `novel-v0.25.db` 空库启动；`novel-v0.24.db` 字节不变并进入候选

#### Scenario: 回滚装回旧版

- **WHEN** 用户已用 v0.25 写过书，随后装回 v0.24 启动
- **THEN** v0.24 打开自己的 `novel-v0.24.db` 直接可用（数据为升级当时状态＋此后在 v0.24 里的写入），不出现空书架；`novel-v0.25.db` 不因版本比较而被误当作当前库

#### Scenario: 同版本形状不符仍可带回

- **WHEN** 同一版本号的库由另一份 schema 不同的构建写过（同 tag 重打包、删 tag 重打、dev 哨兵下的连续开发）
- **THEN** 该件改名为 `novel-v{X}.db.mismatch-<stamp>` 并作为候选出现，用户可一键带回其内容；当前版本新建空库；`.mismatch` 件字节不变

#### Scenario: 损坏库只读可见

- **WHEN** 当前版本库文件不可读（非 SQLite 字节流）
- **THEN** 三件套隔离为 `.corrupt-<stamp>`，空库启动；隔离件不进候选但在只读诊断面列出；应用正常起得来

#### Scenario: 空壳文件不积隔离件

- **WHEN** 首次建库过程中进程被杀，留下 0 表且无 `schema_id` 的同名文件
- **THEN** 判为 `fresh_boot` 复用该文件，不产生任何 `.corrupt-*`

### Requirement: 跨版本转换器链纪律

- 跨版本搬运 SHALL 以**通用列交集搬运**为基线（多数版本无需任何专用转换）；需要语义转换的相邻版本 SHALL 在 `migration/converters/` 提供 `(from_version, to_version)` 转换器，跨多版本 SHALL 按序叠加相邻转换器，SHALL NOT 维护任何直通转换器。
- 链完整性 SHALL 由测试断言：若 `converters/` 存在条目，其 `(from, to)` MUST 相邻且 MUST 可链式到达当前版本；当前无条目时断言 MUST 为绿（空链合法）。
- 版本 PR SHALL 同时携带：必要的相邻转换器（当且仅当存在语义变化）、drill seed 场景。仅列形状变化（加列/加表）的版本 SHALL NOT 需要转换器。

#### Scenario: 跨两代迁入

- **WHEN** 候选为 x.y 库、当前版本 x.z（z ≥ y+2）
- **THEN** 副本上按相邻跳链式转换后入列交集搬运；报告含各跳转换摘要

#### Scenario: 空链合法

- **WHEN** 当前无任何转换器条目
- **THEN** 链完整性断言通过（不得因「目录为空」判失败）

#### Scenario: 非相邻转换器被拒

- **WHEN** 有人新增一条 `(0.24 → 0.26)` 的直通转换器
- **THEN** 链完整性断言失败（必须补 `0.25 → 0.26` 这一跳）

### Requirement: 升级演练升格（version-chain）

- `upgrade_drill` SHALL 提供 `version-chain` 阶段：seed 旧版本库→boot 新 build→断言源文件逐字节不变、自己版本新库空库启动、候选检出、单次确认搬运、搬运计数对拍、搬后再导出 roundtrip 全绿；SHALL 覆盖**跨两版链式搬运**（N-2 → N）并在摘要中打印实际版本对。
- 全部阶段 SHALL 由**单一库名派生辅助**取库路径（不得各阶段硬编码库名），且每个阶段显式设定 `CLIENT_VERSION`。
- 每个版本 PR SHALL 以本演练全绿为验收门（不再限于「破坏性升代」）。

#### Scenario: 升代验收

- **WHEN** 任一版本 PR 提交
- **THEN** version-chain 演练全绿（含源只读、空库启动、候选检出、搬运对拍、搬后 roundtrip），摘要含实际版本对（如 `0.23 → 0.25`）

### Requirement: 打包期组件清单（BOM）

- 打包期 SHALL 在 `release.json` 增写 `components` 对象，至少含该版本实际使用的 `db_filename` 与 `backup_format_version`；取值 MUST 由构建期从后端单源读取，**版本号 MUST 由流水线显式传入**（MUST NOT 用环境变量推断，否则自检与产物同源同错）。
- 库内 SHALL 以 `app_meta` 记录本机版本（`app_version`）与同批组件快照（`app_components`），供库文件脱离数据目录后自证来源。
- 组件清单缺失或与实际单源不一致时，打包冒烟断言 MUST 失败，不得静默发布；`components` MUST NOT 进入运行时可覆盖键白名单（它只作断言与诊断锚）。

#### Scenario: 冒烟断言辨识组件

- **WHEN** 某版本出包
- **THEN** 产物内 `release.json.components.db_filename` 等于该版本运行时会打开的库文件名，且与后端单源派生结果逐字相等；删掉该键后同一条断言必须转红

#### Scenario: 库自证来源

- **WHEN** 用户把某版本的库文件拷到别处后打开（如人工备份、排障）
- **THEN** 库内 `app_meta` 可读出写入它的 C端 版本与组件快照
