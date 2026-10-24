# cover-avatar Specification

## Purpose
封面与角色头像：图像模型配置独立于写作模型，封面/头像资产入库、上传/采用/撤销/签名读取，书卡与角色页就地展示，并为阶段 3 的生成链路保留 prompt 与 seed 契约。

## Requirements

### Requirement:### Requirement: 图像配置与写作配置隔离

系统 SHALL 将图像模型配置存于独立 `image_configs`，MUST NOT 让图像配置出现在写作模型列表、写作就绪判定或写作 AI 兜底选择中。Key SHALL 复用本地加密存储；列表响应 MUST 只回掩码 Key。第一条 active 配置 SHALL 自动成为默认；删除或恢复配置后系统 SHALL 保持“有 active 配置就有且只有一个默认”的不变量。

#### Scenario: 只有图像 Key 时写作仍不可用

- **WHEN** 用户只配置了图像模型、没有写作模型
- **THEN** 写作 AI 就绪判定 MUST 仍为未配置，写作端点 MUST NOT 选中图像配置

#### Scenario: 图像配置软删后可同名重建

- **WHEN** 用户删除一个图像配置并立即新建同名配置
- **THEN** 系统 SHALL 复活原行（保留 id）或明确拒绝，MUST NOT 触发数据库唯一约束 500

#### Scenario: 软删配置可列出并恢复

- **WHEN** 用户请求 `GET /api/image-configs?include_deleted=true`
- **THEN** 响应 SHALL 同时包含 active 与 deleted 行，并带 `status`；deleted 行 MAY 通过 restore 端点恢复

#### Scenario: 删除默认配置后自动补默认

- **WHEN** 用户删除当前默认配置且仍有其他 active 配置
- **THEN** 系统 SHALL 把另一个 active 配置设为默认；若已无 active 配置则默认为空

#### Scenario: 软删配置解绑书

- **WHEN** 用户删除一本书正在绑定的图像配置
- **THEN** 该书 `image_config_id` MUST 被清空，后续读取设置 MUST NOT 指向已删除配置

### Requirement:### Requirement: 授权与所有权

系统 SHALL 在角色、图像资产、图像设置与 prompt 预览端点上校验书属于当前用户。MUST NOT 仅凭 `project_id`/`character_id`/`asset_id` 返回或修改其他用户的数据；越权读取 MUST 返回 404 或 400，越权写入 MUST 不产生任何落库。

#### Scenario: 跨用户读角色列表

- **WHEN** 用户 A 用用户 B 的 `project_id` 请求角色列表或角色详情
- **THEN** 系统 MUST 返回 404，且不返回任何角色卡或头像签名 URL

#### Scenario: 跨用户删角色

- **WHEN** 用户 A 对用户 B 的角色卡发 DELETE
- **THEN** 系统 MUST 返回 404，角色卡与该角色头像资产 MUST 保持原样

#### Scenario: 跨用户采用资产

- **WHEN** 用户 A 对用户 B 的 `asset_id` 发 adopt
- **THEN** 系统 MUST 视为资产不存在并返回 400，不改变原资产状态

### Requirement:### Requirement: 资产上传与规范化

系统 SHALL 接收 JPG/PNG/WebP 上传，按封面 768×1024、头像 512×512 做等比缩放＋居中 cover-crop，重编码 WebP，并生成缩略图。单张 MUST ≤10MB、≤30MP、边长 ≤4096；解码失败/超限/格式不支持 MUST 返回带 `code` 的可读 4xx。

#### Scenario: 上传封面

- **WHEN** 用户上传一张 800×600 PNG 作为封面
- **THEN** 系统 SHALL 返回 `asset_id`、full/thumb 签名链接，宽高为 768×1024，内容类型 image/webp

#### Scenario: 头像必须绑定角色

- **WHEN** 用户上传 kind=avatar 但未提供 character_id
- **THEN** 系统 MUST 返回 400，不落资产

#### Scenario: 拒绝非图片格式

- **WHEN** 用户上传 GIF/BMP/TIFF
- **THEN** 系统 MUST 返回 400 `unsupported_format`，不落资产

### Requirement:### Requirement: 资产状态机、TTL 与清理

系统 SHALL 把新上传资产置为 `candidate`，`expires_at=24h`；只有 `candidate` 可被 adopt。采用时 SHALL 把旧 `current` 置 `previous`（`expires_at=adopted_at+8s`）、删除更早 `previous`、给新 current 写 `undo_token` 与 `undo_expires_at=adopted_at+8s`。撤销 MUST 在 8 秒内且 token 匹配时恢复 previous；首次采用撤销 SHALL 删除 current 回无图状态。启动期 SHALL 全库 sweep 过期 candidate/previous；上传与采用前 SHALL 按用户 sweep。并发状态冲突 MUST 返回 409 `asset_state_conflict`，MUST NOT 500。

