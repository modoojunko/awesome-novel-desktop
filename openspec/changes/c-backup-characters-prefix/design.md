## Context

- `_dump_characters(zf, db, project)`（export.py:201）：无 prefix 参数，`zf.writestr("characters/characters.yaml" / "characters/relations.yaml", …)` 硬写包根；`dump_book_into` 调用点（export.py:113）不传前缀。
- 正确对照：`_dump_hooks(zf, db, project, prefix)`（export.py:251）写 `prefix + "hooks/hooks.yaml"`（实测 :298）。
- 导入端 `_import_characters`（importer.py:162-182）：只读 `f"{book_dir}characters/characters.yaml"`，v2 存在性判断，无包根回退。
- 单书路径（`kind=single` 与 `GET /novels/{id}/export`，prefix=""）读写成包根，因此 `test_backup_roundtrip.py:172`（单书包）全绿——缺陷只在整库多书路径。

## Goals / Non-Goals

**Goals:**
- 整库包每书角色段写入各自 `projects/{slug}/` 前缀；导入端零改动即可恢复。
- 先红后绿用例：修复前两书 `projects/*/characters/` 均缺失。

**Non-Goals:**
- 不做旧整库包的包根回退（多书语义不可判定，回退即错发——见 proposal Non-Goals）。
- 不动 v1 角色读窗、id 重映射、主角收敛等既有导入语义。

## Decisions

**1. 签名 `_dump_characters(zf, db, project, prefix: str = "")`，写入 `prefix + "characters/…"`；调用点传 `prefix`。**
与 `_dump_hooks` 完全同构；`novels/router.py:646` 的既有调用（单书布局）走默认值，零改动零风险。

**2. 回归口径 = 导出产物断言 + 导入恢复断言，双保险。**
① 整库导出后：两书前缀下角色文件均在、内容互异、包根无 `characters/`；**包根检查用 `namelist()` list 计数**（zip 保留重复条目，`set()` 会塌成 1 掩盖「两书写同根」的实证形态）。② 导入恢复：走 `test_backup_roundtrip.py` 既有 harness——`_import_single_book(db, zipfile.ZipFile(path), f"projects/{slug}/", uid)` **逐书直调**（跳过 parse/reattach，导入端本 change 零改动，足够覆盖 `{book_dir}` 读口径）；断言**角色姓名集合逐书相等**（而非仅计数——两书计数相同则「最后一本发给每本书」可蒙混过关）。先红断言：修复前 ① 必红（两书前缀下文件缺失 + 包根 2 条重复），② 必红（两书角色均为空）。

替代方案：写包根 + 导入端加「单书回退、多书报错」——被否，语义修正应落在导出端一处，导入端发明回退只会把错误形态固化进契约。

## Risks / Trade-offs

- [多人协作期的旧整库包] → 旧包本就不恢复角色（导入端读不到），修复不改变旧包行为；救援路径已登记（单书导出配方）。
- [断言的包根检查] → 断言同时检查「包根无 characters/」防未来回归成双写。

## Migration Plan

`_dump_characters` 签名默认值向后兼容；一次 commit（修复＋用例）；随下次发版带出。回滚 = revert，无状态残留。

## Open Questions

无。
