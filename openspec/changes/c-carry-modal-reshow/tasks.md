# c-carry-modal-reshow — tasks

## 1. 指纹数据件化（schema_version）

- [x] 1.1 新增 `data_file_mtime`/`data_file_size`（主文件＋`-wal`；`-shm` 退出），docstring 记真机判例与实勘依据
- [x] 1.2 `candidate_stamp` 切数据件形态；新增 `candidate_stamp_legacy`（旧三件套形态，仅供存量记录对拍）
- [x] 1.3 `three_file_mtime`/`three_file_size` 收窄为 legacy 专用（docstring 注明）；`snapshot_signature`（拷贝一致性守卫）不动——`-shm` 活动是「旧版还在写」的有效信号

## 2. 扫描载荷与清单零接触（db_lifecycle）

- [x] 2.1 `scan_migration_candidates` 的 mtime/size 字段切数据件形态；每项增列 `stamp_legacy`
- [x] 2.2 `candidate_manifest` 对 WAL 库走暂存复检（`_is_wal_mode`→`copy_sidecars`→`prepare_staged`→副本只读），非 WAL 直接只读；查询体抽 `_manifest_rows` 共用

## 3. 双形态对拍（migration/router）

- [x] 3.1 `candidates()`：carried/suppressed 按 {stamp, stamp_legacy} 集合命中
- [x] 3.2 `_migrated_stamps()`：数据件未变时把旧形态记录换算成现行指纹进清理白名单；变了保守放行原串（对不上＝不可删）

## 4. 回归测试（修复前代码三针全红自证）

- [x] 4.1 全链：带边车候选 start→done→`-shm` 漂移→carried/suppressed 仍真（`TestCarryModalReshow`）
- [x] 4.2 manifest 跨进程零接触：子进程读清单，源三件套 sha+mtime_ns 不变（同进程读者测不出违例，实勘注记在用例内）
- [x] 4.3 双形态对拍单测：旧形态完成记录 carried 真／数据件漂移双假（test_migration_snooze）
- [x] 4.4 指纹单测：`-shm` 漂移不动指纹／`-wal` 写动指纹／无边车新旧同串（test_db_lifecycle）

## 5. 门禁

- [x] 5.1 后端全量 pytest 绿（1917 passed, 0 failed）＋ ruff 干净
- [ ] 5.2 CI 双绿（push 后看 run）
- [ ] 5.3 真机验收：测试同学机器升级到修复版——告知卡不再复弹、旧文件仍在、清理入口可达
