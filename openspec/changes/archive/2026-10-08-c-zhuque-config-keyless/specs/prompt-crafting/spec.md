## ADDED Requirements

### Requirement: 提示词取数与编辑不依赖写作大模型配置

- 提示词面板的取数与编辑端点（书目总览 `GET /api/novels/{project_id}/prompt-summary`、章级列表 `GET .../prompts`、内容读取 `GET .../prompts/{seg}`、内容保存 `PUT .../prompts/{seg}`、生成弹窗的提示词预览 `GET .../write/prompt`）SHALL 只挂登录＋`prompt-panel` 档位门（`require_tier_access`）：PRO 及以上（试用同权）SHALL 可查看/编辑/存稿，**SHALL NOT 因其未配置写作大模型 Key 而返回 503**。
- 「未配写作大模型 Key」的引导 SHALL 落在**生成动作**上（正文生成等 `require_ai_access` 端点）：点生成时按 Key 判据返回 503 并提示去「模型配置 → 写作大模型」添加——查看与编辑不会被拦，生成才提示。
- 面板的档位口径不变：无 `prompt-panel` 权益的档位 SHALL 403（`member_required`/`feature_required`），SHALL NOT 因撤 Key 判据而放行。

#### Scenario: PRO 未配模型 Key 仍可看/改已存提示词

- **GIVEN** PRO（或试用）会员，未配置任何写作大模型 Key，某章已有存稿提示词
- **WHEN** 作者打开提示词面板（或 AI 生成正文弹窗）查看并编辑该提示词、点「存为本章提示词」
- **THEN** 读取与保存成功（SHALL NOT 出现 503「尚未配置写作大模型 API Key」），编辑稿落库；同一弹窗的提示词预览照常展示

#### Scenario: 点生成才提示去配模型 Key

- **GIVEN** 同上（PRO、零写作大模型 Key）
- **WHEN** 作者在弹窗内点「生成正文」
- **THEN** 就地得到提示去「模型配置 → 写作大模型」添加 API Key（不整页跳转）；提示词内容与编辑结果不受影响

#### Scenario: 非 PRO 档位仍不可用

- **GIVEN** 免费/标准档作者
- **WHEN** 调用提示词面板任一取数/编辑端点
- **THEN** 403（`member_required`/`feature_required`，`tier_required=pro`）——档位门未因撤 Key 判据而放松
