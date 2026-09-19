## Context

五路评审收敛（关键裁定，含被否备选）：
- 自存储 ADR 后业务数据全在库表内（`composite_storage.py:1-8`），行级迁入对 ADR 后世代完备；前 ADR 世代（设定在盘上 yaml）行迁会丢设定→世代门禁引走资产包通道（架构矛盾 #1 裁定）。
- 现行 `classify_drift` 只认子集→additive；**超集今天判 breaking 清库**——「同代 additive 后退旧 build」是现存事故级缺陷，tolerant 类修复（架构矩阵 #4）。
- `main.py:110-399` 20+ 段 ad-hoc ALTER 且含一处代内 DROP COLUMN（216 行）——新纪律下违例，全删收编声明式（架构「必须现在做」#4）。
- FK 若在迁入连接 ON，`INSERT OR IGNORE` 会把 FK 违规行**静默吞掉**、计数必然对不上——连接保持 OFF＋事后 `foreign_key_check` 报告（架构 #10）。
- 现行 `_scan_legacy_archives` 会把 `-wal/-shm/.bak` 当候选且 WAL 常是 mtime 最新→book_count 可能取自不可读文件——实 bug，新扫描器排除（架构 #11）。
- dismiss/完成态必须绑**候选身份指纹**（path+mtime+size），一刀切键会吞掉「回滚编辑→再升级」的合并提示（架构矩阵 #10）。
- PM 红线 R1（源只读含 WAL：checkpoint 只在副本）、R2（两阶段原子+磁盘预检第 0 步）、R5（宁少勿错：整表跳过+预告）、R7（可核对计数：报告 v:1 preview/result 同构）。
- 首个版本化代号：落地时 SCHEMA_VERSION 初值取 1（novel.db 视为第 0 代）；backup FORMAT_VERSION 是另一根轴不共用。

## Goals / Non-Goals

**Goals：** 升级/回滚/找回任何组合数据无损；换代必经迁入引擎（用户显式确认）；转换器链与演练成为永久工程纪律；「书架空恐慌」在产品层被「开口行+首答句」消解。

**Non-Goals：** 同代文件级恢复（.corrupt 换入，MVP 缓——逻辑恢复由备份包覆盖）；多残留库智能合并去重（列表选择+同 ID 跳过）；自动迁移/自动清理（永须用户显式动作）；data_epoch 同步盘回退检测（留钩子：app_meta 预留键名规范）。

## Decisions

1. **SCHEMA_VERSION 独立模块**（config 拼 URL 引用；被否：models 内=import 环、legacy_archive 内=被退役模块绑架）。
2. **破坏性才 +1**：升代=迁入交互，加列就升代会把引导退化成噪音；additive 走 ADDITIVE_COLUMNS 幂等补列（被否：任何变更都升代）。
3. **tolerant 放行+审计不放声**：不改戳（回升 newer build 即 current）+drift_accepted 键+诊断面可见——无声放行=把清空事故换成漂移库慢性事故（架构 #3）。
4. **六步引擎在暂存副本**：源零接触含不做 checkpoint；中断恢复=删暂存重跑（幂等由 OR IGNORE+PK 保证）。
5. **报告 v:1 preview/result 同构**：skipped/fk_violations 明细列表；前端两步复用同一渲染。
6. **世代门禁**：行迁只对 ADR 后世代；ADR 前走资产包（LEGACY_FIELD_MAP 通道既有）。
7. **转换器链逐代文件+registry+CI 连续性断言**：直通转换器被否（数量失控）。
8. **迁移 INSERT FK OFF**：违规行事后报告不静默吞（计数可核对的前提）。

## Risks / Trade-offs

- [tolerant 掩盖真漂移] → 审计键+诊断面+不改戳（回升自愈）。
- [转换器链长期成本] → PM/架构共同裁定为可接受隐性承诺（代数-1 个文件），CI 断言防缺跳；spec 固化升代 PR 三件套要求。
- [磁盘占用（旧库永留）] → 清理入口（L2 确认）延后 P2；存储便宜书很贵。
- [升代发布带 bug 且用户已迁入] → 源库不动=物理回滚路径（装旧版→旧库完整→重升级 mtime 变化重提示合并，OR IGNORE 合并不重不丢）。

## Migration Plan

1. PR0：schema_version+db_lifecycle（状态机四态+tolerant）+config 版本化+conftest 改造——**本代不 +1**（首个版本化代号落地，novel.db 保持第 0 代候选）；main.py ALTER 段删除。
2. PR1：migration/ 引擎六步+报告 v1+候选扫描（排 -wal/-shm）+世代门禁+免登端点（复用 change 2 防护）。
3. PR2：前端向导五步+空态开口+原型（backup-restore 屏 8/list 空态）+drill gen-bump/loginless。
4. 每步 pytest/vitest/e2e 全绿；PR0 特别验证：现行 novel.db 在新机制下=第 0 代候选、书架不空（现状数据无缝）。

## Open Questions

- `.legacy-*` 历史文件的世代判定（多数为第 0 代）：按库内容探测（有 yaml 世代特征列则门禁）——实现时以 inspect 结果为准，不猜文件名。
