## Why

用户实绩（2026-10-08）：删除配置后新建同名配置报「名称已被使用」，体感是「数据库没删干净」。

根因＝删除是软删（`status="deleted"`，行保留——支撑前端 8 秒「撤销删除」），而 `api_configs` 有 DB 级 `(user_id, name)` 唯一约束（`uq_api_configs_user_name`），软删行把名字永久占死：撤销窗口一过期，重建/改名到这个名字必然被一行任何列表都看不到的 tombstone 堵死。原实现（测试 TC-SOFT-04）把「软删后同名重建 409」钉成了故意行为（tombstone 永久占名），本次按用户反馈翻转口径。

## What Changes

- **口径翻转**：活跃（`status != "deleted"`）重名照旧 409；名字只被软删行占着时，旧行自动改名让位（`{原名}（已删除 {行id}）`，嵌行主键保证唯一、用户不可见），新建同名与改名到该名放行。
- **撤销语义不变**：窗口内行原样保留、restore 照常复活原名；极端序（删→重建同名→又点撤销）复活行以让位名与新配置并存。
- **朱雀保留名豁免**：`vendor="zhuque"` 行不参与让位——「朱雀 AI 检测」任何状态撞名一律 409（`get_zhuque_config` 按 name+vendor 单槽位查行，名字被借走＝朱雀行永久查不到）。
- **约束兜底**：create/update 路由对 `IntegrityError` 回滚转 409（治让位名与字面名相撞的构造态 500 与 check-then-act 交错窗）。
- **输入契约补齐**：`UpdateApiConfigBody.name` 补 min/max_length（与 create 同契约，1–100）。
- 重名判定收进 `_assert_name_available` 单点（create/update 同源）；让位 UPDATE 在 helper 内显式 `flush()` 分批（SQLite 唯一约束逐行检查，同批自撞判例）。

## Impact

- **Specs**：`model-api-config` ADDED「配置删除撤销与名称让位」（主 spec 此前无删除/撤销 Requirement）。
- **Code**：`client/backend/api_configs/service.py`（helper＋create/update）、`router.py`（IntegrityError 兜底）、`schemas.py`（update name 长度）。
- **Tests**：`tests/test_api_key_config.py` TC-SOFT-04 翻转＋TC-SOFT-05/06/07/08/09 新增。
