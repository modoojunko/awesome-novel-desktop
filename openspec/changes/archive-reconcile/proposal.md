## Why

归档一章后，AI 产出散落三处且处置方式不一：伏笔留痕自动写库（无确认）、世界 lore 建议随响应即焚（采纳靠当页）、角色状态写入 legacy YAML（v2 已真表化，疑为死路径）。storyline.html 原型给出的目标形态是：归档即刻生效，AI 收尾活放后台跑，产出一律是**待确认提案**——不确认不进全书、不进后续章节的提示词。同时原型中栏的「设定/角色关系/伏笔」页签需要「本章变化 / 截至本章」两个视图，这要求每条数据都能回答「从哪一章来」。本变更按用户约束「同样的对象不另建新表」落地：**不给设定/关系/伏笔建账本表，只给既有对象补「来源章」并做派生投影**；唯一新增的表存的是新对象——收尾产出本身。

## What Changes

- **来源章补齐（同对象加列，零新表）**：`character_relations` 加 `origin_chapter_id`（FK SET NULL，对齐 novel_hooks 的章引用做法；存量 `ch_ref` 字符串一次性解析回填，解析不了的留空）；`chapter_characters` 加 `state_change` 文本列（本章该角色的状态变化一句话；替代 legacy `character-setting/*.yaml` 的 `state_history` 追加路径）。`novel_hooks` 与世界 lore 的 origin **零改动**（已有章引用/origin 字段）。
- **归档收尾改提案制（唯一新表）**：新表 `chapter_reconcile`（每行＝某章某类收尾的一次产出：kind ∈ 设定变化/角色关系/伏笔登记，status ∈ 待确认/已采纳/已驳回/失败，payload 只存**待确认的差异**不复存对象数据；采纳时调目标对象自己的服务写回）。归档的同步部分（archives 行、伏笔 mentioned 留痕、threads、状态迁移）保持即刻生效不变；AI 三件收尾活（提取设定变化/关系建议/伏笔登记）迁入后台单飞线程（复用 backup/export 的线程模式），产出落 `chapter_reconcile` 待确认行。
- **伏笔登记改提案**：归档后台对「本章埋下/本章收束」给出登记建议（含证据句），采纳才写 `novel_hooks`；**mentioned 留痕保持自动**（它是事实记录不是判断，维持 write-archive-meta-sync 契约）。世界 lore 建议**收进同一张表**（现状随响应即焚，改为落待确认行，采纳走既有 lore-apply 幂等合并），归档响应不再携带一次性建议。
- **角色状态变化进收尾**：AI 从正文提取「本章各出场角色的状态变化」→ 写 `chapter_characters.state_change`（每章每角色一行，重跑覆盖）——替代 legacy YAML `state_history` 追加（该路径退役，legacy 键保留不删，回滚安全）。
- **「截至本章」投影（派生，零新端点为原则）**：设定/关系/伏笔三处列表把来源章带出，前端组合出「本章变化 / 截至本章」两视图；提示词组装与体检的现有过滤语义不变——**未确认提案不在目标对象上，天然不参与后续章节的提示词**。
- **收尾进度与确认 UI**（工作台中栏新增「设定」与「操作」两页签）：归档后展示收尾进度（进行中/待确认/失败重试），逐条确认/驳回/重试；不确认不阻塞继续写作下一章。
- 退役：`archive/service.py` 的 legacy `update_character_states` YAML 追加路径（legacy 键与既有数据保留）。

## Capabilities

### New Capabilities

- `archive-reconcile`: 归档收尾提案制契约——`chapter_reconcile` 行生命周期（待确认/采纳/驳回/失败/重试）、采纳经目标对象自身服务写回（不复存对象数据）、后台单飞与进度查询、未确认提案不参与提示词、世界 lore 建议入表、角色状态变化落到出场引用、免费/PRO 门控沿用（体检只读免费、收尾 AI 归 PRO）。

### Modified Capabilities

- `character-settings`: 「章节出场引用按角色身份」扩展——出场引用行增加「本章状态变化」字段（AI 收尾产出或手填，重跑覆盖）；「人物关系为单向视角」补充——关系记录可携带来源章（origin），来源随章回退语义一并可见。
- `write-archive-meta-sync`: 归档联动的处置方式分化——伏笔 mentioned 留痕保持自动即刻；角色状态变化改落出场引用行；AI 收尾（设定变化/关系/伏笔登记/lore 建议）改提案制入 `chapter_reconcile`，不再随响应即焚。
- `backup-restore`: 双包契约补登——`chapter_characters.state_change`、`character_relations.origin_chapter_id` 随对象导出/导入（含 ref↔id 重绑）；`chapter_reconcile` 属运行态待办**不随包**（登记归属即界外）。
- `workbench`: 工作台中栏新增「设定」「操作」两页签（设定＝本章变化编辑/截至本章投影；操作＝归档收尾进度与提案确认），归档入口语义不变。

## Design Impact

- 受影响端：**C端**（工作台中栏两新页签＋归档收尾 UI）；后端为行为与存储调整（无 S端 界面改动）。
- 对象状态：新增「待确认/已采纳/已驳回/失败」四态（收尾提案行，沿用 info/ok/err/warn 语气映射，无新语气档）；「进行中」复用既有进行中语义。
- 共享段：未触碰（新 UI 均在 `.wb` 屏级作用域内）→ 免 design-cross。
- 原型先行：storyline.html 已给出目标形态（中栏设定/操作页签、收尾进度、提案确认卡），实现侧按其移植并照例在 ADJUSTMENTS 登记；book.html 本期不动（新页签属 storyline 范围，实现先行、原型随验收补）。

## Impact

- 后端：`models/`（character_relations/chapter_characters 加列、新模型 ChapterReconcile）、`archive/`（service 拆同步/后台、reconcile 服务）、`write/`（提示词组装不变；`auxiliary.py` 的 legacy YAML 读路径随退役清理）、`chapters/`（出场引用读写带 state_change）；schema 走幂等 ALTER＋指纹，含存量 `ch_ref` 回填。
- 前端：`ChapterWorkspace`（页签 3→5）、`ChapterStore`（收尾状态轮询）、新组件（提案确认卡/收尾进度/本章变化行编辑）。
- AI 成本：归档 AI 调用从「摘要 1 次」变为「摘要＋3 类收尾」，全部走本书模型（用户自配 Key）；免费/PRO 门控沿用现状口径——收尾 AI 归 PRO，免费版归档仍即刻生效且无收尾提案。
- 不随包：`chapter_reconcile`（运行态待办，登记归属即界外）；随包：`state_change`、`origin_chapter_id`（随各自对象）。
