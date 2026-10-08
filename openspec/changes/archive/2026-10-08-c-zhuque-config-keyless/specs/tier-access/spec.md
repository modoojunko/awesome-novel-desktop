## MODIFIED Requirements

### Requirement: 端点门禁对拍守卫

门禁对拍测试 SHALL 真实枚举全部已注册路由上的 feature key 标注并双向断言，SHALL NOT 因框架路由表的懒加载包装而空扫通过：

- 扫描 SHALL 穿透框架懒路由包装（starlette ≥1.6 的 `_IncludedRouter` 等形态），枚举结果 MUST 非空（现状仓库 ≥40 个挂 key 端点，随功能增长只增不减）；
- 已挂 key 的端点 SHALL 同时挂载**与其 key 相称**的 AI 门禁——key 标注不得成为无门死标注，也不得错挂门型。两种门分工：`require_ai_access`＝会员＋档位＋已配写作大模型 Key，为 LLM 类 key 的唯一合法门；`require_tier_access`＝会员＋档位（Key 由作者自持），**仅**白名单 key（`ai-detect`／`prompt-panel`）可用——白名单外的 key 若只剩键自持门即判失败（防「生成类端点错挂键自持门」把未配模型的作者放行到业务深处）；
- 端点声明的 key MUST ∈ 门禁 key 词汇表（含 AI 的档位 key 全集，免费键除外）；
- 关键档位 key（`chapter-review`、`style-quant`、`ai-plot`、`ai-polish`、`ai-detect`、`ai-generate`、`prompt-panel`、`ai-plan`、`settings-ai-fields`、`style-suggest`）SHALL 各有至少一个真实端点消费点。

#### Scenario: 扫描穿透懒路由包装

- **GIVEN** 框架以懒包装形态暴露路由表（顶层非可直接识别的端点对象）
- **WHEN** 门禁对拍测试运行
- **THEN** 全部已挂 key 的端点被枚举（结果非空），并与登记消费点清单一致——SHALL NOT 空扫通过

#### Scenario: 死标注被拒

- **GIVEN** 某端点挂了 feature key 但未挂任一 AI 门依赖
- **WHEN** 门禁对拍测试运行
- **THEN** 测试失败并点名该端点，提示补相称的门或移除标注

#### Scenario: 错挂门型被拒

- **GIVEN** 某 LLM 类 key（如 `ai-generate`）的端点只挂了 `require_tier_access`（或反之：白名单外的 key 用键自持门）
- **WHEN** 门禁对拍测试运行
- **THEN** 测试失败并点名该端点与 key——未配写作大模型的作者 SHALL NOT 因此被放行到业务深处才失败

#### Scenario: 白名单自身失效被拒

- **GIVEN** 键自持门白名单为空、或含不在门禁词汇表内的 key
- **WHEN** 门禁对拍测试运行
- **THEN** 测试失败（守卫不得退化成「任何门都算」）

#### Scenario: 拼错或未登记 key 被拒

- **GIVEN** 某端点声明的 key 不在门禁词汇表内
- **WHEN** 门禁对拍测试运行
- **THEN** 测试失败并点名该端点与 key（防「快照发了 key、端点没挂门」与拼错 key 静默开洞）
