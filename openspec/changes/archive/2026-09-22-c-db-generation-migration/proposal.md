# Proposal: c-db-generation-migration

## Why

C端 schema 换代现走「指纹不符→整库改名 `.legacy-<stamp>`→空库启动」：升级即书架空（2026-09-19 用户本人连撞两次「书丢了」）、留档堆积不可预测、回滚互踩（旧代码回来又 breaking 再留档）、救援无 UI。结构性修复＝**DB 版本化命名**：`novel-v{SCHEMA_VERSION}.db`，代码与库文件一一对应，旧库永不被触碰——升级、回滚、迁入全部安全。

## What Changes

- **SCHEMA_VERSION 单源**：独立零依赖模块 `schema_version.py`（config.py 拼 DATABASE_URL 引用；不放 models 防 import 环）。**破坏性变更才 +1**（删表/删列/改名/类型收窄）；additive（新表/可空列）走代内声明式补列 `ADDITIVE_COLUMNS`，不升代。
- **首启状态机**：`novel-v{V}.db` 存在→指纹校验梯→current／additive 补列／**tolerant 放行**（库为超集且多出列可空/带默认——修「同代 additive 后退旧 build 被误判 breaking 清空」的现存缺陷）＋审计键 `drift_accepted`（不放行无声化）／breaking·不可读→改名 `.corrupt-<stamp>` 隔离＋空库；不存在→空库＋扫迁入候选。
- **迁入引擎（六步＋第 0 步）**：0 磁盘与安全预检（空间≥源×2、暂存同卷、候选≠活跃库）→1 暂存三件套拷贝（**源文件此后零接触**）→2 副本 checkpoint+integrity→3 列交集计划（NOT NULL 无默认列整表跳过并预告）→4 ATTACH ro 逐表 `INSERT OR IGNORE`（**FK OFF**＋app_meta 永不搬＋预置种子表幂等）→5 `foreign_key_check` 只报不删＋计数对拍→6 收尾写 `migration.*` 键（**绑定候选身份指纹 path+mtime+size**——回滚编辑后再升级会重新提示合并，dismiss 不吞）＋删暂存。
- **迁入候选与世代门禁**：候选=`novel-v{k}.db`(k<V)＋`novel.db`＋`novel.db.legacy-*`（**排除 -wal/-shm/.bak 噪声**——现行扫描器的实 bug）；book_count=0 剔除；**前 ADR 世代（设定在盘上 yaml 的旧库）不进行级迁入**，向导引导走资产包通道（行级迁入会丢设定，违 R5）。
- **迁入向导（UX=「找回我的书」五步）**：发现（首答「没有丢失」＋计数）→多代选择（时间+计数呈现，不出文件路径）→预览（重名《（旧版）》后缀行内解决、缺列预告、「上次已找回」幂等标记默认不勾）→进度（locked）→结果（hero「已找回 N 本书」＋计数核对；部分成功成功为主叙事；清理=L2 ConfirmGuard 盘点确认，**不输文件名**——系统产物非用户命名对象）。
- **legacy_archive 退役**：函数迁入新 `db_lifecycle.py`＋`migration/` 包，`archive_if_legacy` 改名语义删除；`main.py` 历史 ALTER 段（110-399，含一处代内 DROP COLUMN 违例）全删收编声明式。
- **转换器链约定固化**：`migration/converters/` 逐代一文件＋registry 链式注册＋CI 连续性断言（链上无缺跳）；升代 PR 必须同时带转换器+drill seed。
- **upgrade_drill 升格**：新增 `gen-bump`（seed 低代库→boot→断言源文件逐字节不变/空库/pending 态/迁入计数对拍/迁后 roundtrip）与 `loginless-export` 阶段，作为升代验收门。

## Capabilities

### New Capabilities
- `db-generation`：库文件代数治理（SCHEMA_VERSION 单源、+1 纪律、首启状态机四态、tolerant 审计、ADDITIVE_COLUMNS）＋迁入引擎（六步+预检、候选与世代门禁、报告契约 v1、转换器链纪律）。

### Modified Capabilities
- `backup-restore`：「旧库留档与升级演练」改写——留档机制退役为隔离件与迁入候选；演练口径升格为 gen-bump 全链。

## Impact

- **后端（client/backend）**：新 `schema_version.py`/`db_lifecycle.py`/`migration/`（engine/router/report/converters）；删 `legacy_archive.py`；`config.py`（DATABASE_URL 版本化）；`main.py`（lifespan 头段重构＋ALTER 段删除＋`config.json→User` 迁移段保留）；`backup/router.py`（候选扫描重写排除 -wal/-shm）；`job_runner.py`（kind 加 migration）；`tests/conftest.py`（测试库路径版本化）。
- **前端（client/frontend）**：新 `useLegacyDb.ts`/`LegacyMigrateBar.tsx`/`LegacyMigrateModal.tsx`（五步向导）；`NovelListPage` 空态开口行；设置「备份与恢复」行增「找回」入口与双徽标态。
- **原型**：`backup-restore.html` 增屏 8（找回向导五步+清理确认）；`list.html` 空态注脚；ADJUSTMENTS 登记（含**推翻 v3「首启静默」口径**：书架空且检出旧数据必须开口）。
- **测试**：db_lifecycle 状态机四态+tolerant+校验梯；引擎六步（幂等重跑零重复/中断恢复/FK OFF 计数对拍/世代门禁）；drill gen-bump；前端向导全流。
- **依赖**：c-loginless-data-exit 的防护面与免登端点先就位（迁入全家免登+回环保护复用其基建）。

## Design Impact

- 受影响端：仅 C端。
- 受影响屏/弹层：书架空态（开口行）／设置备份行（找回入口）／迁入向导 Modal（440px wb-style 五步）。
- 对象状态：进度=既有过程态（serif 大百分比+pill）；幂等项=pill ok「上次已找回」（**ok 非 warn**——成功回声不制造待办错觉）；部分成功=成功主叙事+失败明细行；清理确认=L2 ConfirmGuard（inventory chips 中性陈述，danger 只在确认主按钮）；「不再提示」唯一合法形态=「保留旧文件，不再提醒」（先声明数据去向再停提醒，记忆键绑候选快照，新候选出现自动重开）。
- 文案：用户可见层禁「迁入/迁移/数据库/多代库/资产包」→「找回」「旧版数据」「一份旧版数据」；多代选择只呈现时间+计数，不出文件路径与版本号。
- 原型先行：**需要**——backup-restore.html 增段＋list.html 空态；ADJUSTMENTS 登记三条（含首启静默口径推翻的理由）。