#### Scenario: 连续采用两张

- **WHEN** 用户采用第二张封面
- **THEN** 第一张变为 previous，第二张 version+1 成为 current；撤销第二张后第一张回到 current

#### Scenario: 候选过期后不能采用

- **WHEN** 用户对 `expires_at` 已过的 candidate 发 adopt
- **THEN** 系统 MUST 返回 409 `asset_expired`，不改变任何资产状态

#### Scenario: 撤销窗口过期

- **WHEN** 用户在当前图的 `undo_expires_at` 之后发 undo
- **THEN** 系统 MUST 返回 409 `undo_expired`，MUST NOT 删除或恢复资产

#### Scenario: 重复采用 current/previous

- **WHEN** 用户对状态为 current 或 previous 的资产发 adopt
- **THEN** 系统 MUST 返回 409 `asset_not_candidate`，不删除该资产、不 500

#### Scenario: 启动清理过期资产

- **WHEN** 应用启动时库里存在过期 candidate 或超过撤销窗口的 previous
- **THEN** 系统 SHALL 删除其元数据与 full/thumb BLOB

### Requirement:### Requirement: 采用、撤销与签名读取

系统 SHALL 用签名 URL 提供图片读取，签名覆盖 asset、variant、exp；过期/坏签名 MUST 返回 403。响应 SHALL 带 `X-Content-Type-Options: nosniff`，缓存 MUST 短于签名有效期，MUST NOT 使用 `immutable`。

#### Scenario: 坏签名读取

- **WHEN** 请求图片时 sig 被篡改
- **THEN** 系统 MUST 返回 403，不返回图片字节

#### Scenario: 签名过期后缓存不装死

- **WHEN** 浏览器缓存了一张签名图片
- **THEN** `Cache-Control` 的最大缓存时间 MUST 小于签名 TTL，使前端能在过期前重新取链接

### Requirement:### Requirement: 资产列表与候选查询

系统 SHALL 提供按书列出资产的端点，支持 `kind`、`character_id`、`status`、`limit` 过滤。列表 MUST 只返回当前用户、当前书的资产，MUST NOT 返回已过期 candidate/previous；`status` 非法 MUST 返回 400 `invalid_status`。系统 SHALL 提供 `GET /api/image-assets/{id}/links` 刷新签名链接，以及 `DELETE /api/image-assets/{id}` 丢弃 candidate/previous；current MUST NOT 被直接删除。

#### Scenario: 上传后查候选

- **WHEN** 用户上传一张封面后请求 `GET /api/novels/{id}/image-assets?kind=cover&status=candidate`
- **THEN** 响应 SHALL 包含该 `asset_id` 与签名链接

#### Scenario: 采用后候选列表移除

- **WHEN** 用户 adopt 某候选后再查 candidate 列表
- **THEN** 该 `asset_id` MUST 不再出现；查 `status=current` 时 SHALL 出现

### Requirement:### Requirement: 图与书/角色单一归属与 prompt 白名单

系统 SHALL 把封面归属到书、头像归属到角色；封面 prompt MUST 只读题材气质、核心承诺、世界舞台、用户 cover_prompt/seed；头像 prompt MUST 只读角色卡的性别/年龄/种族、外貌、势力/身份、一句话人设，并可继承书级 style_key/model/provider。MUST NOT 把书名、角色名、简介原文、正文、章纲、dossier.background、dossier.plot 送入图像 prompt；书名/角色名 SHALL 只出现在 `sources` 供 UI 叠加。prompt 预览端点 SHALL 返回 positive prompt、negative_prompt、prompt_hash、prompt_template_version、style_key、size、seed、candidate_seeds、model、provider、capabilities、sources。

#### Scenario: 头像不泄露角色背景

- **WHEN** 角色卡 background/plot 填了剧情剧透
- **THEN** 头像 prompt MUST 不包含这些字段，只包含外貌/身份/人设等白名单字段

#### Scenario: 书名不画成画面文字

- **WHEN** 书的名称是「夜明铺」
- **THEN** 封面 prompt MUST 不包含「夜明铺」；sources.name SHALL 仍返回书名供 UI 后置叠加

#### Scenario: prompt_hash 可复现

- **WHEN** 同一书/角色、同一模板版本、同一 prompt/negative/size/seed/model 再次预览
- **THEN** prompt_hash MUST 相同；只改 seed 或模型时 hash MUST 变化

### Requirement:### Requirement: 图像设置与种子读写

系统 SHALL 提供每书 `image_config_id/image_model/style_key/cover_prompt/cover_seed` 与角色 `avatar_prompt/seed` 的读写；绑定配置 MUST 属于当前用户且未删除。`PUT` 为全量写入；`PATCH` SHALL 只更新显式提交字段，未提交字段 MUST 保留。未显式提交 `cover_seed` 的 PUT MUST 保留旧值；style_key 不在支持列表 MUST 返回 400 `invalid_style`。

