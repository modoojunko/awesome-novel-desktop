# c-image-generation · 任务

## 1. 权益

- [x] 1.1 `image-generate` feature key：C端 specs 词汇表、entitlement-defaults、STANDARD_FALLBACK、features.ts、e2e 种子、路由声明/门禁/对拍测试；S端 `ENTITLEMENT_DEFAULTS`＋契约副本＋seed SQL 已在 `s-image-generate` 分支同批改（生产 tiers 行发放与 S PR 合并仍待运维）
- [x] 1.2 `require_tier_access`；standard 拒绝/trial 放行矩阵已落测试；旧快照缺 key 时未过期 trial/pro/max 前后端同口径隐式放行（后端 MUST 真放行，已有四臂测试）
- [x] 1.3 免费用户上传永远可用；生成/试画/批量后端 `image-generate` 真拦

## 2. 适配器

- [x] 2.1 canonical/effective request：purpose/prompt/negative/size/n/seed/watermark；reference 图生图首版不暴露（provider 差异大，已列 Non-Goal）
- [x] 2.2 三套 wire：OpenAI-ish（火山/智谱/OpenAI/兼容）、DashScope（百炼）、MiniMax
- [x] 2.3 能力矩阵：negative/seed/watermark/native size；不支持的字段不进 effective hash（OpenAI 无 seed 时用确定性 prompt 变体）
- [x] 2.4 归一化复用阶段 1 管线到 768×1024 / 512×512；错误分类 auth/quota/rate_limit/moderation/timeout/network/invalid/empty

## 3. 任务

- [x] 3.1 `image_jobs`/`image_batches` schema + partial unique（同一 target 同时最多一个 queued/running）＋ idempotency key（批量键含角色集合；failed/cancelled 同键重提就地重排）
- [x] 3.2 独立 dispatcher：条件 UPDATE claim、取消、重试、批量 item；不占写作 `job_runner` 单飞槽；关闭弹窗不取消；重试按库内累计账目、跳过已产候选
- [x] 3.3 启动 sweep running→failed(interrupted)；`cancelled_billed` 状态保留给供应商返回/取消竞态（当前先落候选再检查，正常路径不产生）
- [x] 3.4 生成/试画/批量端点；逐候选独立 seed + prompt_hash 落库；失败保留已产生候选

## 4. 验证

- [x] 4.1 单测：三套 wire/能力降级/错误分类/URL 下载安全（含域名解析到内网拒绝）、逐候选 seed+hash、active 唯一、失败保候选、批量逐项账、取消/重试/启动 sweep、重试账目与去重、批量幂等角色集、旧快照隐式放行、日志脱敏、standard/trial HTTP 门（`test_image_generation.py` 20 passed）
- [ ] 4.2 真机：封面/头像/批量/失败/取消/换供应商（供应商真实响应形状未实测）
- [x] 4.3 发布门禁：生成失败不丢已产生候选（测试钉）；`image_gen` 日志不含 Key/prompt/图片字节（caplog 钉）

## 5. 发布依赖

- [ ] 5.1 S端 `s-image-generate` PR 合并与生产 tiers 行按 pro/max/trial 发放 `image-generate`
- [ ] 5.2 C端 stacked PR 基于 #930，待 #930 合并后 rebase/推送
- [ ] 5.3 真机 4.2 通过后归档本 change
