# archive-reconcile 变更（增量）

## ADDED Requirements

### Requirement: 按需触发本章收尾（run）

- 系统 SHALL 提供 `POST /api/novels/{id}/chapters/{ref}/reconcile/run`：body `kind` 限一类（KINDS 白名单，非法 400），缺省 SHALL 跑全量五类；挂 PRO 与本书模型双门控（拦截零模型调用）。
- 命中单飞语义：同章已有收尾在跑 SHALL 返回 `started=false`（不排队、不报错）；产出仍为 `chapter_reconcile` 待确认行（提案制不变。
- 工作台右栏「AI 辅助」SHALL 以「归档后可点」的三入口接线：设定「提取本章变化」→set_changes、关系「识别角色与物品变化」→relations、伏笔「登记新伏笔」→hooks；触发成功/已有任务在跑 SHALL 以 toast 指路「产出在『操作』页签待确认」；未归档章节三入口禁用。其余占位动作保持「规划中」。

#### Scenario: 按类触发只跑该类
- **WHEN** PRO 用户点「登记新伏笔」
- **THEN** 以 kinds=[hooks] 启动本章收尾；产出（若有）出现在「操作」页签待确认

#### Scenario: 缺省全量
- **WHEN** 请求不带 kind
- **THEN** 按全量五类启动

#### Scenario: 单飞
- **WHEN** 本章已有收尾在跑时再次触发
- **THEN** 返回 started=false，不排队不报错

#### Scenario: 未归档禁用
- **WHEN** 章节尚未归档
- **THEN** 三入口禁用（产出位置「操作」页签此时不可见）
