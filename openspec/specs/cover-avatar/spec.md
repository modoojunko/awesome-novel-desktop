# cover-avatar Specification

## Purpose
封面与角色头像：图像模型配置独立于写作模型，封面/头像资产入库、上传/采用/撤销/签名读取，书卡与角色页就地展示，并为阶段 3 的生成链路保留 prompt 与 seed 契约。

## Requirements

### Requirement: 图像配置与写作配置隔离

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

### Requirement: 授权与所有权

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

### Requirement: 资产上传与规范化

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

### Requirement: 资产状态机、TTL 与清理

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

### Requirement: 采用、撤销与签名读取

系统 SHALL 用签名 URL 提供图片读取，签名覆盖 asset、variant、exp；过期/坏签名 MUST 返回 403。响应 SHALL 带 `X-Content-Type-Options: nosniff`，缓存 MUST 短于签名有效期，MUST NOT 使用 `immutable`。

#### Scenario: 坏签名读取

- **WHEN** 请求图片时 sig 被篡改
- **THEN** 系统 MUST 返回 403，不返回图片字节

#### Scenario: 签名过期后缓存不装死

- **WHEN** 浏览器缓存了一张签名图片
- **THEN** `Cache-Control` 的最大缓存时间 MUST 小于签名 TTL，使前端能在过期前重新取链接

### Requirement: 资产列表与候选查询

系统 SHALL 提供按书列出资产的端点，支持 `kind`、`character_id`、`status`、`limit` 过滤。列表 MUST 只返回当前用户、当前书的资产，MUST NOT 返回已过期 candidate/previous；`status` 非法 MUST 返回 400 `invalid_status`。系统 SHALL 提供 `GET /api/image-assets/{id}/links` 刷新签名链接，以及 `DELETE /api/image-assets/{id}` 丢弃 candidate/previous；current MUST NOT 被直接删除。

#### Scenario: 上传后查候选

- **WHEN** 用户上传一张封面后请求 `GET /api/novels/{id}/image-assets?kind=cover&status=candidate`
- **THEN** 响应 SHALL 包含该 `asset_id` 与签名链接

#### Scenario: 采用后候选列表移除

- **WHEN** 用户 adopt 某候选后再查 candidate 列表
- **THEN** 该 `asset_id` MUST 不再出现；查 `status=current` 时 SHALL 出现

### Requirement: 图与书/角色单一归属与 prompt 白名单

系统 SHALL 把封面归属到书、头像归属到角色；封面 prompt MUST 只读题材气质、核心承诺、世界舞台、用户 cover_prompt；头像 prompt MUST 只读角色卡的性别/年龄/种族、外貌、势力/身份、一句话人设，并可继承书级 style_key/model/provider。MUST NOT 把书名、角色名、简介原文、正文、章纲、dossier.background、dossier.plot 送入图像 prompt；书名/角色名 SHALL 只出现在 `sources` 供 UI 叠加。prompt 预览端点 SHALL 返回 positive prompt、negative_prompt、prompt_hash、prompt_template_version、style_key、size、seed、candidate_seeds、model、provider、capabilities、sources。seed MUST NOT 由用户提供：封面/头像 seed 一律按书/角色 id 确定性派生（同书/角恒定），`seed_source` SHALL 恒为 `derived`。

#### Scenario: 头像不泄露角色背景

- **WHEN** 角色卡 background/plot 填了剧情剧透
- **THEN** 头像 prompt MUST 不包含这些字段，只包含外貌/身份/人设等白名单字段

#### Scenario: 书名不画成画面文字

- **WHEN** 书的名称是「夜明铺」
- **THEN** 封面 prompt MUST 不包含「夜明铺」；sources.name SHALL 仍返回书名供 UI 后置叠加

#### Scenario: prompt_hash 可复现

- **WHEN** 同一书/角色、同一模板版本、同一 prompt/negative/size/model 再次预览
- **THEN** prompt_hash MUST 相同；只改 prompt 或模型时 hash MUST 变化，seed 不随设置漂移

#### Scenario: 老客户端残留种子字段被忽略

- **WHEN** 旧版客户端 PUT/PATCH 设置时仍携带 `cover_seed` 或 `seed`
- **THEN** 服务端 MUST 静默忽略该字段（不报错、不落库、响应不回显）

### Requirement: 图像设置读写

系统 SHALL 提供每书 `image_config_id/image_model/style_key/cover_prompt` 与角色 `avatar_prompt` 的读写；绑定配置 MUST 属于当前用户且未删除。`PUT` 为全量写入；`PATCH` SHALL 只更新显式提交字段，未提交字段 MUST 保留。style_key 不在支持列表 MUST 返回 400 `invalid_style`。

