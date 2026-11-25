## REMOVED Requirements

### Requirement: 图像生成与 PRO 权益

**Reason**: 2026-11-25 拍板 AI 图像类全部归 MAX；原条款把 `image-generate` 发放给 trial/pro/max，与三档会员边界冲突。

**Migration**: 由 ADDED「图像生成与 MAX 权益」承接：生成/试画/批量头像/封面画面提取挂 `image-generate`（MAX）；手动上传保持标准（免费）可用。

## ADDED Requirements

### Requirement: 图像生成与 MAX 权益

- 系统 SHALL 通过 `image-generate` 权益键控制 AI 生成/试画/批量头像/封面画面提取：**标准（免费）/PRO/过期** 只能手动上传，**MAX** 可用 AI 生成。
- 后端 MUST 真拦，MUST NOT 只靠前端置灰；标准（免费）/PRO 调用生成端点 SHALL 返回 `feature_required` 且 `tier_required=max`，不产生供应商调用与扣费。
- 手动上传封面/头像 SHALL 保持标准（免费）可用，SHALL NOT 挂 `image-generate`。
- 旧权益快照不含 `image-generate` 时，未过期 MAX SHALL 隐式放行；PRO/标准（免费）/过期 MUST 仍锁定。
- 试用（7 天 PRO）SHALL NOT 含 AI 图像；试用期点生成走 MAX 升级出口。
- 生成 SHALL 按供应商能力发送 negative/seed/watermark；不支持的字段 MUST 从 effective request 与 hash 中剔除。
- 批量头像 SHALL 仅 MAX 可用；单张上传与手动替换不受影响。

#### Scenario: PRO 生成被拒

- **WHEN** PRO 用户调用封面/头像生成端点且快照不含 `image-generate`
- **THEN** 后端返回 `feature_required`/`tier_required=max`，不产生供应商调用与扣费

#### Scenario: MAX 生成可用

- **WHEN** MAX 用户的快照含 `image-generate`
- **THEN** 生成/试画/批量头像/封面画面提取正常可用

#### Scenario: 手动上传不受影响

- **WHEN** 标准（免费）用户上传封面或头像
- **THEN** 上传、采用、撤销正常；AI 生成入口锁定并走 MAX 升级出口

#### Scenario: 旧快照隐式放行

- **WHEN** 未过期 MAX 用户的完整旧快照缺少 `image-generate`
- **THEN** 后端按 MAX 隐式放行；PRO/标准（免费）/过期仍锁定
