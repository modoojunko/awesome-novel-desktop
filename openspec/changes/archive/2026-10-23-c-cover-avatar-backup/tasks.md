# c-cover-avatar-backup · 任务

- [x] 1.1 `FORMAT_VERSION` 6 → 7；v6 旧包按无图像段正常导入
- [x] 1.2 资产包导出 `images/manifest.yaml` + full/thumb WebP（只带 current）
- [x] 1.3 manifest 带书级 `style/cover_prompt/cover_seed/image_model/image_config_name` 与角色级 `avatar_prompt/seed`
- [x] 1.4 配置包导出 `image_configs`（明文 Key）；导入按名字去重、重加密、唯一默认
- [x] 1.5 导入按角色 id 映射重绑头像；配置缺失置空绑定并 warning；哈希不符/缺变体跳过
- [x] 1.6 迁移引擎 `_reencrypt_dead_image_ciphertexts`；报告 `dead_api_keys`/`dead_image_keys`，保留 `dead_keys` 总数
- [x] 1.7 `test_backup_images.py` roundtrip 1 passed；`test_image_configs_key_reencrypted` 1 passed
- [x] 1.8 后端全量 2417 passed / 296 skipped；ruff 全绿
- [x] 1.9 实现 PR 同批 sync `backup-restore` delta 到主 spec 并归档