#### Scenario: 绑定不存在的配置

- **WHEN** 用户把书绑定到不属于自己的 image_config_id
- **THEN** 系统 MUST 返回 400，不写入设置

#### Scenario: PATCH 只改模型

- **WHEN** 用户 PATCH 只提交 `image_model`
- **THEN** `style_key` 与 `cover_prompt` MUST 保持原值

#### Scenario: 读回角色设置

- **WHEN** 用户保存角色 `avatar_prompt` 后重新 GET 角色设置
- **THEN** 响应 SHALL 原样返回该字段

### Requirement: 书/角色接口就地携带图片，删除级联

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

### Requirement: 错误码

图像端点 SHALL 在 4xx 响应的 `detail` 中返回 `{code, message}`；状态冲突 MUST 用 409，参数/格式/归属失败 MUST 用 400 或 404，文件超限 MUST 用 413。前端 MUST 能只依赖 `code` 做分支，不解析中文文案。

#### Scenario: 前端按 code 分支

- **WHEN** 上传 GIF 返回 400
- **THEN** `detail.code` SHALL 为 `unsupported_format`，`detail.message` 为可读中文

### Requirement: 上传型封面/头像工坊

前端 SHALL 提供上传型封面/头像工坊，使用阶段 1 的 `POST /api/novels/{id}/image-assets`、`GET .../image-assets`、`POST /api/image-assets/{id}/adopt`、`POST .../undo`、`DELETE /api/image-assets/{id}` 与 `GET .../links`。工坊 SHALL 显示候选、当前图、8 秒撤销倒计时；关闭未采用候选 SHALL 确认或明确“候选保留 24 小时”。采用/撤销后 SHALL 重新拉取书/角色 DTO，不把图片 URL 缓存超过 `url_expires_at`。

#### Scenario: 上传并采用封面

- **WHEN** 用户在书卡通过任一封面入口（无封面有章节的点占位块、有封面的悬浮「换封面」、⋯ 菜单「封面…」）发起添加/更换封面并选择 PNG 上传
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

### Requirement: 书卡封面版式（两列·拍板 C）

书架「我的作品」书卡 SHALL 呈两列网格：左列为 3:4 竖版封面列（常规宽 104px，圆角、克制投影，高度贯穿卡片主体），右列为信息列，自上而下依次为题材/状态行、标题、简介、统计、分状态页脚与封面来源说明行。封面 MUST NOT 挤入右列顶行的胶囊行；「首字方块＋文字」的旧单列书卡版式退役。

#### Scenario: 有封面书卡的两列呈现

- **WHEN** 书架渲染一张有封面的书卡
- **THEN** 左列 SHALL 显示竖版封面图（object-fit 裁切、不变形），右列 SHALL 完整呈现题材/状态胶囊行、标题、简介、统计与分状态页脚；顶行胶囊行内 MUST NOT 出现封面缩略图

#### Scenario: 无封面有章节的占位即入口

- **WHEN** 书卡无封面且该书有章节
- **THEN** 左列 SHALL 显示带书名字标的竖版占位块，占位块本身 SHALL 是按钮，点击直接打开封面工坊，CTA 文案为「生成封面」

#### Scenario: 0 章书占位弱化

- **WHEN** 书卡无封面且该书 0 章
- **THEN** 左列占位块 SHALL 不可点击，文案弱化为「还没有封面／可稍后添加」，封面入口 SHALL 保留在 ⋯ 菜单「封面…」

#### Scenario: 悬浮换封面

- **WHEN** 书卡有封面且用户悬浮或键盘聚焦封面列
- **THEN** 封面上 SHALL 浮现「换封面」覆盖按钮，点击打开封面工坊；44×44 小方块与常驻「换/＋」角标形态 MUST NOT 再出现

#### Scenario: 菜单第二入口

- **WHEN** 用户打开任一书卡的 ⋯ 菜单
- **THEN** 菜单第一项 SHALL 是「封面…」，点击打开封面工坊；该项对全部书可见（含 0 章书与免费用户，工坊内权益门照常生效）

#### Scenario: 封面来源说明行

- **WHEN** 渲染任一书卡
- **THEN** 卡片底部 SHALL 显示封面来源说明：生成封面显示「AI 封面 · {画风名}」，本地上传显示「本地上传」，无封面显示「封面位留给作者」

#### Scenario: 窄屏封面列缩放

