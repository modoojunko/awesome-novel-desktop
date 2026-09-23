## 1. 双端影响判定与前置核查

- [ ] 1.1 双端影响判定：本 change 纯 C端 后端（打戳/清理/备份白名单/CI/死表/时间口径），界面行为口径收紧但无视觉变更、不触共享段——Design Impact 判定为「不适用」，无需原型先行
- [ ] 1.2 前置核查：codegraph `callers VolumeCastMember` 与全仓 grep 确认零消费方；grep `planned_volume_no` 确认前端无展示依赖——结果贴进 change 目录

## 2. 打戳失败可见化

- [ ] 2.1 `main.py` 打戳 `except SQLAlchemyError: pass` 改为 error 级日志（含库路径与异常摘要，不含凭据）——diff 贴进 change 目录
- [ ] 2.2 新增测试：模拟打戳写入失败（只读/异常注入）断言 error 日志出现且启动不中断——`pytest client/backend/tests -k stamp` 绿
- [ ] 2.3 正常路径回归：打戳成功不产生 error 噪声——同测试文件断言

## 3. 清理门下沉后端

- [ ] 3.1 `migration/router.py` 的 history 条目补记 `book_count_source`/`tables_skipped`/`fk_violations`（从本次 report 取）——diff 贴进 change 目录
- [ ] 3.2 `db_lifecycle.deletable_candidates` 收窄为 `migration.last.source_stamp` 且完整性校验通过；老条目缺字段按不完整处理——diff 贴进 change 目录
- [ ] 3.3 新增/更新测试：半途搬运（整表跳过）后做一次干净搬运，断言待删清单不含半途源、只含本次源——`pytest client/backend/tests -k cleanup` 绿
- [ ] 3.4 前端 `LegacyMigrateModal.cleanupEligible` 三条件门保留为展示层（判定不再依赖它）——diff 贴进 change 目录

## 4. 备份白名单补 planned_volume_no

- [ ] 4.1 `export._dump_hooks` payload 与 `importer._hook_row_fields` 同批补 `planned_volume_no`（可空，缺失按空）——diff 贴进 change 目录
- [ ] 4.2 `test_backup_roundtrip.py` 的键集完全相等断言改为「必含键 + 新键存在」——断言 diff 贴进 change 目录
- [ ] 4.3 反向验证：临时移除 4.1 的补键跑 4.2 断言，确认测试变红——红→绿过程记录在 change 目录

## 5. 验收门进 CI

- [ ] 5.1 `.github/workflows/e2e-scheduled.yml` 的 e2e 步骤补 `UP11_DATA_DIR`（指向 docker 栈宿主挂载点），确认 `db-version-upgrade.spec.ts` 不再整组 skip——本地/CI 日志贴进 change 目录
- [ ] 5.2 `upgrade_drill version-chain` 接入 nightly（或打包流水线），记录一次实际执行结论——输出贴进 change 目录

## 6. 死表与契约键登记

- [ ] 6.1 删除 `models/volume.py` 的 `VolumeCastMember` 模型与 relationship（含 `lazy="selectin"` 空查）——`pytest client/backend/tests` 全量绿
- [ ] 6.2 导出 YAML `cast_members` 键名保留理由登记在 change 目录（外部消费方 + 形状已从 {who,target,change} 变聚合 {name,role}）

## 7. 时间口径清理（C端）

- [ ] 7.1 `db_lifecycle.py`、`migration/engine.py`、`backup/export.py`（46/67/323）5 处裸 `datetime.now()` 改 `datetime.now(UTC).replace(tzinfo=None)`——`grep -rn "datetime.now()" client/backend` 零命中（`_now_iso` 的 aware 写法除外）
- [ ] 7.2 相关测试回归：备份导出/迁移命名测试绿

## 8. 找回向导两处对齐（复审新增）

- [ ] 8.1 单候选自动预演直跳 preview 时，隔离件只读清单不可达（只在发现步渲染）——补「preview 步可见隔离件清单」或调整跳转，使规格「损坏库只读可见」的直接路径成立——diff + 截图路径贴进 change 目录
- [ ] 8.2 与 `c-chapter-plan-guards` 的 409 判定改动对账：确认搬运发起失败的冲突识别已按 HTTP 409（该题在 C5 tasks 6.1 落地，此处只做交叉验证）——对账结论贴进 change 目录

## 9. 回归

- [ ] 9.1 `pytest client/backend/tests`（全量）输出结论贴进 change 目录
- [ ] 9.2 定向 e2e：升级向导（找回/带回/清理）与备份恢复用例在隔离 docker 栈通过——结论与截图路径贴进 change 目录
- [ ] 9.3 本 change 无前端改动，`npm run design:lint`/`design:check`/`tsc` 不适用（判定依据见 1.1）
