## 落地状态（2026-09-22 开工后回填；PR #464）

**已完成并验证**（证据：命令输出摘要如下，PR #464 内可复现）

- 0.1 归档前序 change ✓ `openspec list --specs | grep -c db-generation` = 1；本 change validate 无 INFO
- 1.1/1.2/1.3 原型与登记 ✓ `list.html` 首启出口行（两出口；变体段 `display:none`）＋`ADJUSTMENTS.md` 第 8 条
- 2.1–2.3 命名单源/解析/比较 ✓ 单测覆盖 `0.9<0.10`、`0.24==0.24.0`、`0.24-rc1<0.24`、遗留名/哨兵/`.mismatch` 判别；`update_check` 委托（`0.11-beta` 不再抛）
- 2.4 tag 形态门禁 ✓ CI 内联断言（纯数字 tag 拒绝）＋本地样例预演
- 3.1–3.4 三态＋分流／改名稳健／补列链退役／版本戳 ✓ `test_db_lifecycle.py`（V1–V7）＋反断言 grep 0 行
- 4.1–4.5 候选白名单/排序/推荐/体检/载荷/残留清理 ✓ UP-03/UP-10/UP-15 ＋ 端点反断言（无 `generation`/`schema_version` 键）
- 5.1–5.3 快照与守卫（不拷 -shm、暂存 checkpoint、一致性拒绝、source_version）✓ UP-04/UP-04b ＋ `test_migration_engine.py`
- 6.1/6.2 清理端点与路径收口 ✓ UP-12/UP-12b（含 `../` 与未带回件拒绝）
- 7.1 死面改由候选扫描供数 ✓ `legacy-db/status` 消费方零改动
- 8.1–8.5 验收矩阵 ✓ UP-01…UP-15（17 用例）全绿；UP-14 单源部分绿
- 9.1–9.3 drill 全阶段命名单源＋version-chain ✓ `upgrade_drill.py --all` 全部通过（摘要含四项结论与版本对）
- 10.1/10.2/10.4 类型/双出口/契约同步 ✓ tsc 0 错；`vitest` 716 通过（含新增双出口两用例）
- 11.1/11.2 components＋冒烟正负例 ✓ 本地同命令预演通过（CI 侧随 tag 触发）
- 12.1–12.4 门禁 ✓ pytest 1277 / vitest 716 / tsc / design:lint / 反断言四条 0 行

**未完成或带口径（交付时如实登记）**

- 10.3 后半：**清理清单 UI 与隔离件只读清单** 未实现（后端 `retention`/`cleanup` 与 `quarantined` 只读数据已就绪；前端仅做了文案口径与双出口）
- 11.3 `notes-release.md` 未写（首个新版本发布说明需写明「升级后需把上一版的作品带过来」＋平台差异）
- UP-11 的 **playwright e2e** 未落（需 docker 栈）：换目录双出口已在 vitest 层覆盖（两用例：无候选时第二出口仍在 / 有候选时并列且书数正确）
- UP-16 **真实数据演练**未跑（需把本机 `client/backend/data/novel.db` 与 `.docker-data/client/novel-v1.db`（35MB，活跃 WAL）拷到会话私有目录再走 首启→候选→搬运）
- UP-14 的 **CI 产物侧**断言未真跑（未打 tag；本地同命令预演已过）
- `design:check` 未全量跑：parity 7 场景中 `list.empty` **1.449% → 1.463% 为 HEAD 存量红**（已用基线 worktree `dfceb17d` 对照证明非本次引入；本次新增约 0.014%）
- 13.1 文档（dev 说明/帮助文档两条人工路径）未落

## 0. 前置：归档前序 change

- [ ] 0.1 归档 `openspec/changes/c-db-generation-migration/`（16/16 已完成、代码随 #453 在 main）→ 把 `db-generation` 立进 `openspec/specs/`、`backup-restore` delta 同步；归档后手改 `openspec/specs/db-generation/spec.md` 的 Purpose 段（代数→版本）。验证：`openspec list --specs | grep -c db-generation` ＝1，且 `openspec validate c-db-per-version` 不再出现「target spec does not exist」

