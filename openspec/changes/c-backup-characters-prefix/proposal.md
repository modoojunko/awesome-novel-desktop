## Why

`backup/export.py::_dump_characters` 是全部导出段里**唯一**不接「每书前缀」的：函数签名无 `prefix` 参数，`zf.writestr("characters/characters.yaml", …)` 硬写包根（对比 `_dump_hooks(zf, db, project, prefix)` 为正确写法）。整库资产包（`kind=backup`，每书位于 `projects/{slug}/`）里，导入端 `_import_characters` 只读 `{book_dir}characters/characters.yaml`（`importer.py:175`，**无包根回退**）——于是：

- **整库包恢复时每本书的角色段全部丢失**（导入端找不到文件、静默跳过）；
- 导出侧各书的角色文件在包根互相覆盖（只留最后一本），文件本身也是错位产物；
- 单书交付导出（`kind=single`，prefix=""）与 `GET /novels/{id}/export` 根路径一致，**不受影响**——这也解释了为何 `test_backup_roundtrip.py`（走单书路径）全绿而缺陷存活。

来源：`todo.md` 第 17 行 ②（foreshadow-settings-v2 会话发现登记），本 change 即该挂起专项的跟进（与 c-backup-archive-dedup 同族：导出段 prefix 纪律）。

## What Changes

- **`_dump_characters` 补 `prefix` 参数**（默认 `""`，保持单书调用方零改动），两个条目名改为 `prefix + "characters/…"`；`dump_book_into` 调用点传 `prefix`——与 `_dump_hooks` 同款写法。
- **导入端零改动**：`_import_characters` 的 `{book_dir}` 读取口径本来就是对的；旧整库包（角色写在包根）维持现状语义（本来也恢复不出角色），不引入把「最后一本的角色发给每本书」的错误回退。
- 契约化：backup-restore 新增「多书包每书段落位置」需求——资产包内全部书级段落（settings/chapters/versions/prompts/archives/characters/hooks）SHALL 位于各书 `projects/{slug}/` 前缀下；单书交付导出为包根；导入端逐书读取，SHALL NOT 跨书混用。
- 无用户可见界面改动；前端/接口零改动。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `backup-restore`: 新增「多书包每书段落位置（prefix 纪律）」需求——锁定本缺陷的回归口径（两本各有角色的书：导出后两书角色文件均在各自前缀下、内容各异；导入后每书角色数与源一致）。

## Impact

- 代码：`client/backend/backup/export.py`（`_dump_characters` 签名 + 两处写入 + 一个调用点；`novels/router.py` 的调用点走默认值不受影响）。
- 测试：新增整库包两书角色用例（先红后绿：修复前 `projects/*/characters/` 均缺失）；补一条整库包导入恢复断言（角色计数逐书对拍）；既有 roundtrip/演练回归。
- 兼容性：新导出的整库包自此可恢复角色；旧整库包行为不变（本就丢角色）；`format_version` 不变（路径修正非布局变更——布局契约一直是 `projects/{slug}/`，此为对齐）。

## Non-Goals（显式排除）

- 不为旧整库包做包根角色回退（多书场景语义不可判定：包根只留最后一本，回退即错发）；如需救援单书内容，用`c-backup-archive-dedup` 归档中已记录的「旧代码对留档库单书导出」配方。
- `_dump_characters` 无角色时提前 return 的行为保持不变（空段不产文件，导入端本就判存在性）。
