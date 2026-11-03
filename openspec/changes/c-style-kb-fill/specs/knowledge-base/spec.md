## ADDED Requirements

### Requirement: 按题材取文风草稿（只读）

系统 SHALL 提供只读端点 `GET /api/novels/{project_id}/settings/style/kb-draft`，按本书题材（`story.yaml.genre`，21 大类）返回知识库里的文风基线草稿，供文风面板右栏「按题材填文风」使用。SHALL NOT 写任何 KV 或表——采纳后的保存仍走 `PUT /settings/style`。

取数口径 SHALL 为：同账号用户条目（`status=active`、`concept ∈ {文风, 文笔}`、`genre ∈ {本书题材, 跨题材通用}`）＋官方基线（c-kb-baseline merged 视图：同题材与跨题材通用；用户 hide 的基线 SHALL NOT 出现，用户 edit 副本 SHALL 以其文本为准），且只取基线条目（`when_json` 为空）。槽位映射 SHALL 与启用快照一致：文风 `role/sample` → 叙事身份/示范段；文笔 `rule/craft/banned_word/tic` → 硬约束/描写手法/禁用词/句式规则。同题材条目 SHALL 排在跨题材通用之前，文本去重。展示上限 SHALL 为 rules 20 / craft 20 / samples 6 / banned_words 100 / tic_patterns 20，并返回逐项 `counts` 与 `total`。`tone/pov/register` 无书内落点，SHALL 只在缺叙事身份时各取第一条拼一句兜底。

#### Scenario: 未定题材

- **WHEN** 本书 `story.yaml` 没有 `genre`
- **THEN** 返回 `theme: ""` 与空数组、`counts.total = 0`（200，不报错），由前端给「先定题材」的引导

#### Scenario: 同题材优先、通用兜底

- **WHEN** 知识库同时存在「悬疑」与「跨题材通用」的文风条目的角色条目
- **THEN** `role` 取同题材那条；`rules/craft/banned_words/tic_patterns` 合并两类并去重，同题材条目排在前面

#### Scenario: 场景条目与已归档条目不进草稿

- **WHEN** 某条文笔规则挂了场景条件（`when_json` 非空），或状态为 archived
- **THEN** 该条 SHALL NOT 出现在草稿的任何数组里

#### Scenario: 句式规则带档次

- **WHEN** 一条 `slot=tic` 的条目载荷带 `tic_severity`
- **THEN** 草稿的 `tic_patterns` 项 SHALL 带同档 `severity`（非法值回落 medium），供表单的句式规则编辑器直接回填
