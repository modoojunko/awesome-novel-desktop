# c-cover-avatar · 任务（阶段 1）

> 本 change 只交付阶段 1。阶段 2/3 的 UI、备份 v7、权益、provider adapter、jobs 已移入
> `follow-ups.md`，分别另立 change；不让本 change 的完成度依赖后续阶段。

## 1. 配置层

- [x] 1.1 新增 `image_configs`（加密 Key/模型/默认/软删），独立于写作 `api_configs`
- [x] 1.2 配置 CRUD + 软删/恢复 + 唯一默认；同名软删行复活避免 UNIQUE 撞车
- [x] 1.3 第一条 active 配置自动默认；取消/删除默认后自动补位；include_deleted 可查软删行
- [x] 1.4 软删配置时清空书中绑定（image_config_id/image_model），避免悬空

## 2. 资产层

- [x] 2.1 新增 `image_assets` + `image_asset_blobs(asset_id, variant)`；current/previous 部分唯一索引
- [x] 2.2 上传：JPG/PNG/WebP → 等比缩放 + 居中 cover-crop → 768×1024/512×512 + 缩略图 → WebP；10MB/30MP/4096 限制；GIF/BMP/TIFF 拒绝
- [x] 2.3 采用/撤销：只有 candidate 可 adopt；current/previous 重复 adopt 409；8s `undo_expires_at` 服务端校验；首次撤销回占位
- [x] 2.4 候选 24h TTL + previous 8s 保留；启动期全库 sweep、上传/采用前按用户 sweep；读取只过滤不写库
- [x] 2.5 签名 URL 读取（HMAC、exp、403、nosniff、短缓存）；签名密钥 lifespan 启动期初始化，GET 不写库
- [x] 2.6 每书 `book_image_settings`（含 cover_seed）与角色 `character_image_settings` 读写；补角色设置 GET
- [x] 2.7 资产列表端点：kind/character_id/status/limit，过滤过期候选与 previous
- [x] 2.8 prompt builder v3：书名/角色名（含藏在自由文本里的）不进 prompt；封面不读简介原文；negative prompt、canonical hash、模板版本、cover/avatar seed、候选 seed
- [x] 2.9 书列表/详情/by-slug 下发 cover、角色列表/详情下发 avatar；删书/删角色/合并角色级联清理资产与 BLOB
- [x] 2.10 角色/资产/设置端点统一归属校验；越权不返回签名 URL、不落库
- [x] 2.11 adopt/undo 条件更新 + StaleDataError→409；sweep 按状态/过期删除；并发同候选恰一个成功
- [x] 2.12 签名密钥故障降级：书架/角色 DTO 返回 null，图片端点 503；写路径可重建密钥
- [x] 2.13 PATCH 书/角色设置、links 刷新、候选丢弃、UTC 时间、undo_token 别名、资产 DTO 统一

## 3. 依赖与打包

- [x] 3.1 `pillow>=11.0.0` 入 requirements
- [x] 3.2 许可证白名单补 `MIT-CMU`；license gate 通过
- [x] 3.3 bundle manifest 加 `image_assets`/`PIL.Image`/`PIL.ImageOps`，移出 `PIL` 排除；manifest 测试通过

## 4. 验证

- [x] 4.1 `test_image_assets.py` 18 passed：配置 CRUD/默认/软删恢复/include_deleted、上传/采用/撤销/签名读取、书/角色 DTO 带图、删除级联、prompt 契约、跨用户越权、TTL/sweep、格式拒绝、资产列表、缓存头、并发 adopt、sweep 不误删 current、签名降级、PATCH/links/UTC
- [x] 4.2 回归：后端全量 2417 passed / 296 skipped；角色/书架/API Key/备份/manifest/db lifecycle 相关组 153 passed
- [x] 4.3 `ruff check` 新文件与改动文件全绿
- [x] 4.4 `openspec validate c-cover-avatar --strict` 通过

## 5. 归档

- [x] 5.1 实现 PR 同批 sync `cover-avatar` delta 到主 spec 并移入 archive
