## 1. 修复与回归

- [x] 1.1 `_dump_characters` 补 `prefix: str = ""` 参数、两个写入改 `prefix + "characters/…"`；`dump_book_into` 调用点传 `prefix`——验证：`pytest tests/test_backup_export.py tests/test_backup_roundtrip.py -q` 全绿
- [x] 1.2 新增整库两书角色用例（先红后绿）：两本各有角色的书 → `kind=backup` 导出 → 断 `projects/{slugA}/characters/characters.yaml` 与 `projects/{slugB}/…` 均在且内容互异、包根无 `characters/`——验证：修复前必红（文件缺失）实测
- [x] 1.3 导入恢复对拍：整库包导入空库 → 两书角色数/关系数逐书与源一致——验证：新用例全绿（先红按 1.2 覆盖导出侧；导入侧红=角色为 0）
- [x] 1.4 回归：`test_backup_roundtrip.py`（单书包）、`tests/test_backup_characters.py`、升级演练（`test_zz_disaster_recovery_drill.py`）——验证：全绿

## 2. 门禁

- [x] 2.1 cwd=`client/backend`：`ruff check .` 与全量 `pytest tests/ -q` 全绿
- [x] 2.2 `openspec validate c-backup-characters-prefix --strict` 通过（当前可跑）
- [ ] 2.3 `openspec validate c-backup-characters-prefix --strict` 通过；归档期判据（归档 PR 勾）：主 spec 追加本需求后 `grep -c "### Requirement: 多书包每书段落位置（prefix 纪律）" openspec/specs/backup-restore/spec.md` = 1
