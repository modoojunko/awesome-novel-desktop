## 1. 修复与回归

- [ ] 1.1 新建 `client/backend/archive/naming.py`（design 决策 1 的公式原样：分隔符→`-`、连续点收敛、**截断后**剥首尾点）；`archive/router.py` 三函数改从 naming 导入并保留 `_slugify`/`_archive_filename`/`_parse_archive_filename` 别名；`archive/service.py:55` 内联副本删掉、`archive_path` 改 `archive_filename(chapter_ref, title)`——验证：`grep -n "replace(\" \", \"-\")" client/backend/archive/*.py` 仅剩 naming.py 一处
- [ ] 1.2 单元参数化（先红后绿）：四行实证表（`上/下`→`上-下`、`上/../下` 无 `/`\\`/`..`、`第1..2章`→`第1.2章`、`"a"*49+"."` 全名无 `..` 且 parse 非 None）+ 截断边界 `"a"*49+".bcdef"` + `第1章.`/`.x`/空串/纯空格/`a\\b` + **普通标题零漂移**（含 50 字窗口无点标题）——验证：修复前前三项必红
- [ ] 1.3 端到端（先红后绿）：危险标题（`上/../下`）书 → 备份导出 → 条目名无分隔符、`".." not in name` 且 `".." not in Path(name).parts`、`validate_paths(zf)` 通过、`parse_archive_filename(basename)` 非 None；导入空库 → title == 完整条目名 stem（既有语义，非被截断尾段）——验证：修复前导出即产 `..` 段必红
- [ ] 1.4 写接口同源用例：归档 POST 响应 `archive_path` basename == 列表 `filename`（复用 `test_archive_free.py:161-175` 模式；`第1..2章` 标题）——验证：半修（只改 router 不改 service）时必红
- [ ] 1.5 回归：`test_archive_free.py`、`test_backup_export.py`、`test_backup_roundtrip.py`——验证：全绿

## 2. 门禁

- [ ] 2.1 cwd=`client/backend`：`ruff check .` 与全量 `pytest tests/ -q` 全绿
- [ ] 2.2 `openspec validate c-archive-filename-safety --strict` 通过；归档期判据（归档 PR 勾）：主 spec 追加后 `grep -c "### Requirement: 归档条目名安全字符集" openspec/specs/backup-restore/spec.md` = 1