## 1. 原型先行（UI 变更的第一批）

- [ ] 1.1 `docs/design-c/prototypes/list.html` 首启空态出口行常驻化、并列两出口（「把上一版的作品带过来」/「从备份包恢复」），形态对齐 `backup-restore.html` 屏 4 的 `fr-note`。验证：`grep -c '把上一版的作品带过来' list.html` ≥1 且 `grep -c '从备份包恢复' list.html` ≥1；原型内 `data-od-id` 齐备
- [ ] 1.2 `docs/design-c/prototypes/backup-restore.html` 屏 8 向导/结果页文案改「带回」口径，并补清理清单屏（默认保留 2＋部分失败不出入口两态）。验证：先钉屏锚点 `data-od-id` 存在，再断言该屏文本 grep 不含「迁入/迁移/数据库/版本号/文件路径」
- [ ] 1.3 `docs/design-c/prototypes/ADJUSTMENTS.md` 逐条登记（出口行常驻化、文案口径、清理两态、隔离件只读清单）。验证：每条登记都带被登记文件锚点（file 或 `data-od-id`），与 1.1/1.2 diff 一一对应

## 2. 后端 · 命名单源与版本比较（design D1/D3/D10）

- [ ] 2.1 重写 `client/backend/schema_version.py`：`app_version()`（委托共享实现）、`db_filename_for(version)`、`parse_db_filename(name)`（返回带 kind 的判别：semver/legacy/legacy-generation/gen0/sentinel/mismatch/非候选）、`version_sort_key(version)`；删死常量 `MIN_ROW_MIGRATION_GENERATION`、`DATA_ROOT_ENV`。验证：单测覆盖 `0.9<0.10`、`0.24-rc1<0.24`、`0.24==0.24.0`、`1` 判 legacy-generation、`novel-dev.db` 判 sentinel、`novel.db`/`.legacy-*` 判 gen0、`novel-v0.24.db.mismatch-20260922` 判 mismatch、`novel.db.e2e-*` 判非候选
- [ ] 2.2 版本比较抽共享实现（`update_check` 反向复用），**非法串降最低且永不抛**；`update_check.get_update_state` 加不抛保护。验证：既有 `tests/test_update_check.py` 全绿；`0.11-beta` 由「抛 ValueError」改判为「有确定序」的用例通过；`grep -rn "def _parse_version\|_VERSION_RE" client/backend/update_check.py` 只余委托
- [ ] 2.3 `client/backend/config.py` 的 `DATABASE_URL` 由派生函数生成（显式 env 覆盖优先）。验证：`CLIENT_VERSION=0.24` 得 `novel-v0.24.db`；不设得哨兵名；`DATABASE_URL=… 显式值` 时取显式值不取派生值（三种取值的断言）
- [ ] 2.4 CI tag 形态断言：清洗后版本 MUST 匹配 `^[0-9]+(\.[0-9]+)+([-._][A-Za-z0-9._-]+)?$` 且 MUST NOT 为纯数字（纯数字会与遗留代数名同形）。验证：workflow 内联脚本以 `v1`/`v0.24-rc1`/`v0.24` 三个样例本地预演，前两者按规则拒绝/通过符合预期

## 3. 后端 · 首启三态与分流（design D4）

