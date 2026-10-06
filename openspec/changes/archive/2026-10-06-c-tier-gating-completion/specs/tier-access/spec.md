## ADDED Requirements

### Requirement: 端点门禁对拍守卫

门禁对拍测试 SHALL 真实枚举全部已注册路由上的 feature key 标注并双向断言，SHALL NOT 因框架路由表的懒加载包装而空扫通过：

- 扫描 SHALL 穿透框架懒路由包装（starlette ≥1.6 的 `_IncludedRouter` 等形态），枚举结果 MUST 非空（现状仓库 ≥40 个挂 key 端点，随功能增长只增不减）；
- 已挂 key 的端点 SHALL 同时挂载档位门禁（`require_ai_access`）——key 标注不得成为无门死标注；
- 端点声明的 key MUST ∈ 门禁 key 词汇表（含 AI 的档位 key 全集，免费键除外）；
- 关键档位 key（`chapter-review`、`style-quant`、`ai-plot`、`ai-polish`、`ai-detect`、`ai-generate`、`prompt-panel`、`ai-plan`、`settings-ai-fields`、`style-suggest`）SHALL 各有至少一个真实端点消费点。

#### Scenario: 扫描穿透懒路由包装

- **GIVEN** 框架以懒包装形态暴露路由表（顶层非可直接识别的端点对象）
- **WHEN** 门禁对拍测试运行
- **THEN** 全部已挂 key 的端点被枚举（结果非空），并与登记消费点清单一致——SHALL NOT 空扫通过

#### Scenario: 死标注被拒

- **GIVEN** 某端点挂了 feature key 但未挂档位门禁依赖
- **WHEN** 门禁对拍测试运行
- **THEN** 测试失败并点名该端点，提示补 `require_ai_access` 或移除标注

#### Scenario: 拼错或未登记 key 被拒

- **GIVEN** 某端点声明的 key 不在门禁词汇表内
- **WHEN** 门禁对拍测试运行
- **THEN** 测试失败并点名该端点与 key（防「快照发了 key、端点没挂门」与拼错 key 静默开洞）

### Requirement: 导入回填 AI 步骤门禁

导入回填流程中真调 AI 的两个步骤（`POST /api/novels/{id}/ai-backfill/step1`、`step2`）SHALL 按 feature key `ai-plan` 门禁（标准档起发放）；纯状态读写的 `status`/`confirm` SHALL NOT 挂会员门。

#### Scenario: 免费档调用被拒

- **GIVEN** 免费档用户
- **WHEN** `POST /ai-backfill/step1` 或 `step2` 被调用
- **THEN** 返回 403（`member_required`，带升级出口语义），SHALL NOT 执行任何 AI 提取

#### Scenario: 标准档及以上放行

- **GIVEN** 权益快照含 `ai-plan` 的档位（标准/PRO/MAX/trial）且已配模型
- **WHEN** `POST /ai-backfill/step1` 或 `step2` 被调用
- **THEN** 过档位门，行为与既有回填流程一致（模型未就绪按既有 503 引导口径）

#### Scenario: 状态端点不设门

- **GIVEN** 任意档位
- **WHEN** `GET /ai-backfill/status` 或 `PUT /ai-backfill/confirm` 被调用
- **THEN** 不因档位被拦截（仅既有登录与项目归属校验）
