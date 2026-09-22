## Purpose

C端 SQLite 库文件代数治理：SCHEMA_VERSION 单源与 +1 纪律、首启状态机（current/additive/tolerant/breaking 隔离四态）、旧库迁入引擎（副本列交集搬运、源只读、幂等）、迁入候选与世代门禁、逐代转换器链纪律——使升级、回滚、找回在任何组合下数据无损。

## ADDED Requirements

### Requirement: 库文件代数与首启状态机

- 库文件 SHALL 按 `novel-v{SCHEMA_VERSION}.db` 命名；SCHEMA_VERSION 单源于独立零依赖模块，**破坏性 schema 变更**（删表/删列/列改名/类型收窄/约束变更）SHALL +1；additive 变更 SHALL NOT 升代（走代内声明式补列 ADDITIVE_COLUMNS，幂等）。
- 首启 `novel-v{V}.db` 存在时 SHALL 走校验梯：指纹匹配→直接启动；库为子集→代内补列+刷戳；**库为超集且多出列均可空/带默认→tolerant 放行**（不改指纹戳）＋写 `drift_accepted` 审计键＋诊断面可见；breaking/不可读→三件套改名 `.corrupt-<stamp>` 隔离＋空库启动（隔离件不进迁入候选，只读可见）。
- 每个版本 SHALL 只读写自己代数的库文件；SHALL NOT 触碰（读改名写删）任何其他代数库文件与历史文件（R6 版本互不侵入）。

#### Scenario: 破坏性升代首启

- **WHEN** 代数 V 代码首启且存在 novel-v{V-1}.db、无 novel-v{V}.db
- **THEN** 新库空库启动；v{V-1} 文件原位不动；进入迁入候选态

#### Scenario: 同代 additive 后退旧 build

- **WHEN** 代数 V 库曾被 V 代新 build 写过（多列）后，用户退回 V 代旧 build 启动
- **THEN** tolerant 放行启动（现状为误判 breaking 清空书架）；drift_accepted 审计键落库；多余列保留

#### Scenario: 隔离件不自动迁入

- **WHEN** novel-v{V}.db 损坏被隔离为 .corrupt-<stamp>
- **THEN** 空库启动；隔离件只在候选端点的隔离列表只读可见，不进入一键迁入

### Requirement: 旧库迁入引擎（六步＋预检）

- 迁入 SHALL 依序执行：**第 0 步预检**（磁盘可用≥源体积×2、暂存目录与目标同卷、候选≠当前活跃库）→ 暂存三件套拷贝（**源文件此后零接触，含不做 checkpoint**）→ 副本上 checkpoint(TRUNCATE)+integrity_check → 列交集计划（目标存在 NOT NULL 无默认无回填列的表整表跳过并在预览预告）→ ATTACH 只读副本逐表 `INSERT OR IGNORE`（连接 FK 保持 OFF——防违规行被静默吞；app_meta 永不搬；预置种子表靠 PK 幂等）→ `foreign_key_check` 只报不删＋书计数对拍 → 写 `migration.source_filename/source_stamp(path+mtime+size)/finished_at`＋删暂存。
- 迁入 SHALL 幂等：中断（断电/杀进程/用户关闭）后重跑 SHALL 零重复行、源文件无损；重跑经 stamp 与完成记录比对识别「上次已迁入」。
- 迁入报告 SHALL 为 v:1 版本化结构且 preview 与 result 同构（skipped/fk_violations 为明细列表非计数；含 book_count_source/migrated 可交叉核对）。
- 迁入端点全家 SHALL 免登录（复用 loginless-data-exit 防护面）；与导出/下载经 job_runner 跨 kind 单飞互斥。
- **世代门禁**：低于最小行迁世代（设定存于盘上 yaml 的前 ADR 世代）的候选 SHALL NOT 进入行级迁入，向导 SHALL 引导走资产包导入通道。

#### Scenario: 源数据只读

- **WHEN** 迁入全程完成或中途失败
- **THEN** 源库三件套（db/-wal/-shm）字节不变（含 mtime 不因迁入变化）

