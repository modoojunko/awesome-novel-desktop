# 图像生成与权益（c-image-generation）

## Why

阶段 1/2 只解决“上传型”封面/头像。真正的 AI 封面/头像需要供应商适配、任务队列、逐候选 seed/hash、PRO 权益与计费台账；这些契约必须与任务层、失败重试和 S 端权益一起冻结，不能塞进上传工坊。

## What Changes

- `image-generate` feature key 六步 SOP；`require_tier_access`；standard/trial 矩阵拍板（当前假设 standard 只能上传、trial 同 PRO）。
- provider adapter：火山 Seedream、阿里 Qwen-Image、智谱 CogView、OpenAI gpt-image-1、MiniMax image-01、OpenAI 兼容；能力矩阵（negative/seed/watermark/native size）、尺寸归一化、错误分类。参考图/图生图首版不暴露。
- `image_jobs`/`image_batches` + dispatcher：幂等、取消、恢复、批量 item；不占用写作 `job_runner` 单飞槽。
- 生成/试画/批量端点；prompt builder 快照 positive/negative/template_version/hash/seed；每候选独立 seed 与 hash。
- 计费账先记供应商返回张数（`billed_n`）与失败重试；关闭弹窗 ≠ 取消；失败/取消保留已产生候选。

## Capabilities

### Modified Capabilities

- `cover-avatar`: 增加生成/测试/试画/批量与 PRO 门控。

## Design Impact

- 新表：`image_jobs`、`image_batches`（阶段 3 单独 change 落 schema）。
- 新配置：`image-generate` 权益键与 `entitlement-defaults.json` 对拍。
- 受影响屏：封面/头像工坊的生成态、批量头像、失败/取消态。

## Impact

- `client/backend/image_assets/`（adapters/generation/dispatcher/router/schemas/prompt_builder）、`models/image_asset.py`、`auth_local/service.py`、`logging_setup.py`
- `client/frontend/src/lib/features.ts`、`hooks/useTier.ts`、`lib/imageApi.ts`、`components/image/`、`components/novel/settings/CharacterManager.tsx`
- `docs/contracts/entitlement-defaults.json`、`openspec/specs/tier-gating/spec.md`
- S端 私有仓：`server/app/config.py`、`docs/contracts/entitlement-defaults.json`、`server/scripts/seed_four_tiers.sql`（`s-image-generate` 分支）