- **WHEN** 视口宽度 ≤820px
- **THEN** 封面列 SHALL 缩到 88px 宽，右列信息自适应换行，卡片 MUST NOT 出现横向溢出

### Requirement: 设置部分更新

前端 SHALL 用 `PATCH /api/novels/{id}/image-settings` 与 `PATCH .../characters/{cid}/image-settings` 做部分更新；只改模型时 MUST NOT 清空画风、封面描述或头像描述。

#### Scenario: 只换本书模型

- **WHEN** 用户在工坊页脚只切换图像模型
- **THEN** 画风与封面描述 MUST 保持不变

### Requirement: 封面画面 AI 提取

系统 SHALL 提供端点 `POST /api/novels/{id}/image-prompt/cover-extract`，从书级白名单素材（选题 genre/sub_genre、一句话故事 promise_note、简介 synopsis、主线 story_arc.fullstory、世界舞台 stage）经提示词仓模板 `image_cover_scene` 蒸馏出一段封面画面场景草稿。端点 MUST 挂 `image-generate` 权益门与书模型就绪门（未就绪 503，`reason` 与前端 `ai_state` 同枚举；非本书 404）。模板 MUST 来自提示词仓（缺包沿既有 503 `prompts_missing` 语义）；模型输出 MUST 按严格 JSON 契约解析（`{"scene": ...}`），解析失败或空 scene MUST 返回 502 可重试错误。草稿 SHALL 只返回给前端填充「画面描述」输入框（用户可改、显式保存才落库），MUST NOT 直接写入设置或触发生成任务。产出场景 MUST 遵守模板硬约束：画面无文字载体、人物只作剪影/背影/远景、不出现书名/角色名/势力名专名、不剧透关键反转。

#### Scenario: 提取草稿填充画面描述

- **WHEN** PRO 用户在封面工坊点「AI 提取」
- **THEN** 端点 SHALL 返回 `{scene}`，前端 SHALL 把草稿填入「画面描述」输入框并提示可修改后保存；未点保存时设置 MUST 保持原值

#### Scenario: 书模型未就绪

- **WHEN** 本书未绑定可用的写作大模型配置
- **THEN** 端点 MUST 返回 503，`detail.reason` 为 ai_state 枚举值，前端按既有四态卡引导

#### Scenario: 坏 JSON 可重试

- **WHEN** 模型返回非 JSON 或 scene 为空
- **THEN** 端点 MUST 返回 502 且文案含「可重试」；调用账目 SHALL 记失败行

#### Scenario: 素材白名单

- **WHEN** 组装提取请求
- **THEN** 发送内容 SHALL 只含五类书级素材（各按上限截断），MUST NOT 含正文、章纲、角色 dossier

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

### Requirement: 图像生成与 PRO 权益

系统 SHALL 通过 `image-generate` 权益键控制生成/试画/批量：`none/free/standard/expired` 只能上传，`trial/pro/max` 可用。后端 MUST 真拦，MUST NOT 只靠前端置灰。生成 SHALL 按供应商能力发送 negative/seed/watermark；不支持的字段 MUST 从 effective request 与 hash 中剔除。旧权益快照不含 `image-generate` 时，未过期 trial/pro/max SHALL 隐式放行，standard/free/过期 MUST 仍锁定。

#### Scenario: 免费用户生成被拒

- **WHEN** 免费用户调用生成/试画/批量端点
- **THEN** 后端 MUST 返回 `feature_required` 且 `tier_required=pro`，不产生供应商调用与扣费

#### Scenario: 标准档生成被拒

- **WHEN** standard 用户调用生成端点且快照不含 `image-generate`
- **THEN** 后端 MUST 返回 403 `feature_required`，不产生供应商调用

#### Scenario: 旧快照隐式放行（前后端同口径）

- **WHEN** 未过期 trial/pro/max 用户的完整快照缺少 `image-generate`
- **THEN** 后端 MUST 放行生成端点（standard/free/过期仍拒），前端 MUST 显示可生成

#### Scenario: 不支持 seed 的供应商

- **WHEN** 使用 `gpt-image-1` 生成头像且候选 2 张
- **THEN** 适配器 MUST 不发送 seed，改用确定性 prompt 变体；每个候选仍 MUST 有独立 prompt_hash

#### Scenario: 取消不丢候选

- **WHEN** 批量头像在中途取消
- **THEN** 已完成候选 MUST 保留可查看/采用；未完成 item MUST 标记 cancelled，MUST NOT 假装成功

### Requirement: 生成任务与 seed 快照

