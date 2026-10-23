# c-cover-avatar-backup · 设计

## Decisions

- **只备份 current**：candidate/previous 是 24h/8s 运行态，不随包；恢复后 current 直接成为当前图。
- **manifest 单源**：每书 `images/manifest.yaml` 记录书/角色设置与资产元数据；BLOB 用 `asset_id-variant.webp` 命名。
- **按名字恢复配置**：`book_image_settings` 不存配置名，manifest 写 `image_config_name`，导入按目标用户 active 配置名查找；找不到置空并 warning，不静默指向不存在 id。
- **角色重映射**：复用 `_import_characters` 的 id 映射；头像 character_id 同步重绑，封面强制空 character_id。
- **v6 兼容**：`FORMAT_VERSION=7`；v6 包无 `images/` 段，导入端跳过，不报错。
- **迁移 Key**：`image_configs` 与 `api_configs` 共用 Fernet 钥匙；转接分表统计，`dead_keys` 保留总数兼容旧 UI。

## Risks

- 备份包体积随封面/头像增长；只带 current 控制上限。
- 旧版应用（≤6）读取 v7 包会被版本闸拒绝，符合“删键/改布局升版”规则。
