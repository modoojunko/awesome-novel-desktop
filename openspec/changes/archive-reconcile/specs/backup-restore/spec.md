# backup-restore 变更（增量）

## MODIFIED Requirements

### Requirement: 双包格式契约 v1

双包契约新增/明确以下字段归属（其余不变）：

- `chapters/{ref}.yaml` 的出场引用行 SHALL 携带 `state_change`（可空）；导入 SHALL 原样落库。
- `relations.yaml` 的关系记录 SHALL 携带 `origin_chapter`（章 ref 形式，可空）；导入 SHALL 按 ref→id 重绑为 `origin_chapter_id`，目标章不存在时 SHALL 留空并计入导入告警（不阻断）。
- `chapter_reconcile`（归档收尾提案/进度）SHALL 属**运行态待办，不随包**——包边界原则：丢了不心疼的内容不进包；登记归属即界外。
- 导出 SHALL 在包内 `manifest` 或相应段登记上述字段的存在（格式版本号不变，加键兼容）。
- 既有约束 SHALL 原样保留：包为数据库无关 yaml/md、N-1 读窗、章引用一律 ref 形态、versions/archives 冻结原文不重排、token_log/模型历史/events 不随包。

#### Scenario: v3 包含伏笔段且不含旧 KV 键

- **WHEN** 对含伏笔的书执行导出
- **THEN** 包内存在 `hooks/hooks.yaml`（章引用为 ref 形态），不存在 `settings/hooks.yaml`

#### Scenario: 备份导出双包

- **WHEN** 已登录用户在设置发起备份并选择保存目录
- **THEN** 所选目录内生成资产包与配置包两个 zip，包含全部活跃书的 8 类资产对象与全部 api_configs（密钥明文，本机解密导出）
- **AND** 用量台账（token_log）、模型切换历史、埋点（events）不出现在任何包内

#### Scenario: 冻结原文不重排

- **WHEN** 导出含版本快照与归档的书
- **THEN** versions/*.json 与 archives/*.md 的内容为库内原文字节级直写，不做任何格式转换

#### Scenario: format_version 演进规则

- **WHEN** 导入端遇到包内 format_version
- **THEN** 缺失（v0 旧包）按兼容模式全量回吃；≤3 全部可导入（1=v1 契约、2=角色 v2、3=本 change 伏笔段）；大于 3 拒绝并提示「请先升级应用」
- **AND** 未来演进：加键=兼容不升版；删键/改布局=升版且导入端保留 N-1 读窗

#### Scenario: 出场引用带状态变化跨机恢复
- **WHEN** 导出含「第 3 章出场沉舟 state_change=从犹豫到决意」的包并在新机导入
- **THEN** 该字段原样恢复，且「截至本章」视图可显示

#### Scenario: 关系来源章跨机重绑
- **WHEN** 导出关系记录 origin_chapter=vol-1-ch-5 并在新机导入
- **THEN** 来源章重绑为对应章 id；若该章缺失则来源留空并出现导入告警

#### Scenario: 收尾提案不随包
- **WHEN** 作者有 3 条待确认提案未处理即导出全书
- **THEN** 包内不含提案数据，新机导入后提案区为空（不视为数据丢失）