系统 SHALL 为每次生成保存 positive prompt、negative prompt、template_version、prompt_hash、provider/model、每个候选的 seed。候选 seed SHALL 独立（禁止 n=2 复用同一 seed）；同一 canonical request 重跑 SHALL 能复现 preview hash。同一目标（书封面/单角色头像/批量头像）同时 MUST 只有一个 queued/running 任务；关闭工坊 MUST NOT 取消任务。

#### Scenario: 两个候选不重复

- **WHEN** 一次生成 2 张候选
- **THEN** 两个候选的 seed 与 prompt_hash MUST 不同

#### Scenario: 预览与生成 hash 对齐

- **WHEN** 用户先预览 prompt 再生成
- **THEN** 生成落库的候选 0 prompt_hash MUST 等于预览 hash

#### Scenario: 同一目标重复提交幂等

- **WHEN** 同一目标已有 queued/running 任务时再次提交
- **THEN** 系统 MUST 返回 409 `job_active_exists`；相同 idempotency key 的重复提交 SHALL 返回原任务。批量任务的 idempotency key MUST 含角色集合（不得因人数/代表角色相同而错配）；原任务为 failed/cancelled 时 SHALL 就地重置为 queued 续跑，MUST NOT 永久返回终态任务

#### Scenario: 重试不重复计费

- **WHEN** 任务部分成功后失败/取消并重试
- **THEN** 已产出的候选 MUST 保留且 MUST NOT 重复生成（单角色按候选 prompt_hash 跳过）；`produced_count/billed_n` MUST 以库内累计为准，不得回落到本次重试数量

#### Scenario: 应用重启恢复

- **WHEN** 应用启动时存在 running 图像任务
- **THEN** 系统 SHALL 将其置为 failed（`interrupted`），用户可重试；已产生候选保留

### Requirement: 供应商适配与错误分类

系统 SHALL 通过统一适配层调用图像供应商：OpenAI images 形态（火山/智谱/OpenAI/兼容）、DashScope multimodal-generation、MiniMax image_generation。供应商返回的 b64/URL SHALL 收敛为图片字节；URL MUST 仅允许 http(s)、禁止重定向/内网/本机/带凭据链接且 ≤10MB；域名 MUST 解析后再判内网（私网/回环/链路本地/保留/多播均拒绝）。调用失败 SHALL 归类为 auth/quota/rate_limit/moderation/timeout/network/invalid/empty。日志 MUST NOT 记录 API Key、prompt 正文或图片字节。

#### Scenario: 配置 Key 无效

- **WHEN** 供应商返回 401/403
- **THEN** 任务错误 kind MUST 为 `auth`，错误信息可读且不泄露 Key

#### Scenario: 供应商只返回 URL

- **WHEN** 供应商响应中的图片以 URL 形式返回
- **THEN** 适配器 SHALL 在同一次出网上下文中下载并校验内容类型与大小，再交给统一归一化管线

### Requirement: 批量头像逐角色账

批量头像 SHALL 按角色建立逐项账：每个 item 记录 pending/running/completed/failed/cancelled 状态、seed、prompt_hash、产生张数与耗时。完成后各角色 SHALL 在自己的头像工坊看到候选；批量入口 MUST 按同一 `image-generate` 权益门控。

#### Scenario: 两个角色批量生成

- **WHEN** 用户选择两个角色发起批量头像且全部成功
- **THEN** 两个 item MUST 都是 completed，各自角色名下各有一张候选，且 prompt_hash 不同

#### Scenario: 单角色失败不拖垮整批

- **WHEN** 批量中一个角色的供应商调用失败、另一个成功
- **THEN** 失败 item MUST 是 failed 并带错误 kind；成功候选 MUST 保留可用
### Requirement: 图像模型配置表单与连接测试

图像配置表单 SHALL 以单一「模型」输入作为模型信息的唯一入口：保存时系统 MUST 将其落为配置的默认模型，并在请求未显式携带模型清单时自动派生模型清单为 `[默认模型]`；显式携带清单的请求（备份恢复、旧客户端）MUST 被尊重。表单 SHALL NOT 再展示独立的「模型清单」输入。系统 SHALL 提供图像配置连接测试：以配置参数真实调用一次最小生成请求（试画），成功时记录测试通过状态与测试时间，失败时记录失败状态与可读错误摘要；测试 MUST 由后端真实执行（试画请求打向供应商），MUST NOT 只靠前端探测；测试结果 SHALL 在表单中即时呈现。测试端点 SHALL 受 `image-generate` 权益门控制（与生成端点同语义）。更换供应商保存后 MUST 清空既有测试状态。切换供应商时表单 MUST 预填该供应商的 Base URL 与最新预设模型 id，作家可改为任意模型 id。

