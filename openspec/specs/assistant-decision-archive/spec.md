# assistant-decision-archive Specification

## Purpose

书级项目决策的分层记忆：决策以 append-only 档案文件全量留痕（永不截断），系统提示词分层注入（最近全文→更早索引→尾注计数），agent 经 recall_decisions 按需召回——半年前作家的决定近期不被遗忘。

## Requirements

### Requirement: 决策档案文件契约

本书项目决策 SHALL 以 JSONL append-only 持久化于 `DATA_ROOT/decisions/<novel_id>.jsonl`，每行一条（id/decision/reason/created_at），全量留档永不截断。追加 SHALL 为单行 append；删除（删书级联）SHALL 移除整个档案文件。决策写入与读取 SHALL 走文件，DB book_decisions 表 SHALL 停止读写（存量迁移后归档）。

#### Scenario: 决定落盘可直读
- **WHEN** 作家拍板「主角不能飞」，agent 调 remember_decision 留痕
- **THEN** `decisions/<novel_id>.jsonl` 追加一行含 decision/reason/日期，文本编辑器可直接读

#### Scenario: 删书级联
- **WHEN** 作家删除一本书
- **THEN** 该书决策档案文件一并移除（零孤儿）

### Requirement: 分层注入

系统提示词的决策段 SHALL 分层：注入预算内的最近决策保留全文；超预算的更早决策 SHALL 降级为「日期＋一句话」索引行（索引自身设预算上限）；仍有更早者 SHALL 以尾注告知在档总条数与召回途径。SHALL NOT 静默丢弃超出预算的决策（现截断行为退役）。书级写作规矩段（800 字层）维持现状。

#### Scenario: 老决定降级为索引
- **WHEN** 决策全文超出注入预算
- **THEN** 最近决策全文注入，更早决策以「[日期] 一句话」索引行注入，尾注告知「另有 N 条在档」

#### Scenario: 半年前的决定有索引可查
- **WHEN** 半年前的一条决定已不在全文预算内
- **THEN** 其索引行仍在注入段中（日期＋一句话），agent 据此可召回全文

### Requirement: 按需召回工具

agent SHALL 提供 recall_decisions 工具（read 类免授权）：按关键词子串过滤（decision/reason 不区分大小写）与条数上限返回档案中的历史决策（含日期与理由）。工具 SHALL 在所有页签域可见（共享读集合）。输出 SHALL 对单条超长决策裁剪。

#### Scenario: 作家提起半年前的决定
- **WHEN** 作家说「之前不是说主角不能飞吗」且该决定只存在于索引层
- **THEN** agent 调 recall_decisions("飞") 拉到全文（含日期与理由），如实按档案回答

#### Scenario: 空档案
- **WHEN** 本书还没有任何决策时调用
- **THEN** 返回如实的空提示（不编造）

### Requirement: 存量迁移

启动迁移 SHALL 把 DB book_decisions 表存量按同契约追加写入决策档案（幂等：同 id 已在档即跳过）；DB 行 SHALL 保留归档（代码不再读写）；迁移失败 SHALL NOT 阻塞启动。

#### Scenario: 老决定进档案
- **WHEN** 带存量决策的旧库启动新版
- **THEN** 决策档案包含全部存量决策，注入与召回可见；重复启动不重复写入