#### Scenario: 绑定不存在的配置

- **WHEN** 用户把书绑定到不属于自己的 image_config_id
- **THEN** 系统 MUST 返回 400，不写入设置

#### Scenario: PATCH 只改模型

- **WHEN** 用户 PATCH 只提交 `image_model`
- **THEN** `style_key/cover_prompt/cover_seed` MUST 保持原值

#### Scenario: 读回角色设置

- **WHEN** 用户保存角色 `avatar_prompt` 与 `seed` 后重新 GET 角色设置
- **THEN** 响应 SHALL 原样返回这两个字段

### Requirement:### Requirement: 书/角色接口就地携带图片，删除级联

系统 SHALL 在 `GET /api/novels`、`GET /api/novels/{id}`、`GET /api/novels/by-slug/{slug}` 返回 `cover`，在角色列表/详情返回 `avatar`；MUST NOT 要求前端先取 asset_id 再走统一元数据接口。删除书 SHALL 删除该书全部资产与 BLOB；删除或合并角色 SHALL 在同一事务内删除该角色的头像资产与 BLOB。

#### Scenario: 书架刷新直接拿到封面

- **WHEN** 用户打开书架
- **THEN** 每本书的响应直接含 `cover`（或 null），无需额外请求 `/image-assets`

#### Scenario: 删除角色级联头像

- **WHEN** 用户删除一个角色
- **THEN** 该角色的 avatar 资产与 BLOB MUST 一并删除；撤销角色卡不恢复头像

#### Scenario: 删卡失败不留下半截

- **WHEN** 用户删除一个不存在的角色卡
- **THEN** 系统 MUST 返回 400，且该卡 id 下不得发生头像资产删除

### Requirement:### Requirement: 错误码

图像端点 SHALL 在 4xx 响应的 `detail` 中返回 `{code, message}`；状态冲突 MUST 用 409，参数/格式/归属失败 MUST 用 400 或 404，文件超限 MUST 用 413。前端 MUST 能只依赖 `code` 做分支，不解析中文文案。

#### Scenario: 前端按 code 分支

- **WHEN** 上传 GIF 返回 400
- **THEN** `detail.code` SHALL 为 `unsupported_format`，`detail.message` 为可读中文

### Requirement:### Requirement: 上传型封面/头像工坊

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

### Requirement:### Requirement: 设置部分更新

前端 SHALL 用 `PATCH /api/novels/{id}/image-settings` 与 `PATCH .../characters/{cid}/image-settings` 做部分更新；只改模型/seed 时 MUST NOT 清空画风、封面描述或头像描述。未提交 `cover_seed` 时 MUST 保留旧值。

#### Scenario: 只换本书模型

- **WHEN** 用户在工坊页脚只切换图像模型
- **THEN** 画风、封面描述、cover_seed MUST 保持不变

#### Scenario: 只改头像 seed

- **WHEN** 用户只点“换一个”改 seed
- **THEN** avatar_prompt MUST 保持不变

### Requirement: 供应商尺寸契约与失败留痕

发往火山方舟图像端点的请求 `size` MUST 是 `宽x高` 像素写法，MUST NOT 使用比例字符串（如 `3:4`、`1:1`）；所选尺寸 MUST 满足端点的面积下限（≥ 921600 px²）：封面 MUST 为 3:4 竖版的 `960x1280`，头像 MUST 为 `1024x1024`。其他供应商沿用各自合法尺寸口径，本契约不改变其取值。供应商返回 4xx/5xx 时，系统 SHALL 在日志中留痕供应商错误体的 `code`、`message`、`param` 字段（单行、总长截断 ≤500 字符）；留痕 MUST NOT 记录 API Key、prompt 正文、图片字节或完整请求体。

#### Scenario: 火山封面按像素尺寸出图

- **WHEN** 使用火山 provider 发起封面生成调用
- **THEN** 请求 payload 的 `size` MUST 为 `960x1280`，端点不再因 size 返回 400 InvalidParameter

#### Scenario: 火山头像按像素尺寸出图

- **WHEN** 使用火山 provider 发起角色头像生成调用
- **THEN** 请求 payload 的 `size` MUST 为 `1024x1024`

#### Scenario: 供应商 400 报文可观测

- **WHEN** 供应商对图像调用返回 400（如 size 非法）
- **THEN** 日志 SHALL 出现一行含供应商 `error.code` 与 `message`（如 `InvalidParameter`）的留痕，且不含 Key、prompt 正文或图片字节

#### Scenario: 其他供应商尺寸不受影响

- **WHEN** 使用 aliyun/zhipu/openai/minimax provider 发起生成
- **THEN** 请求中的尺寸口径 MUST 与本次改动前一致
