## ADDED Requirements

### Requirement: 图像生成与 PRO 权益

系统 SHALL 通过 `image-generate` 权益键控制生成/试画/批量：`none/free/standard/expired` 只能上传，`trial/pro/max` 可用。后端 MUST 真拦，MUST NOT 只靠前端置灰。生成 SHALL 按供应商能力发送 negative/seed/watermark；不支持的字段 MUST 从 effective request 与 hash 中剔除。旧权益快照不含 `image-generate` 时，未过期 trial/pro/max SHALL 隐式放行，standard/free/过期 MUST 仍锁定。

#### Scenario: 免费用户生成被拒

- **WHEN** 免费用户调用生成/试画/批量端点
- **THEN** 后端 MUST 返回 `feature_required` 且 `tier_required=pro`，不产生供应商调用与扣费

#### Scenario: 标准档生成被拒

- **WHEN** standard 用户调用生成端点且快照不含 `image-generate`
- **THEN** 后端 MUST 返回 403 `feature_required`，不产生供应商调用

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
- **THEN** 系统 MUST 返回 409 `job_active_exists`；相同 idempotency key 的重复提交 SHALL 返回原任务

#### Scenario: 应用重启恢复

- **WHEN** 应用启动时存在 running 图像任务
- **THEN** 系统 SHALL 将其置为 failed（`interrupted`），用户可重试；已产生候选保留

### Requirement: 供应商适配与错误分类

系统 SHALL 通过统一适配层调用图像供应商：OpenAI images 形态（火山/智谱/OpenAI/兼容）、DashScope multimodal-generation、MiniMax image_generation。供应商返回的 b64/URL SHALL 收敛为图片字节；URL MUST 仅允许 http(s)、禁止重定向/内网/本机/带凭据链接且 ≤10MB。调用失败 SHALL 归类为 auth/quota/rate_limit/moderation/timeout/network/invalid/empty。日志 MUST NOT 记录 API Key、prompt 正文或图片字节。

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
