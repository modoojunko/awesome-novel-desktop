## MODIFIED Requirements

### Requirement: 图像资产与图像配置随包（v7）

备份格式 SHALL 从 v6 升至 v7，资产包每书 SHALL 包含 `images/manifest.yaml` 与 current 封面/头像的 full/thumb WebP；manifest SHALL 记录书级 `style_key/cover_prompt/image_model/image_config_name`、角色级 `avatar_prompt` 与资产业务元数据。配置包 SHALL 新增 `image_configs` 段（导出明文 Key，导入按目标库钥匙重加密）。旧 v6 包无图像段时导入 SHALL 正常跳过，MUST NOT 报错；v7 包多出已退役的 `cover_seed`/`seed` 键时导入 SHALL 静默忽略，MUST NOT 报错。

#### Scenario: 封面头像跨机恢复

- **WHEN** 用户导出含 current 封面和头像的 v7 资产包，并在新库导入
- **THEN** 两本书的 current 资产、full/thumb BLOB、书级画风/描述与角色头像描述 MUST 原样恢复；seed 不随包迁移（新库按书/角色 id 派生）

#### Scenario: 图像配置 Key 重加密

- **WHEN** 导入 v7 配置包里的 `image_configs`
- **THEN** 明文 Key MUST 按目标库当前 Fernet 钥匙重加密；导入后能解密回原值

#### Scenario: 旧包无图像段

- **WHEN** 导入 v6 或更早包
- **THEN** 图像段缺失 MUST 被跳过，书/角色恢复不受影响

#### Scenario: 旧版 v7 包含种子键

- **WHEN** 导入早期 v7 包（manifest 带已退役的 `cover_seed`/`seed` 键）
- **THEN** 导入 SHALL 成功且忽略这两键，MUST NOT 报错或告警

#### Scenario: 迁移图像 Key

- **WHEN** 同机升级搬库且源库有 `image_configs`
- **THEN** 目标钥匙解不开的行 MUST 用源库钥匙转接；报告 SHALL 给出 `dead_api_keys` 与 `dead_image_keys`，`dead_keys` 保留总数兼容

#### Scenario: 发布门禁

- **WHEN** 准备发布带图版本
- **THEN** v7 roundtrip（封面+头像+设置+配置 Key）MUST 通过；未通过 MUST NOT 发布
