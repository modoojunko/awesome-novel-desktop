## MODIFIED Requirements

### Requirement: 检测门禁与额度口径

- 后端检测端点 SHALL 要求登录，并挂 feature key `ai-detect` 门禁（仅 MAX 发放，trial 不含；403 feature_required 契约见 tier-access）——「MAX 精确门禁由前端 useFeature 判定」的过渡态退役，改为后端真门＋前端 useFeature 双层（前端锁定形态见 zhuque-workbench）；本地门禁 UX 级可绕过为定价文档已认账口径。
- 端点 SHALL 区分「会员但朱雀 Key 缺失/刚被删除」的分支（503，`zhuque_not_configured`，提示指向模型配置朱雀页签），SHALL NOT 把它混入 401 语义。
- 端点 SHALL 把上游每次实际扣减额度（`makers_models_usage.total_tokens`，缺失回退 `usage.total_tokens`）记入本地用量留痕（独立 operation="zhuque-check"，model 记 "zhuque"）；既有用量汇总查询（总量/按配置/按项目）SHALL 排除该 operation，SHALL NOT 混入写作模型用量统计；C端 SHALL NOT 提供朱雀月度额度统计，月度用量一律引导腾讯云控制台查看。

#### Scenario: 上游 401 映射为 Key 无效

- Given 作者配置的 Key 已在腾讯侧失效
- When 发起检测
- Then 返回 401 语义错误，前端失败条显示「API Key 无效或已失效」＋「去配置」「重试」出口

#### Scenario: 限流与额度耗尽同口径

- Given 作者 Key 有效且非本地原因
- When 上游返回 429（限流或免费额度耗尽）
- Then 端点透传可读原因，前端文案为「触发限流或本月免费额度已用完，以腾讯云控制台为准」＋「重试」出口

#### Scenario: 会员但未配朱雀 Key 直调端点

- Given MAX 作者（含 ai-detect 权益）已配任一写作大模型 Key，但朱雀 Key 缺失或刚被删除
- When 端点被调用
- Then 返回 503（zhuque_not_configured），SHALL NOT 误报为 401 Key 无效
- 注：作者**任何 Key 都没有**时，模型就绪门的通用 503（AI 服务未配置）在 ai-detect 门之后判定——非 MAX 用户先吃 403 feature_required

#### Scenario: 同章并发检测被拒

- Given 同一作者同一章的检测请求在途
- When 第二发请求到达
- Then 返回 409（zhuque_check_in_progress），前端映射为「检测中」既有态