#### Scenario: 中断重跑幂等

- **WHEN** 迁入进行到第 4 步某表时进程被杀，用户重开向导再迁
- **THEN** 重跑完成且全库零重复行；预览将已入表行标「上次已找回」默认不勾

#### Scenario: 不可迁世代引走

- **WHEN** 候选为前 ADR 世代旧库（设定在盘上 yaml）
- **THEN** 向导不提供一键迁入，明示走「备份包导入」通道

### Requirement: 迁入候选与找回向导

- 候选扫描 SHALL 覆盖 `novel-v{k}.db`(k<V)、`novel.db`、`novel.db.legacy-*`，SHALL 排除 `-wal`/`-shm`/`.bak` 后缀与 book_count=0 的空库；每候选只读体检（书数/卷章/字数/mtime/可读性）。
- 向导五步：发现（首答「没有丢失——在这台电脑上找到了旧版作品」＋计数）→多代选择（仅 >1 份时；按时间+计数呈现并标「推荐」，不出文件路径/版本号）→预览（逐书字数核对；重名行内预告《书名（旧版）》；缺列/整表跳过预告）→进度（locked）→结果（hero「已找回 N 本书」＋与预览同源计数；部分成功=成功主叙事+失败行「重试这本书」；全部失败=回滚声明「这次没有写入任何内容」+解锁可关）。
- 空书架且存在候选 SHALL 在书架空态呈现开口行「这台电脑上有旧版作品 · 找回我的书」（**推翻 backup-restore v3 首启静默口径**：空库必须开口）；书架非空时提示条常驻可 dismiss——dismiss 唯一合法形态「保留旧文件，不再提醒」，记忆键绑定候选身份快照（新候选出现自动重开），设置行留永久路标。
- 清理旧文件 SHALL 为结果页可选折叠的 L2 盘点确认（ConfirmGuard：不可逆声明+已找回不受影响声明+「先备份一份」出口；**不要求输入文件名**）；部分失败时清理入口 SHALL NOT 出现。

#### Scenario: 空书架开口

- **WHEN** 新版首启空库且扫描到含 5 本书的旧库
- **THEN** 书架空态呈现「找回我的书」开口；自动弹向导一次（本会话尺度）

#### Scenario: 清理二步确认

- **WHEN** 全部找回且计数核对一致后用户展开清理
- **THEN** ConfirmGuard 呈现盘点 chips（N 本书·M 字·最后使用时间）与不可逆声明；确认后才删除；已找回内容不受影响

#### Scenario: dismiss 不吞新数据

- **WHEN** 用户 dismiss 某候选后回滚旧版又写了新书再升级
- **THEN** 候选 stamp 变化（mtime/size），提示自动重开（合并语义 INSERT OR IGNORE：同 PK 行当前库获胜）

### Requirement: 逐代转换器链纪律

- 跨代迁入 SHALL 经 `migration/converters/` 逐代链式转换（v(k)→v(k+1)→…），SHALL NOT 维护任何直通转换器；链完整性 SHALL 由 CI 断言（registry 连续性）。
- 升代 PR SHALL 同时携带：SCHEMA_VERSION+1、对应转换器、drill seed 场景——缺任一 SHALL NOT 合入。

#### Scenario: 跨两代迁入

- **WHEN** 候选为 v3 库、当前代 v5
- **THEN** 副本上链式 v3→v4→v5 后入列交集搬运；报告含各跳转换摘要

### Requirement: 升级演练升格（gen-bump）

- upgrade_drill SHALL 新增 gen-bump 阶段：seed 低代库→boot 新 build→断言源文件逐字节不变、空库启动、候选检出、一键迁入、迁入计数对拍、迁后再导出 roundtrip 全绿。
- SHALL 新增 loginless-export 阶段（免登导出→包内无配置块断言）。升代 PR SHALL 以本演练全绿为验收门。

#### Scenario: 升代验收

- **WHEN** 某 PR 使 SCHEMA_VERSION +1
- **THEN** gen-bump 演练在该 PR 上全绿方可合入
