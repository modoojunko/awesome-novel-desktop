# 图像资产备份 v7（c-cover-avatar-backup）

## Why

阶段 1 把封面/头像和图像配置存进 SQLite 后，旧备份格式（v6）只带 YAML 与写作 `api_configs`：换机/恢复会静默丢图、丢图像 Key；同机升级搬库时 `image_configs.api_key` 也不会重加密。带图版本发布前必须补上这条持久化链路。

## What Changes

- `FORMAT_VERSION` 6 → 7。
- 资产包每书新增 `images/manifest.yaml` + `images/{asset_id}-full.webp` / `-thumb.webp`，只带 `current` 资产；manifest 含书级 `style_key/cover_prompt/cover_seed/image_model/image_config_name`、角色级 `avatar_prompt/seed` 和资产元数据。
- 配置包新增 `image_configs` 段（明文 Key 导出，导入按目标库钥匙重加密）；导入按名字去重、默认唯一。
- 导入按角色 id 映射重绑头像；找不到配置时置空绑定并写 warning；旧 v6 包无图像段时正常跳过。
- 迁移引擎密钥转接覆盖 `image_configs`，报告新增 `dead_api_keys`/`dead_image_keys`，保留 `dead_keys` 总数兼容旧消费方。
- 新增 roundtrip 测试：图片/设置/配置导出→导入、Key 重加密。

## Capabilities

### Modified Capabilities

- `backup-restore`: 图像资产、书/角色图像设置和图像配置随包；v7 格式与迁移 Key 转接。

## Design Impact

- 受影响端：C端后端备份/恢复/迁移；不改 S端、不改前端协议。
- 数据：v7 包新增 `images/` 段与 `image_configs` 配置段；v6 旧包兼容。
- 发布门禁：v7 roundtrip 通过前带图版本不得发布。

## Impact

- `client/backend/backup/format.py`、`backup/export.py`、`backup/importer.py`
- `client/backend/migration/engine.py`
- `client/backend/tests/test_backup_images.py`、`tests/test_migration_engine.py`
- `openspec/specs/backup-restore/spec.md`（sync 时）
