# 封面/头像前端工坊（c-cover-avatar-ui）

## Why

阶段 1 后端已提供配置 CRUD、上传、候选列表、采用/撤销、签名读取、PATCH 设置与链接刷新；阶段 2 需要把书架、角色页、图像模型页接上这些真实 API。当前只做“上传型工坊”，生成/测试/批量任务依赖阶段 3 的 jobs 与权益键。

## What Changes

- 图像模型页第三页签：图像配置 CRUD/默认/软删恢复；编辑页支持换供应商（显式确认；未填新 Key/模型时由后端清空旧值）。
- 封面工坊/头像工坊：上传、候选列表、采用、8 秒撤销、丢弃候选、签名 URL 过期刷新。
- 书卡/角色卡展示 `cover`/`avatar`；无图时保留“添加封面/头像”入口；删除书/角色的文案与后端级联一致。
- 书级/角色级设置接 `PATCH`：只改模型/seed 不清画风、描述；未显式提交 `cover_seed` 保留旧值。
- 时间字段统一用 `parseServerTime`（或后端 `*_Z` / epoch），撤销倒计时与 URL 刷新不裸用 `new Date`。
- 免费用户只能上传；生成/测试/批量入口显示“PRO 以上可用”，后端拦截随阶段 3。
- 不做：生成 2 张候选、模型拉取、测试连接、试画、批量头像（这些属 `c-image-generation`）。

## Capabilities

### Modified Capabilities

- `cover-avatar`: 增加前端上传型工坊与展示行为。

## Design Impact

- 受影响屏：书架书卡、角色列表/详情、图像模型配置页、封面/头像工坊。
- 复用现有 `Modal`、`VendorGrid`、`ModelPicker`、`SecretField`、`TestResult`、`UndoToast`。
- 不改后端数据库；阶段 1 API 已冻结。

## Impact

- `client/frontend/src/lib/imageApi.ts`
- `client/frontend/src/components/image/ImageConfigPanel.tsx`、`ImageWorkshopModal.tsx`、`ImageThumb.tsx`
- `client/frontend/src/pages/ApiKeyConfigPage.tsx`、`NovelListPage.tsx`
- `client/frontend/src/components/novel/settings/CharacterManager.tsx`
- `client/frontend/src/design/image-assets.css`
- `client/frontend/src/lib/charactersApi.ts`
- `docs/design-c/drafts/ai-novel-c端-封面与角色头像-原型.src.html`（设计基线）
