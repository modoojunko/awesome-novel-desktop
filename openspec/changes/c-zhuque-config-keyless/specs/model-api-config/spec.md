## ADDED Requirements

### Requirement: Key 判据与引导（两个 Key 世界互不顶替）

- 「已配写作大模型 Key」判据 SHALL 单源在判定层 `user_has_ai_key`（门控层不得内联重写）：候选取 active 行、按**可解密口径**（死文不算已配）、排除 `vendor="zhuque"`，并保留旧 `User.api_key` 与 config.json 的迁移期兜底。
- 会员调用**使用大模型的功能**而该判据为假时，端点 SHALL 返回 503 且文案指向写作大模型配置口（「模型配置 → 写作大模型」）；SHALL NOT 用不区分 Key 归属的含糊措辞（如「AI 服务未配置」）让用户不知道该配哪把 Key。
- 朱雀 Key 的配置状态 SHALL NOT 参与该判据：只配朱雀 SHALL NOT 影响任何大模型功能的可用性判定；对称地，写作大模型 Key SHALL NOT 顶替朱雀 Key——朱雀检测未配置时按其自身 503 引导（见 zhuque-detection）。

#### Scenario: 只配朱雀 → 大模型功能提示去配大模型

- **GIVEN** 会员只配了朱雀 Key（无任何写作大模型 Key）
- **WHEN** 调用任一需要写作大模型的功能
- **THEN** 返回 503，文案含「写作大模型」并指向「模型配置 → 写作大模型」；SHALL NOT 因朱雀行存在而放行、再在更深处失败

#### Scenario: 只配大模型 → 朱雀功能各自引导

- **GIVEN** 会员只配了写作大模型 Key（未配朱雀）
- **WHEN** 打开模型配置页朱雀页签，或发起朱雀检测
- **THEN** 页签配置动作照常可完成（配置不分套餐权益）；检测返回 503 `zhuque_not_configured` 指向朱雀配置口——写作大模型配置 SHALL NOT 顶替朱雀 Key
