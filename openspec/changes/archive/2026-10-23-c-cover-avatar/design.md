# c-cover-avatar · 设计（阶段 1）

## Context

图像模型与写作模型是两套凭据、两套端点、两套计费；图像资产需要候选/采用/撤销与签名读取。现有 `api_configs` 的写作查询、就绪判定与备份白名单都把「所有 active Key」当写作 Key，不能直接复用。

## Decisions

- **配置独立表**：`image_configs` 只共享 `api_configs/crypto.py` 与 `http_client.py`；不做 `kind` 列，避免写作链路全量审计。第一条 active 配置自动成为默认；显式取消默认时优先补另一个 active 配置。
- **资产身份**：`image_assets` 一条逻辑资产；`image_asset_blobs(asset_id, variant)` 复合主键，variant=full|thumb；`current/previous` 部分唯一索引只作用逻辑资产。
- **保留策略**：候选 `expires_at=24h`；采用时旧 current→previous，旧 previous 物理删除；`undo_expires_at=adopted_at+8s` 由服务端校验；首次采用撤销=删除 current 回占位。启动期全库 sweep，上传/采用前按用户 sweep；读取端点只过滤不写库。
- **状态机**：只有 `candidate` 可 adopt；current/previous 重复 adopt 返回 409 `asset_not_candidate`；并发写唯一索引冲突转 409 `asset_state_conflict`，不 500。
- **授权**：角色路由统一用 `_require_owned_project` 校验书归属；图像配置/资产/设置 helper 都带 user/novel 作用域；越权返回 404/400，不泄漏资产。
- **签名读取**：HMAC-SHA256 绑 `asset:variant:exp`，密钥存 `app_meta.image_asset_signing_key`，由 lifespan 启动期初始化；`GET /api/image-assets/{id}?variant=&exp=&sig=` 不挂 Bearer；响应 `Cache-Control: private, max-age=3300`（短于 1h 签名），禁止 `immutable`。
- **每书绑定**：`book_image_settings` 存 style/cover_prompt/cover_seed/image_config_id/image_model；`character_image_settings` 存 avatar_prompt/seed。画风书级、封面描述/种子与头像描述/种子各自可覆盖。
- **Prompt 契约 v3**：`prompt_template_version=3`；书名/角色名只进 sources，自由文本统一脱敏；封面 prompt 不读简介原文；输出 positive/negative/size/seed/model/provider/capabilities，`prompt_hash` 对 canonical JSON 做 SHA-256；每候选独立 seed。
- **尺寸**：目标封面 768×1024、头像 512×512；统一等比缩放→居中 cover-crop→精确尺寸，禁止拉伸；上传仅接受 JPG/PNG/WebP。
- **本阶段不做**：生成/测试/试画、provider adapter、job 队列、前端 UI；它们需要单独契约与计费/任务评审。备份 v7 已由 `c-cover-avatar-backup` 交付。

## Phases

- **阶段 1（本 change，已实现）**：`image_configs` / `image_assets` / `image_asset_blobs` / `book_image_settings` / `character_image_settings`；配置 CRUD、上传、采用/撤销、资产列表、签名读取、书/角色 DTO 带图、删除级联、prompt 预览、归属校验与 TTL sweep。
- **阶段 2（c-cover-avatar-ui）**：前端图像模型页/工坊/上传 UI；备份 v7 已由 `c-cover-avatar-backup` 交付（images + manifest + image_configs 重加密 + roundtrip）。
- **阶段 3（另立 change，见 follow-ups.md）**：`image-generate` 权益与 PRO 门控；provider adapter（火山/阿里/智谱/OpenAI/MiniMax/兼容）；`image_jobs`/`image_batches`；生成/测试/试画；计费台账。

## Assumptions（待确认）

- standard 档只能上传，trial 按 PRO 同权；如要放宽 standard，改 `image-generate` 权益矩阵即可。
- 角色删除当前立即删除 avatar 与 BLOB（撤销回无头像卡）；若要撤销连头像回，改为 `pending_delete` + undo TTL。
- 新书默认跟 `image_configs.is_default`；没有默认时用唯一可用配置。
- 备份 v7 已由 `c-cover-avatar-backup` 完成（图片/设置/图像配置 + 迁移 Key 转接）。

## Risks

- 新增表会改变 schema 指纹，旧库需按 c-db-per-version 升级；本 change 未发版，测试用临时库。
- 备份 zip 已带 BLOB（v7）；仍以 roundtrip 为发布门禁（`c-cover-avatar-backup`）。
- 免费/PRO 门控、provider 适配与任务层未进入本阶段。
