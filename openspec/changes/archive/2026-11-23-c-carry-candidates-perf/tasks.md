## 1. 原型先行（UI 变更首任务）

- [ ] 1.1 `docs/design-c/prototypes/upgrade-carry.html` 增补「整理旧版数据」两出口形态（归档为主出口＋删除维持原状＋二步确认弹层含「先备份一份」出口），并在 `ADJUSTMENTS.md` 登记偏差原因；验证＝原型在浏览器可走查两出口＋登记条目在案
- [ ] 1.2 文案过声检查（§13：按钮动词「归档」「删除」、不出现内部术语、补救语句带出口）；验证＝最长三条念出声无报表腔

## 2. P0 后端：多槽缓存

- [ ] 2.1 `schema_version.py`：`candidate_stamp_hash` 单槽缓存改为按 `(路径, 主 mtime_ns, size, wal mtime_ns, size)` 键的多槽 LRU（容量 64）＋`threading.Lock`；验证＝单测「同键命中不重读字节（open 计数探针）／mtime 变化即重算／并发线程命中一致」
- [ ] 2.2 `db_lifecycle.py`：`probe_library` 书数探活结果按同键缓存（与 2.1 同一锁与 LRU 机制）；验证＝单测重复扫描不重复开库、数据件变化后重探
- [ ] 2.3 全量跑迁移相关 pytest 确认判定语义零变化（carried/suppressed/清理白名单对拍不变）；验证＝`pytest client/backend/tests/test_migration_engine.py client/backend/tests/test_db_lifecycle*.py` 全绿

## 3. P0 后端：扫描去阻塞

- [ ] 3.1 `migration/router.py`：`candidates`/`retention` 的扫描体改 `await asyncio.to_thread(...)`；验证＝单测模拟慢扫描（monkeypatch 大目录）时并发 `GET /api/novels` 在百毫秒级返回（事件循环不阻塞）
- [ ] 3.2 本机真值复测：43 槽场景连发 `candidates` 与 `check-auth`/`novels`，对比 app.log 排队指纹消失；验证＝curl 计时记录进任务账（candidates 首扫后缓存命中毫秒级）

## 4. P1 后端：链上溯源与归档

- [ ] 4.1 `db_lifecycle.py`：新增链回溯（沿各槽 `app_meta.migration.last` 逐跳回溯＋每跳完整性单源判定＋源槽三形态指纹对拍），候选快照新增只读字段 `chain_carried`；探活同次开库顺读链证据并进缓存；验证＝单测覆盖「三跳全达成／中途缺证断链／链外 dev 槽／源被复写指纹不命中」四形态
- [ ] 4.2 `migration/router.py`：新增 `POST /api/backup/db-migration/archive`（仅收链上白名单内名字，服务端二次收口；`shutil.move` 到 `data/archive/`，绝不删除；白名单校验沿用 `validate_candidate_filename` 家族纪律）；验证＝单测「白名单外 400／归档后文件在 archive 且字节不变／归档件从 candidates/retention/quarantined 三清单消失」
- [ ] 4.3 归档目录惯性核查：隔离清理、staging 残留清理、`parse_db_filename` 白名单对 `data/archive/` 子目录零感知（不扫、不误判）；验证＝单测归档件不进任何盘点清单＋旧版兼容说明一段

## 5. P1 前端：整理入口

- [ ] 5.1 `carryStore.ts`：类型加 `chain_carried`；新增 `archiveCandidates(filenames)` 动作与归档列表态；验证＝vitest 动作调用与态翻转
- [ ] 5.2 `LegacyMigrateModal.tsx`：清理区扩为「归档旧版数据」（主出口，列表＝`chain_carried` 件）＋「删除」（原 retention 清单原样保留）；二步确认弹层按原型 1.1 形态；验证＝组件测试两出口互不串扰、确认后归档回报结果渲染
- [ ] 5.3 对照原型像素门禁；验证＝`npm run design:lint`＋`npm run design:check` 全绿（upgrade-carry 原型已先行）

## 6. P2 前端：候选快照降频

- [ ] 6.1 `carryStore.ts`：`refreshCarry({ auto })`＋会话级「无待办」标记（无可搬运待办即挂载自动刷新跳过；force 绕过并清标记）；`useLegacyDb.ts` 书架挂载改传 auto；验证＝vitest「无待办→二次挂载零请求／force 恢复请求／搬运终局后 force」
- [ ] 6.2 存量测试修补（carryDialog/novelListPage 等对挂载拉取次数的断言）；验证＝前端 vitest 全绿＋coverage 阈值过

## 7. 回归

- [ ] 7.1 双端类型与全量门禁；验证＝后端 `ruff`＋pytest 全绿；前端 `tsc --noEmit`＋vitest＋`npm run coverage` 全绿
- [ ] 7.2 e2e 受影响面（书架挂载、迁移弹层既有用例）；验证＝e2e 相关 spec 通过，存量红单独列名不新增
- [ ] 7.3 review-agent 全量审查（boss 判例：feature PR 合入前必过）；验证＝review 结论归档、findings 收口

## 8. 真机走查与清池

- [ ] 8.1 本机装新包，记录 43 槽基线：书架打开体感＋app.log 中 `candidates`/`novels` 时延；验证＝基线数字入账
- [ ] 8.2 走整理入口：先「备份一份」→ 归档链上槽（0.48.2/0.49.0 等）→ 复测书架打开与并发时延；验证＝43 槽收敛到活跃槽＋链尾，耗时回亚秒级，数字入账
- [ ] 8.3 走查「8 本软删书」结论回告（均不恢复，维持 3 本 active 口径）；验证＝用户确认记录