- [ ] 3.1 `boot_lifecycle` 收敛三态＋分流：指纹匹配→`current`；不存在或「0 表且无 `schema_id`」→`fresh_boot`；**可读而异形**→改名 `novel-v{X}.db.mismatch-<stamp>` 且返回可带回标记；**不可读**→`.corrupt-<stamp>` 隔离。验证：更新 `tests/test_db_lifecycle.py`（原 additive/tolerant 两用例改判为分流两条），并新增「空壳不隔离」「.mismatch 件字节不变」用例
- [ ] 3.2 隔离/改名的稳健性：迁移前尽力 `wal_checkpoint(TRUNCATE)`；三件套移入**单目录**；失败重试一次后记日志并返回可展示状态（不抛到 lifespan）。验证：单测用 monkeypatch 让 `os.replace` 首次抛 `PermissionError` → 断言重试后成功；持续抛 → 断言不抛异常且 `main.py` 起得来（TestClient 200）
- [ ] 3.3 删 `ADDITIVE_COLUMNS`/`apply_additive_columns` 与 `main.py` 重复调用块（94-101）＋死字典（205-208）＋`ADDITIVE_VOLUME_COLS`；删 `drift_accepted` 写入分支。验证：反断言 `grep -rn "ADDITIVE_COLUMNS\|apply_additive_columns\|ADDITIVE_VOLUME_COLS\|drift_accepted\|tolerant_booted\|additive_booted" client/ server/` 输出 0 行；`pytest` 全量绿
- [ ] 3.4 `app_meta` 版本戳：键名钉死 `app_version`(str) ＋ `app_components`(JSON: `{"db_filename","backup_format_version"}`)；首启与搬运收尾写入，版本不同则按「最后写入方」刷新；只写当前库。验证：单测断言首启落键、换版本启动刷新、**源库 `app_meta` 前后 diff 为空**

## 4. 后端 · 候选、排序、推荐与诊断面（design D2/D3/D6）

- [ ] 4.1 `scan_migration_candidates` 改白名单**形状枚举**（禁 `novel*` 前缀通配）：semver 名 / 纯数字遗留名 / 恰为 `novel.db` / `novel.db.legacy-*` / 哨兵 / `.mismatch-*`；排除活跃库路径、边车、`.bak*`、`.corrupt*`、空库、空壳、`migration-staging/`。验证：单测以真实残件命名（`novel.db.e2e-20260909-223352`、`novel.db.recovered-*`、`novels.db`、`migration-staging/x.db`）断言全部不进候选
- [ ] 4.2 排序与推荐：semver 逐段数值降序 → 遗留数字降序 → 第 0 代 → 哨兵垫底；同族按三件套 `max(mtime)`；`recommended` 由后端给（第一个不新于当前版本者）；**新于当前版本的候选列出但不推荐**。验证：单测覆盖 `["novel-v0.24.db","novel-v0.23.db","novel-v1.db","novel.db"]` 全序、`0.99` 在 v0.25 下列出且 `recommended=false`、`0.24` 在 `0.24.0` 下不因相等被排除
- [ ] 4.3 体检口径：只读打不开时走暂存复检（拷 db＋wal→可写打开→checkpoint→读计数）再判可读性。验证：用真实形态 fixture（WAL 模式头 + 无 `-shm` 的库）断言 `unreadable=false` 且 `book_count` 正确
- [ ] 4.4 载荷字段改版本语义：候选项 `{filename, version, kind, size_bytes, mtime, book_count, unreadable, recommended, stamp, suppressed}`，顶层 `current_version`＋`quarantined`（只读隔离件清单）。验证：端点测试断言响应体**不含** `generation`/`schema_version` 键（反断言）
- [ ] 4.5 清理残留：启动或候选扫描时清掉非本次会话的 `migration-staging/*`。验证：单测造休眠残留目录 → 断言被清且候选不含它

## 5. 后端 · 引擎快照与一致性守卫（design D7）

- [ ] 5.1 第 1 步改「拷 db＋`-wal`（**不拷 `-shm`**）→ 暂存可写打开→`wal_checkpoint(TRUNCATE)`→`integrity_check`」。验证：单测断言源 `-shm` 未被读取、暂存可 checkpoint、计数含 WAL 中未落主文件的提交
- [ ] 5.2 拷贝一致性守卫：前后快照源三件套 `(size, mtime_ns)`，变化重试一次，仍变化则拒绝并给可读原因。验证：单测在拷贝回调里改源 mtime → 断言重试一次后仍变化即 `{"ok": false, "reason": "source_busy"}`（文案含「关闭旧版本应用」）；源静止时零重试
- [ ] 5.3 `precheck`/报告字段改版本语义（`source_version`/`legacy_generation` 取代 `generation`），保留 `book_count_source`/`book_count_migrated` 既有名。验证：`tests/test_migration_engine.py` 全绿且断言不含旧键

## 6. 后端 · 清理端点（design D9）

