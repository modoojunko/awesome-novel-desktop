## ADDED Requirements

### Requirement: 上传型封面/头像工坊

前端 SHALL 提供上传型封面/头像工坊，使用阶段 1 的 `POST /api/novels/{id}/image-assets`、`GET .../image-assets`、`POST /api/image-assets/{id}/adopt`、`POST .../undo`、`DELETE /api/image-assets/{id}` 与 `GET .../links`。工坊 SHALL 显示候选、当前图、8 秒撤销倒计时；关闭未采用候选 SHALL 确认或明确“候选保留 24 小时”。采用/撤销后 SHALL 重新拉取书/角色 DTO，不把图片 URL 缓存超过 `url_expires_at`。

#### Scenario: 上传并采用封面

- **WHEN** 用户在书卡点“添加封面”，选择 PNG 上传
- **THEN** 工坊 SHALL 显示候选缩略图，点“使用”后书卡 SHALL 显示新封面，并出现 8 秒撤销入口

#### Scenario: 撤销采用

- **WHEN** 用户在 8 秒内点撤销
- **THEN** 前端 SHALL 调 undo 并刷新书/角色 DTO；超时后撤销入口 MUST 消失

#### Scenario: 签名链接过期

- **WHEN** 图片 URL 的 `url_expires_at` 已过或 `<img>` 返回 403
- **THEN** 前端 SHALL 调 `/image-assets/{id}/links` 换新链接一次，MUST NOT 无限重试

#### Scenario: 免费用户

- **WHEN** 免费用户打开工坊
- **THEN** 上传入口 SHALL 可用；生成/测试/批量入口 SHALL 显示 PRO 提示且不可点

### Requirement: 设置部分更新

前端 SHALL 用 `PATCH /api/novels/{id}/image-settings` 与 `PATCH .../characters/{cid}/image-settings` 做部分更新；只改模型/seed 时 MUST NOT 清空画风、封面描述或头像描述。未提交 `cover_seed` 时 MUST 保留旧值。

#### Scenario: 只换本书模型

- **WHEN** 用户在工坊页脚只切换图像模型
- **THEN** 画风、封面描述、cover_seed MUST 保持不变

#### Scenario: 只改头像 seed

- **WHEN** 用户只点“换一个”改 seed
- **THEN** avatar_prompt MUST 保持不变
