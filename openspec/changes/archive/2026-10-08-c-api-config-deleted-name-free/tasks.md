## 1. 实现（client/backend/api_configs）

- [x] 1.1 `service.py`：重名判定收进 `_assert_name_available`（活跃重名 409＋软删行让位改名 `{原名[:40]}（已删除 {行id}）`＋朱雀行豁免＋末尾显式 flush）；`create_api_config`/`update_api_config` 同源调用。
  - 回执：✅ 初版 a4895bcc；朱雀豁免为评审 P1 整改（b211bcdd）。
- [x] 1.2 `router.py`：create/update 补 `IntegrityError` → 回滚 → 409 兜底。
  - 回执：✅ 评审 P2 整改（b211bcdd）。
- [x] 1.3 `schemas.py`：`UpdateApiConfigBody.name` 补 `min_length=1, max_length=100`（与 create 同契约）。
  - 回执：✅ 评审 P2 整改（b211bcdd）。

## 2. 测试（tests/test_api_key_config.py）

- [x] 2.1 TC-SOFT-04 口径翻转：软删后同名重建放行，旧行确认仍软删在库但已让名。
  - 回执：✅ a4895bcc。
- [x] 2.2 TC-SOFT-05 重建同名后 restore：两配置并存、名字互不冲突。
- [x] 2.3 TC-SOFT-06 改名到软删占名放行＋让位名形态钉子（曾以「组合跑红、单跑绿」复现同批自撞，本用例钉 update 路径 flush 分批）。
- [x] 2.4 TC-SOFT-07 双重让位（删→建同名→再删→第三次重建）。
- [x] 2.5 TC-SOFT-08 朱雀保留名不参与让位（软删朱雀行占名时同名普通配置 409）。
- [x] 2.6 TC-SOFT-09 让位名与字面名相撞 → 约束兜底 409 不出 500。
- [x] 2.7 全量回归：后端 2076 passed / 1 skipped；ruff 0.16.3（钉版）干净；实现 PR #746 与评审整改批 CI 双绿。
  - 回执：✅ 合入 main = d9fc6a46（2026-10-08）。