- [ ] 6.1 新增 `GET /api/backup/db-migration/retention`（待删清单：仅 `stamp == migration.last.source_stamp` 的件；默认保留最近 2 by 三件套 max mtime）与 `POST /api/backup/db-migration/cleanup`（执行删除）。硬校验：白名单形状＋`resolve()` 收敛在数据目录内＋非活跃库＋非哨兵；无用户动作永不删。验证：端点测试覆盖「3 份历史只列 1 份」「未带回件不出现」「路径穿越 `../` 被拒」「活跃库被拒」「部分失败时清单为空」
- [ ] 6.2 `dismiss` 端点同批收紧路径校验（现状直接 `DATA_ROOT / filename`，无校验）。验证：单测传 `../../etc/passwd` 被 422

## 7. 后端 · 死面与相邻端点（design D12）

- [ ] 7.1 `backup/router.py` 的 `legacy-db/status`（旧留档机制）改为指向新候选端点或退役；同步 `client/frontend/src/pages/LoginPage.tsx` 的消费点。验证：反断言 `grep -rn "legacy-db/status" client/` 只余改造后的单一来源；`pytest tests/test_legacy_archive.py` 按新语义更新后绿

## 8. 后端 · 版本升级验收用例（评审矩阵 UP-01…UP-15）

- [ ] 8.1 新建 `client/backend/tests/test_version_upgrade_acceptance.py`：落地 UP-01（全新首启）、UP-15（噪声排除）、UP-03（遗留代数名进候选且垫底）、UP-10（dev 哨兵与 dev 不过滤）。验证：四个用例全绿，且 UP-03 断言 `legacy_generation==1` 与排序位置
- [ ] 8.2 落地 UP-02（同路径升级：新库空启动＋源 sha256/mtime_ns 不变＋候选＋单次确认搬运＋计数对拍）、UP-06（跨两版链式）、UP-08（先写后搬同 PK 当前库获胜）。验证：三用例全绿，断言含源三件套 sha256/mtime_ns 前后相等
- [ ] 8.3 落地 UP-04（第 0 代 + WAL 边车）、UP-07（硬杀 `os._exit(9)` 后重跑零重复）、UP-05（回滚：旧库直接可用、无 `.corrupt`）。验证：三用例全绿；UP-07 断言三个表计数无重复
- [ ] 8.4 落地 UP-09（损坏同名库分流）、UP-13（app_meta 版本戳与库自证）、UP-12（留存与清理两态）。验证：三用例全绿；UP-13 断言源 `app_meta` diff 为空
- [ ] 8.5 UP-14（release.json components 正/负例）与「components 不进 `RELEASE_OVERRIDE_KEYS`」断言落到打包任务 11.2 的同组脚本。验证：正例相等、负例（删键）转红、白名单反断言 0 命中

## 9. 演练 · version-chain（design D6/规格）

- [ ] 9.1 `upgrade_drill.py` 全阶段改为**单一库名派生辅助**取路径（不得各阶段硬编码 `novel-v{SCHEMA_VERSION}.db`），每阶段显式设 `CLIENT_VERSION`。验证：`grep -n "SCHEMA_VERSION" scripts/upgrade_drill.py` 输出 0 行；`--all` 全绿
- [ ] 9.2 新增 `version-chain` 阶段（seed 旧版本库→boot 新 build→断言源只读、空库启动、候选检出、单次确认搬运、计数对拍、搬后 roundtrip），覆盖 N-2 → N 并在摘要打印实际版本对。验证：`python scripts/upgrade_drill.py --all --work /tmp/drill-<stamp>` 全绿，`PHASES` 可 grep 到 `version-chain`，摘要含 `0.23 → 0.25` 形态的版本对与四项结论
- [ ] 9.3 删除规格里不存在的 `loginless-export` 阶段的引用（该阶段从未实现，属前序 change 的账）。验证：`grep -rn "loginless-export" openspec/changes/c-db-per-version/ scripts/upgrade_drill.py` 输出 0 行

## 10. 前端（单端改动）

