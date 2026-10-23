# C端 封面与角色头像（c-cover-avatar）

## Why

作者需要给书一个封面、给角色一张脸，但当前书架只有首字方块、角色只有章印首字。图像模型（火山引擎 Seedream、阿里云百炼 Qwen-Image、智谱 CogView、OpenAI、MiniMax、OpenAI 兼容）已经可用，先把**资产地基**做稳：配置与写作 Key 物理隔离、图片进库、上传/采用/撤销/签名读取、每书绑定。生成/测试/试画不在本 change 的第一阶段，避免在任务层与计费契约冻结前产生返工。

## What Changes

- **图像配置独立表** `image_configs`：加密 Key（复用 api_configs/crypto）、模型清单、默认配置、软删/恢复；不复用 `api_configs` 查询，避免图像 Key 被写作链路误选。
- **资产表** `image_assets` + `image_asset_blobs(asset_id, variant)`：逻辑资产一条、full/thumb 两条字节；候选 24h TTL、current/previous 部分唯一索引、undo_token + 8s 撤销窗口。
- **上传/采用/撤销/签名读取**：JPG/PNG/WebP → 等比缩放 + 居中 cover-crop → 768×1024（封面）/512×512（头像）+ 缩略图 → WebP；单张 ≤10MB、≤30MP；签名 URL 读取，`nosniff` + 短缓存（缓存必须短于签名 TTL，不能 `immutable`）。
- **权限与状态机**：角色、资产、设置端点统一校验书归属；候选 24h、撤销 8s 由服务端强制执行，启动期与上传/采用前 sweep；只有 candidate 可 adopt，current/previous 重复 adopt 返回 409，状态冲突不 500。
- **每书绑定** `book_image_settings`（style_key/cover_prompt/cover_seed/image_config_id/image_model）与 `character_image_settings`（avatar_prompt/seed）。
- **Prompt 契约 v3**：书名/角色名（包括藏在世界舞台/人设/势力/自定义描述里的）只进 sources 不进 prompt；封面不把简介原文当画面；negative prompt、canonical prompt_hash（含模板版本/尺寸/seed/模型/provider/能力）、cover seed、候选 seed。
- **Pillow 依赖**：requirements、许可证白名单（MIT-CMU）、打包 hiddenimports（移出 PIL 排除）。
- **本次只交付阶段 1**：配置/资产地基。阶段 2 前端工坊在 `c-cover-avatar-ui`，备份 v7 在 `c-cover-avatar-backup`（已实现），阶段 3 生成/权益在 `c-image-generation`；见 `follow-ups.md`。
- **待确认假设**（未获用户回答，先按推荐值写，评审时需确认）：standard 档只能上传；trial 按 PRO 同权；角色删除当前立即删头像（撤销回无头像卡）；新书默认跟显式 `is_default` 配置，没有默认时自动补一个。

## Capabilities

### New Capabilities

- `cover-avatar`: 图像配置、资产上传/采用/撤销/签名读取、每书与角色级图像设置。

### Modified Capabilities

- 无（备份/导出在后续 change 处理，避免本阶段跨格式升级）。

## Design Impact

- 受影响端：C端后端 + 打包清单；不改 S端、不改两端共享设计令牌。
- 受影响屏：无前端屏改动（阶段 1 后端 API）；原型只作设计基线。
- 数据：新增五张表；不 ALTER 既有表。旧库首启按 c-db-per-version 走版本升级（本 change 不发布）。
- 共享段：无。

## Impact

- `client/backend/models/image_asset.py`、`models/__init__.py`
- `client/backend/image_assets/`（service/router/schemas）
- `client/backend/main.py`（路由注册）
- `client/backend/requirements.txt`、`scripts/check_py_licenses.py`
- `client/packaging/build/bundle_manifest.py`
- `client/backend/tests/test_image_assets.py`
