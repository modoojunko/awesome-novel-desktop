# c-library-avatar-gen — 库卡头像生成（复用书内头像生成能力）

## Why

角色库建卡时头像只有两条路：收录书内卡带过来的图，或先显示姓字块；书内早已有成熟的「按角色卡档案生成头像」能力（图像配置＋供应商适配器＋512/96 压缩链＋prompt 白名单脱敏）。库卡作为账号级角色资产，同样需要出图入口——否则手建角色永远没有头像，拆进来的角色也换不了脸。

## What Changes

- **库侧头像生成端点**（`POST /api/character-library/{id}/avatar/generate`）：账号级**同步生成**——复用既有图像供应商适配器（`image_assets.adapters.generate_images`）与 `normalize_image("avatar")` 512/96 压缩链，不经过 ImageJob 异步队列（该表的 `novel_id` 是书级必填，账号级不引入新任务体系）。
- **prompt 单源**：把书内头像的 prompt 组装抽成字段级纯函数 `avatar_prompt_payload()`，书内 `build_avatar_prompt` 与新的 `build_library_avatar_prompt` 共用——同一套风格/头肩构图/名称脱敏/负向词/seed 派生规则；库卡版本只读本卡档案（性别/年龄/种族/外貌/势力/人设）并脱敏本卡名与别名，不牵连其他书。
- **档位门同书内**：`ai_feature("image-generate")` ＋ `require_tier_access`（PRO）——与书内头像/封面的生成同权，不新增售卖面。
- **前端**：库卡编辑/新建弹窗头像位新增「生成头像 / 重新生成头像」；新建未落卡时先按当前表单落卡再生成（生成后自然转为编辑态）；无 PRO 或未配图像配置给可读提示；生成成功即时替换头像并提示可再生成。
- 明确不做：库内画面描述编辑框（沿用卡上档案；后续可加）、候选图多选（v1 一图一换）、批量生成、异步队列。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `character-library`: 新增「库卡头像生成」要求（按卡档案组装/复用图像配置与供应商/512-96 档位/成功替换并 bump rev/PRO 同权/失败可读/缺配置可读）。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：角色库编辑/新建弹窗（头像位新增生成按钮；加载中态文案）。
- **对象状态**：生成中按钮「正在生成…」禁用；成功 toast＋头像即时刷新；失败/无权限/缺配置 toast 可读文案。不新增提示语气、不触共享段。
- **原型先行**：库页无 parity 基线（既有 ADJUSTMENTS 豁免），生成按钮随实现落并在 ADJUSTMENTS 追加登记。
- **设计工件产出**：实现侧自查（本单 UI 面极小；drafts 原型不追补，见 ADJUSTMENTS）。

## Impact

- `client/backend/image_assets/prompt_builder.py`：新增 `avatar_prompt_payload()`（字段级纯函数，书内/库卡单源）与 `build_library_avatar_prompt()`（账号级：用户默认图像配置＋本卡脱敏）；`build_avatar_prompt()` 改为读库后委托（行为零变化）。
- `client/backend/library/service.py`：`generate_avatar()`（取配置→组装 prompt→同步调适配器→normalize→写 blobs→bump rev）。
- `client/backend/library/router.py`：新端点＋状态码映射（缺配置 400、供应商失败/超时 502）＋PRO 门。
- `client/frontend/src/lib/libraryApi.ts`：`generateLibraryAvatar()`（信封解包）。
- `client/frontend/src/components/library/CardEditorModal.tsx`：workingCard 工作态（新建先落卡）、生成按钮与加载/失败态。
- 测试：后端 prompt/成功落图/缺配置/供应商失败/超时映射；前端生成成功（已有卡/新建）/无 PRO/无名字/失败文案；覆盖率契约同批 100%。
- 依赖：用户需已配置图像模型（`image_configs` 默认项）；无配置时给可读出口。