- [ ] 10.1 `hooks/useLegacyDb.ts` 类型改版本语义（`version`/`kind`/`recommended`/`current_version`）。验证：`npx tsc --noEmit` 绿 ＋ 反断言 `grep -rn "generation" src/hooks src/components | grep -v legacy_generation` 输出 0 行
- [ ] 10.2 `pages/NovelListPage.tsx` 首启空态出口行**常驻**并列两出口：「把上一版的作品带过来」（有候选时，单次确认→搬运→结果回声）与「从备份包恢复」（恒在，唤起 `RestoreModal`）。验证：`src/__tests__/novelListPage.test.tsx` 补两出口存在性＋「候选为空时第二出口仍在」分支并全绿
- [ ] 10.3 `LegacyMigrateModal.tsx`：文案改「带回」口径；结果页接清理清单（默认保留 2、部分失败不出入口）；发现步补隔离件只读清单。验证：组件单测覆盖三态；文案断言不含内部术语
- [ ] 10.4 `AcctMenu.tsx`/`RestoreModal.tsx` 入口与 `coverage-contract.ts` 同步（新增组件必须登记）。验证：`npx vitest run` 全绿且 `coverageContract.test.ts` 通过

## 11. 打包与发布（BOM）

- [ ] 11.1 `.github/workflows/client-package.yml` 生成 `release.json` 时增 `components`（`db_filename`、`backup_format_version`），版本**显式传入**并 import 后端单源取值。验证：本地以同一片段预演，输出与 `db_filename_for("0.25")`、`backup.format.FORMAT_VERSION` 逐字相等
- [ ] 11.2 冒烟断言正/负例：缺失或与单源不一致即失败；`components` 不进 `RELEASE_OVERRIDE_KEYS`。验证：删键后断言退出码非 0 且点名缺失键；`grep -n "components" client/backend/config.py` 0 命中
- [ ] 11.3 发布说明底稿 `notes-release.md`（首个新版本必须写明「升级后需把上一版的作品带过来；旧文件原位保留、可装回旧版本」＋平台差异：Windows 原地覆盖数据原地、macOS 数据在 Application Support）。验证：文件落库，末尾留用户过目记录位

## 12. 回归门禁与证据

- [ ] 12.1 后端全量 `python -m pytest tests/ -q`，输出摘要（通过/失败/用例数）写在此任务下
- [ ] 12.2 前端 `npx tsc --noEmit`、`npx vitest run`、`npm run design:lint`、`npm run design:check`（像素差百分比写在此任务下，须 <0.2%）
- [ ] 12.3 e2e：**以干净会话私有 `DATA_ROOT`**（或 candidates suppressed）跑 `npx playwright test`，落地 UP-11（换目录无候选 + 两出口）用例；用例数/失败数写在此任务下
- [ ] 12.4 反断言门禁四条全部输出 0 行：`ADDITIVE_COLUMNS|apply_additive_columns`、`SCHEMA_VERSION|DB_FILENAME`（backend）、`generation`（frontend，除 `legacy_generation`）、`drift_accepted|tolerant_booted|additive_booted`
- [ ] 12.5 人工真数据演练（UP-16）：**拷贝**（不原地）`client/backend/data/novel.db(+wal/shm)` 与 `.docker-data/client/novel-v1.db(+wal/shm)` 到会话私有目录 → 首启→候选→preview→一键搬运→roundtrip；留两组三件套 sha256/mtime_ns/size 前后对照表＋候选 JSON＋report JSON＋首启空态与结果页截图（落 `openspec/changes/c-db-per-version/evidence/screens/`）
- [ ] 12.6 证据清单归档到 `openspec/changes/c-db-per-version/evidence/`：源库对照表、candidates 原文、每候选 preview/report、新库 `app_meta` dump、UP-07 退出码与残留清单、日志行（含 `boot=` 与「tolerant drift accepted 不得出现」）

## 13. 收尾

- [ ] 13.1 文档：dev 说明补「dev 哨兵名与 `DATA_ROOT` 绕法」；帮助文档补「换安装目录/换机：老版本导出→新版恢复」「把旧 `data\` 拷进新安装目录即可被带回」两条。验证：两份文档 diff 落库
- [ ] 13.2 `todo.md` 条目关账＋`openspec validate c-db-per-version` 通过。验证：两条命令输出
