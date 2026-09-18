## 1. 修复与回归

- [x] 1.1 `backup/export.py::dump_book_into`：把**卷循环内的归档块**（书级 `Archive join Chapter` 查询、`for arch in archives:` 写入、`manifest_archives` 追加）整块移到卷循环之后；归档查询补 `.join(Volume).order_by(Volume.volume_no, Chapter.chapter_no)`；`put`/`put_yaml` 闭包与命名不变——验证：`pytest tests/test_backup_export.py -q` 全绿
- [x] 1.2 新增多卷书种子用例（2 卷 × 每卷 1 章 × 每卷 1 归档，整库 `kind=backup`）：断言按 design.md 决策 2 的形态——**`namelist` list 计数**过滤 `projects/{slug}/archives/*.md` 恰 2（修复前 4，必红；勿用 set）、manifest `archives` 恰 2 条且 `filename` 去重后仍 2、字段集 `{filename, ref, title, summary, archived_at}` 不变——验证：先在修复前代码上跑出红（先红后绿）
- [x] 1.3 新增 1 卷 1 归档用例（对接 spec「单卷书行为不变」scenario）：条目名/`zf.read` 内容字节/manifest 字段集与既有口径一致；并回归 `tests/test_backup_roundtrip.py`（1 卷 1 归档，层 7 可顺手扩断言）——验证：全绿
- [x] 1.4 单飞机制回归：`pytest tests/test_manuscript_download.py -q`——下载成稿与备份**共用 `job_runner` 单飞骨架**（不经 `dump_book_into`），验证修复不扰任务互斥——验证：全绿

## 2. 门禁

- [x] 2.1 后端全量（CI 同口径，cwd=`client/backend`）：`ruff check .` 与 `python -m pytest tests/ -q --timeout=30` 全绿——验证：零新增告警、零失败
- [x] 2.2 双 validate 门禁（当前可跑）：`openspec validate c-backup-archive-dedup --strict` 与 `openspec validate backup-restore --strict` 均通过
- [x] 2.3 归档期判据（归档 PR 时勾）：`grep -c "### Requirement: 归档段唯一性与完整性" openspec/specs/backup-restore/spec.md` = 1、既有 requirement 全在（`grep -c "### Requirement:"` = 7）