#### Scenario: 保存时模型清单自动派生

- **WHEN** 作家在表单只填单一模型 id 并保存
- **THEN** 配置的默认模型为该 id，模型清单自动为 `[该 id]`，表单无需单独填写清单

#### Scenario: 显式清单仍被尊重

- **WHEN** 请求显式携带模型清单（如备份恢复路径）
- **THEN** 系统按显式清单落库，不用单模型派生值覆盖

#### Scenario: 测试连接成功

- **WHEN** 作家点击测试连接且供应商真实返回可解析的生成结果
- **THEN** 表单呈现测试通过；对已保存的配置，通过状态与测试时间被记录并可在配置列表查看

#### Scenario: 测试连接失败

- **WHEN** 测试请求因 Key 无效、Base URL 错误、模型名不存在或超时等原因失败
- **THEN** 表单呈现失败与可读错误摘要；对已保存的配置，失败状态与错误摘要被记录；保存配置本身不被测试失败阻止

#### Scenario: 未保存的新配置可直接测试

- **WHEN** 作家在新建表单填完参数后点测试连接（尚未保存）
- **THEN** 测试以表单参数真实执行并即时呈现结果，MUST NOT 写入任何配置的测试状态

#### Scenario: 测试频控

- **WHEN** 同一用户在短时间内连续发起测试连接
- **THEN** 后端 SHALL 限频拒绝并返回可读提示，前端呈现该提示而非通用报错

#### Scenario: 免费用户测试被权益门拦截

- **WHEN** 无 `image-generate` 权益（free/standard/过期）的用户调用测试端点
- **THEN** 后端真实拒绝（MUST NOT 仅前端置灰），前端呈现升级引导

#### Scenario: 换供应商清空测试状态

- **WHEN** 编辑保存更换了供应商
- **THEN** 既有测试状态、错误摘要与测试时间被清空，需重新测试

#### Scenario: 供应商预设预填

- **WHEN** 作家切换供应商
- **THEN** Base URL 与模型输入被预填为该供应商预设（火山引擎为 Seedream 5.0 系模型 id），可改为任意模型 id

### Requirement: 头像外貌 AI 起草

系统 SHALL 提供端点 `POST /api/novels/{id}/characters/{cid}/image-prompt/look-extract`，从角色卡白名单素材（题材、性别/年龄/种族、外貌档案 look、势力/身份、一句话人设）经提示词仓模板 `image_avatar_look` 蒸馏出一段只写外貌/服饰的头像描述草稿。端点 MUST 挂 `image-generate` 权益门、书模型就绪门（未就绪 503，`reason` 与前端 `ai_state` 同枚举）与角色归属校验（不属于本书/当前用户 400）。模板 MUST 来自提示词仓（缺包沿既有 503 `prompts_missing` 语义）；模型输出 MUST 按严格 JSON 契约解析（`{"look": ...}`），解析失败或空 look MUST 返回 502 可重试错误。草稿守卫 MUST 与 prompt_builder 的 avatar_prompt 截断（140 字）对齐。草稿 SHALL 只返回给前端填充「头像描述」输入框（用户可改、显式保存才落库），MUST NOT 直接写入设置或触发生成任务。产出 MUST 遵守模板硬约束：只写外貌/服饰、适配近景头肩构图、服装无文字徽标、不出现角色名/势力名专名、不编造角色卡没有的特征。

#### Scenario: 起草草稿填充头像描述

- **WHEN** PRO 用户在头像工坊点「AI 起草」
- **THEN** 端点 SHALL 返回 `{look}`，前端 SHALL 把草稿填入「头像描述」输入框并提示可修改后保存；未点保存时设置 MUST 保持原值

#### Scenario: 角色归属校验

- **WHEN** 请求的角色不属于当前用户或本书
- **THEN** 端点 MUST 返回 400，不发起模型调用

#### Scenario: 坏 JSON 可重试

- **WHEN** 模型返回非 JSON 或 look 为空
- **THEN** 端点 MUST 返回 502 且文案含「可重试」；调用账目 SHALL 记失败行

#### Scenario: 素材白名单与不编造

- **WHEN** 组装起草请求
- **THEN** 发送内容 SHALL 只含五类角色卡白名单素材（各按上限截断），MUST NOT 含正文、章纲、dossier.background/plot；模板 SHALL 要求素材没有的特征不凭空定死
