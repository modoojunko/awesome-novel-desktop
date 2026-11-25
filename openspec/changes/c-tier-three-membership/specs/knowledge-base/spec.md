## REMOVED Requirements

### Requirement: 按题材取文风草稿（只读）

**Reason**: 三档会员把官方写作知识库（含按题材取文风）收为 PRO 权益；原条款未设档位门，标准（免费）可直接从官方库取草稿。

**Migration**: 由 ADDED「按题材取文风草稿（PRO）」承接：端点挂 `kb-official`（PRO），标准（免费）面板显示锁定与升级出口，手填文风不受影响。

## ADDED Requirements

### Requirement: 本地库与官方库分层访问

- 知识库 SHALL 分两层：**本地层**（本书设定/人物/决策档案/用户条目/拆书产物入库）与**官方层**（官方写作知识库 331 本基线、官方写法条目、官方知识树/图谱节点）。
- 本地层 SHALL 对标准（免费）可用：浏览、检索、手填、编辑、删除；助理 `kb_search`/`kb_read` 读本地层 SHALL 免费。
- 官方层 SHALL 挂 `kb-official`（PRO 起）：官方库查询、官方写法检索、按题材取文风、官方知识树/图谱节点读取；标准（免费）入口可见但锁定，点击走 PRO 升级出口。
- 助理代收录/修改本地库（`kb_create_entry`/`kb_update_entry`）SHALL 属写类工具，挂 `assistant-execute`（PRO 起）；标准（免费）可手填，不能让助理代写。
- 拆书产物收进知识库 SHALL 写入本地层，挂 `deconstruct`（PRO）；一键建书挂 `deconstruct-import`（MAX）。
- 知识库基线同步/探针属系统内部能力，SHALL NOT 直接向作家暴露；官方层消费才挂 `kb-official`。

#### Scenario: 标准（免费）看本书库

- **WHEN** 标准（免费）用户打开本书知识库/决策档案
- **THEN** 可浏览、检索、手填、编辑；助理可读本地层

#### Scenario: 标准（免费）开官方库

- **WHEN** 标准（免费）用户打开官方写作知识库
- **THEN** 入口可见但锁定，显示「PRO 专属」与升级出口；不返回官方条目内容

#### Scenario: PRO 用官方库

- **WHEN** PRO 用户检索官方库或点「按题材填文风」
- **THEN** 正常返回官方层内容；本地层照常可用

#### Scenario: 助理代收录

- **WHEN** 标准（免费）用户让助手「把这条笔记收进知识库」
- **THEN** 助手回 PRO 升级引导，不写入；PRO 用户可授权写入本地层

### Requirement: 按题材取文风草稿（PRO）

- 系统 SHALL 提供只读端点 `GET /api/novels/{project_id}/settings/style/kb-draft`，按本书题材返回官方库文风基线草稿，供文风面板「按题材填文风」使用。
- 端点 SHALL 挂 `kb-official`（PRO 起）；标准（免费）调用 SHALL 返回 `feature_required` 与 `tier_required=pro`，前端显示锁定与升级出口。
- 端点 SHALL NOT 写任何 KV 或表；采纳后的保存仍走 `PUT /settings/style`。
- 标准（免费）文风面板 SHALL 保留手填三区（叙事身份/硬约束/描写手法），不得因官方草稿锁定而阻断保存。

#### Scenario: 标准（免费）取草稿被拒

- **WHEN** 标准（免费）用户点「按题材填文风」
- **THEN** 端点返回 `feature_required`/`tier_required=pro`，面板显示 PRO 升级出口；手填三区仍可保存

#### Scenario: PRO 取草稿

- **WHEN** PRO 用户点「按题材填文风」
- **THEN** 返回同题材草稿（句式规则带 severity），采纳后仅填表单，不落库
