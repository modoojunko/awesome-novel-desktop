# dev 哨兵分流件纳入迁入候选——补形状枚举盲区

## Why

首启状态机对「指纹不符但可读」的库按可读性分流（`*.mismatch-<stamp>`），spec 明文「该件 SHALL 作为候选参与找回」（db-generation「库文件版本命名与首启状态机」）。但候选扫描的白名单形状枚举只认 `novel-v{X}.db.mismatch-*`，**dev 哨兵构建（无版本语义）实际产出的分流件是 `novel-dev.db.mismatch-*`**——不在任何白名单形状里，`parse_db_filename` 判 None，候选扫描永远扫不到：UI 无候选、找回向导无入口，「看起来丢书」且产品内无任何自救通道。

实锤案例（2026-09-24）：作者日常用 dev 栈写书，代码换代后换新栈启动，书库被分流成 `novel-dev.db.mismatch-*`，书架清空；最终靠**手工改名**成 `novel-v0.0.db.mismatch-*` 借形状让迁入引擎认到才找回。缺口是结构性的——每个 dev 栈用户换代都会踩。

## What Changes

- **`schema_version.parse_db_filename` 补哨兵分流件形状**：新增 `novel-dev.db.mismatch-<stamp>`（kind=`mismatch`、version=None——排序按既有 `version_sort_key(None)` 全域垫底，与「dev 哨兵垫底」口径一致）与 `novel-dev.db.corrupt-<stamp>`（kind=`corrupt`，对称认取，照旧不进候选、进只读诊断面）。stamp 字符集与既有 `_DISPOSED_RE` 同款。
- **候选扫描零改动**：`scan_migration_candidates` 只依赖 `parse_db_filename` 的 `is_candidate`（已含 `mismatch`）＋空壳过滤，形状认取后自动可见；迁移引擎（precheck/preview/start/列交集搬运）与清理端点的「候选白名单校验」同源受益，均零改动。
- **前端零改动**：`LegacyMigrateModal` 不消费 `version` 字段（展示文件名/书数/时间），`version=None` 无展示面。
- **spec 双 MODIFIED**（`db-generation`）：「迁入候选与找回向导」白名单枚举补哨兵分流件形状、corrupt 对称排除；「库文件版本命名与首启状态机」分流改名目标形状按构建形态分述（版本构建 `novel-v{X}.db.mismatch-*`／dev 哨兵 `novel-dev.db.mismatch-*`），钉死「同版本形状不符仍可带回」场景在 dev 下的产出形态。
- **测试**：`parse_db_filename` 新形状单测（mismatch/corrupt/残件回归）＋候选扫描集成用例（dev 分流件进候选、book_count 过滤仍生效），落 `tests/test_db_lifecycle.py`。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `db-generation`：「迁入候选与找回向导」候选白名单枚举补 `novel-dev.db.mismatch-*`（corrupt 对称排除）；「库文件版本命名与首启状态机」分流改名形状按构建形态分述，明文哨兵分流件 SHALL NOT 成为扫描盲区。

## Impact

- `client/backend/schema_version.py`（形状枚举一处＋正则一条）
- `client/backend/tests/test_db_lifecycle.py`（＋2～3 用例）
- `openspec/specs/db-generation/spec.md`（归档 sync 生效，两 requirement 各一处）
- 迁移引擎、候选扫描、前端、清理端点：零改动（单源形状枚举的下游全部自动受益）
