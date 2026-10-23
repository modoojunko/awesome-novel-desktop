# c-cover-avatar-ui · 设计

## Context

阶段 1 已冻结后端契约：图像配置 CRUD、每书/每角色图像设置、上传/候选/采用/8 秒撤销、签名 URL 刷新与书/角色 DTO 内联图片。前端已有模型配置页双页签、书架书卡、角色面板与通用 `Modal`/`UndoToast` 组件。本 change 只把这些契约接到现有界面，不新增后端端点，也不做生成链路。

## Goals / Non-Goals

**Goals:**

- 图像模型配置进入 `/config` 第三页签，交互沿用写作模型配置的列表卡＋弹窗习惯。
- 书卡与角色面板都能就地看到当前封面/头像，并从无图入口直接打开上传型工坊。
- 上传、候选、采用、撤销、丢弃在工坊内闭环；关闭再开时 8 秒撤销状态可续期。
- 签名 URL 过期只在图片加载失败时刷新一次，避免无限重试。
- 所有时间解析走 `parseServerTime`，不裸用 `new Date(iso)`。

**Non-Goals:**

- 不做 AI 生成、模型拉取、连接测试、试画、批量头像与任务队列（归 `c-image-generation`）。
- 不改变后端数据模型或备份格式（归 `c-cover-avatar-backup`）。
- 不重画模型配置/书架视觉基因；只新增必要的图像组件词汇并保持 parity。

## Decisions

- **API 客户端单源 `lib/imageApi.ts`**：配置、资产、设置、prompt、签名链接统一封装；XHR FormData 专门服务上传进度。相比在组件里散落 `fetch`，能保证 Bearer、`mediaUrl()` 与错误形状一致。
- **签名 URL 组合在 `mediaUrl()`**：后端下发相对 `/api/...`，`VITE_API_BASE_URL` 非空时 `<img>` 需要拼上 API origin。组件一律不手拼。
- **三个组件分层**：`ImageConfigPanel` 只管配置页；`ImageWorkshopModal` 只管资产与设置；`ImageThumb` 只管缩略图与一次性链接刷新。避免一个巨型弹窗同时承担配置和上传。
- **采用/撤销状态由宿主保存**：`ImageWorkshopModal.onChanged` 把 undo 状态上抛给书架/角色面板，宿主再用 `initialUndo` 传回。这样关闭弹窗再开不会丢 8 秒撤销；撤销后宿主清空状态。
- **书架/角色数据同步采用宿主刷新**：工坊完成后由书架 `fetchNovels()`、角色面板 `reloadList()` 刷新，不在工坊内直接改 React Query 缓存，避免同一 DTO 在多处双写。
- **图像模型页签挂载即拉数据，其他页签不渲染面板**：避免旧测试和无关注册请求被图像 API 打扰，也减少后台请求。
- **视觉词汇放 `design/image-assets.css`**：只新增 `.img-*`、`.cover-*`、`.char-seal-btn` 等图像专用类，不改共享基础段；原型 `prototypes/list.html` 同步书卡封面入口，保持像素 parity。
- **删除文案按后端事实声明**：删书会删当前封面；删角色只恢复卡不恢复头像。不在前端承诺“撤销可恢复图片”。

## Risks / Trade-offs

- [上传大图时 XHR 进度只覆盖传输，不覆盖后端裁剪] → 进度到 100% 后显示“处理中…”，完成后刷新候选。
- [签名 URL 只有 1 小时] → `ImageThumb` 加载失败只刷新一次；超过撤销/过期窗口的操作由后端 4xx 语义兜底。
- [8 秒撤销窗口较短，跨弹窗续期仍可能过期] → 状态由宿主保存但过期自动消失；过期后后端返回 `undo_expired`，前端不再重试。
- [新增页签和书卡角标可能影响冻结像素] → 原型同步修改并通过 `design:check` 全绿。

## Migration Plan

纯前端增量，无需数据迁移。发布时依赖阶段 1 后端与 v7 备份随同上线；回滚前端不会破坏已上传资产，但会回到无封面/头像展示的状态。
