# c-image-generation · 设计

## Context

阶段 1/2 已提供上传型资产地基与工坊：`image_configs`、`image_assets`、prompt 预览、PATCH 设置、v7 备份都已冻结。本 change 只补“AI 生成”链：权益、供应商适配、任务队列、前端生成/批量入口。生成复用阶段 1 的 `normalize_image`、candidate/current 状态机、签名 URL 与 prompt 白名单，不另建第二套资产管线。

## Goals / Non-Goals

**Goals:**

- `image-generate` 权益键按 `none/free/standard/expired → 只能上传，trial/pro/max → 可用` 生效；图像 Key 作者自持，不查写作大模型。
- 六家供应商收敛为三套 wire；不支持的字段从 effective request/hash 剔除。
- 每候选独立 seed 与 prompt hash；无 seed 供应商用确定性 prompt 变体。
- 任务落库可恢复：同一目标最多一个 active job；关闭弹窗不取消；取消保留已生成候选。
- 批量头像逐角色一行账，候选生成后进各自角色工坊采用。

**Non-Goals:**

- 不做参考图/图生图（provider 差异大，首版不暴露入口）。
- 不把 `image_jobs` 写入备份包：任务是运行态，候选资产已随 v7 备份。
- 不接入 `job_runner` 全局单飞槽，避免图像生成锁死备份/下载。
- 不做用量价格换算；`billed_n` 先记供应商返回张数。

## Decisions

- **键自持门**：生成/试画/批量端点挂 `ai_feature("image-generate") + require_tier_access`，与朱雀同属 `KEYLESS_GATE_KEYS`；不要求配置写作大模型。
- **旧快照兼容**：C端 前端在快照不含 `image-generate` 时，对未过期 trial/pro/max（含 monthly/quarterly/yearly/lifetime 别名）隐式放行，避免 S端 快照刷新前老会员被误锁；standard/free/过期仍锁。
- **任务表**：`ImageJob.target_type/target_id` 表达目标（book/character/batch），partial unique index 限制同一目标同时只有一个 queued/running；`idempotency_key=(user,target,purpose,prompt_hash,n)` 让重复提交返回同一 job。
- **独立 dispatcher**：复制拆书 dispatcher 形态（daemon 线程 + event loop + 条件 UPDATE claim + 2s 轮询），但完全独立；测试用 `IMAGE_DISPATCHER_OFF=1`，`stop_dispatcher()` 只作测试收线。
- **逐候选调用**：即使供应商支持 `n>1` 也一张一请求，保证每个候选独立 seed/变体与 hash；供应商 billed 张数记 `billed_n`。
- **effective hash**：`prompt_builder.effective_prompt_hash()` 按能力矩阵剔除 seed/negative/watermark；预览 hash 即候选 0 hash，候选 1+ 因 seed 或 prompt 变体而不同。
- **取消语义**：queued 直接 cancelled 并把 pending item 收敛 cancelled；running 只置 `cancel_requested`，worker 在候选/角色间检查；已落库候选不删除。`cancelled_billed` 状态保留给“供应商已返回但取消先到”的竞态，当前实现总是先落候选再检查，因此正常路径不产生该状态。
- **适配层**：`image_assets/adapters.py` 统一 `ImageGenerationSpec/GeneratedImage/ImageProviderError`；OpenAI-ish（火山/智谱/OpenAI/兼容）、DashScope、MiniMax 三套 payload；错误归为 auth/quota/rate_limit/moderation/timeout/network/invalid/empty。供应商 URL 只允许 http(s)、禁重定向、禁内网/本机/带凭据链接、≤10MB。
- **日志**：`image_gen` 进 llm.log 专项档；只记 provider/model/host/path/status/duration/result/张数，Key、prompt、图片字节不落。
- **前端**：工坊内生成态独立于上传 busy，轮询 1.5s；批量头像单独 `BatchAvatarModal`，默认勾选无头像角色。

## Risks / Trade-offs

- [供应商真实响应形状未真机验证] → 适配器解析递归收敛 b64/url，错误/空结果有测试桩；tasks 4.2 真机验收保持开放。
- [取消不能中断已发出的 HTTP 请求] → 只在候选/角色之间生效；该请求若返回图片仍落候选并计费。
- [旧快照隐式放行可能比 S端 快照更宽] → 只限 image-generate 且要求未过期 trial/pro/max；S端 契约和 fallback 同批更新，快照刷新后删除兼容层。
- [jobs 未随备份走] → 换机后任务历史不迁移，但已采用图片在 v7 资产包内；候选若未采用则视为放弃。

## Migration Plan

- 新表 `image_jobs`/`image_batches` 随本版全新库 `create_all` 建；无 ALTER。开发中未发布的 stage1 表可同批改 `image_assets.job_id` 为真 FK。
- S端 需要 `s-image-generate` 分支同步 `ENTITLEMENT_DEFAULTS` 与契约，生产 tiers 行按档补 key 后再发布 C端。
- 回滚：前端回滚后上传/采用仍可用；已落库任务停止调度，候选按 24h TTL 自然清理。
