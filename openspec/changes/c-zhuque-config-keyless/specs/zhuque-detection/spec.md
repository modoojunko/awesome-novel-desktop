## MODIFIED Requirements

### Requirement: 检测门禁与额度口径

- 后端检测端点 SHALL 要求登录，并挂 **会员＋`ai-detect` 档位门**（`require_tier_access`：非会员 403 `member_required`、档位不够 403 `feature_required`；**SHALL NOT 挂含「已配写作大模型 Key」判据的 `require_ai_access`**——朱雀 Key 自持，检测不依赖写作模型配置）；前端 `useFeature("ai-detect")` 快照锁定为第二层（锁定形态见 zhuque-workbench）；本地门禁 UX 级可绕过为定价文档已认账口径。
- 端点 SHALL 区分「会员但朱雀 Key 缺失/刚被删除」的分支（503，`zhuque_not_configured`，提示指向模型配置朱雀页签），SHALL NOT 把它混入 401 语义，SHALL NOT 被通用 503「AI 服务未配置 — 请先在设置中填写 API Key」盖过（2026-10-08 拍板：使用口同换键自持门）。
- 端点 SHALL 把上游每次实际扣减额度（`makers_models_usage.total_tokens`，缺失回退 `usage.total_tokens`）记入本地用量留痕（独立 operation="zhuque-check"，model 记 "zhuque"）；既有用量汇总查询（总量/按配置/按项目）SHALL 排除该 operation，SHALL NOT 混入写作模型用量统计；C端 SHALL NOT 提供朱雀月度额度统计，月度用量一律引导腾讯云控制台查看。

#### Scenario: 上游 401 映射为 Key 无效

- **GIVEN** 作者配置的 Key 已在腾讯侧失效
- **WHEN** 发起检测
- **THEN** 返回 401 语义错误，前端失败条显示「API Key 无效或已失效」＋「去配置」「重试」出口

#### Scenario: 限流与额度耗尽同口径

- **GIVEN** 作者 Key 有效且非本地原因
- **WHEN** 上游返回 429（限流或免费额度耗尽）
- **THEN** 端点透传可读原因，前端文案为「触发限流或本月免费额度已用完，以腾讯云控制台为准」＋「重试」出口

#### Scenario: 会员但未配朱雀 Key 直调端点

- **GIVEN** 有 ai-detect 权益（PRO/试用）的作者，朱雀 Key 缺失或刚被删除（无论其是否配置过写作大模型 Key）
- **WHEN** 端点被调用
- **THEN** 返回 503（`zhuque_not_configured`，提示指向「模型配置 → 朱雀」），SHALL NOT 误报为 401 Key 无效，SHALL NOT 返回通用 503「AI 服务未配置」

#### Scenario: 同章并发检测被拒

- **GIVEN** 同一作者同一章的检测请求在途
- **WHEN** 第二发请求到达
- **THEN** 返回 409（`zhuque_check_in_progress`），前端映射为「检测中」既有态
