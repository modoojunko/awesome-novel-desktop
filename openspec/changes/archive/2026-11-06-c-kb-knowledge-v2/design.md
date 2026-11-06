# c-kb-knowledge-v2 · Design

## Context

现状：知识是 `kb_entries` 单表一行（instruction/example/evidence/src_* 内嵌），关系在 `kb_relations`（条目 id 两端）。消费端 `write/write_block.py`、`kb/match.py`、`kb/book_scope.py`、`kb/merged.py`、拆书导入与备份都直接读写 `kb_entries`。浏览页签为 列表/图谱/条目图，星图原型已把「图谱/条目图」替换为「星图」。

约束：C端 单用户桌面、SQLite、无 alembic（迁移走启动期/一次性脚本）；知识库是账号级域 + 书级域；六类注册表与 D6 概念相容矩阵是既有硬口径；原型已定稿（`docs/design-c/drafts/`）。

## Goals / Non-Goals

**Goals:**
- 知识/实例/关系三表承载落地，知识 id、实例 id、关系两端知识 id
- 一个知识多个实例；版本、创建、更新时间
- 增删改查页面与 Obsidian 式知识视图/编辑器
- 星图视图（单一大星系，概念节点，D6 合法边）
- 旧数据就地升级（幂等、可回滚）；消费端（写法块/匹配/书级/备份）同步改造

**Non-Goals:**
- 不扩 D6 概念相容矩阵（跨概念关系仍只从「手法」发出）
- 不做子概念种子（星图仍只到六类概念）
- 不改视觉令牌/共享设计段
- 不做多用户/云同步

## Decisions

### D1 三表承载：知识主体原地升级，实例独立成表

知识主体＝`kb_entries` 原地加列升级（`definition`/`version`/`origin`/`archived_at` 四列，`KbEntry` 补 ORM 字段，消费端以 `KbKnowledge = KbEntry` 别名统一口径）；`kb_knowledge_instances`（1:N 实例，独立 id）为新建表；`kb_relations` 沿用原表（两端 id 即知识 id），辅以 `kb_knowledge_aliases`、`kb_knowledge_revisions`。

理由：实例是独立生命周期（增删/排序/多来源），塞在知识行里无法表达 1:N；版本历史需要快照。替代方案「给 kb_entries 加 instance_json」被否：查询/排序/级联都难，且与「实例有 id」冲突。另建 `kb_knowledge` 独立主表的方案也未采纳：39 处消费端与关系/书级副本/备份全部引用 `kb_entries.id`，整表搬迁改动面大而语义收益为零——原地加列达到同一模型语义。

### D2 知识 id 沿用旧条目 id

原地升级下 `kb_entries.id` 天然保留为知识 id，关系两端不换 id，拆书幂等键 `src_ref/src_key` 继续落在知识主体行上。

替代方案「重新生成 id + 映射表」被否：关系/书级副本/备份引用面太大，收益为零。

### D3 定义与实例分离

`definition` 是知识的一般性定义；实例是具体案例（文本＋出处＋原文摘句）。迁移时旧 `instruction` 落为实例文本，`definition` 置空并显示「知识定义待补」——**不把实例冒充定义**（原型评审已纠）。

### D4 关系表沿用：知识 id + 口径闸门在应用层

`kb_relations` 表名与行不迁移，`from_id/to_id`（即 `kb_entries.id`）语义升级为知识 id。六类白名单、概念相容矩阵、active 唯一、禁自环全部在应用层闸门校验（组织/整理写入前），SQLite 不落 CHECK／部分唯一索引。

理由：矩阵是领域规则会演进，DDL 写死会锁死；沿用原表省一次搬迁，「应用层闸」与现行写入路径一致（此前也未落 DDL 约束）。

### D5 版本与时间

`version` 整数在知识主体行上（`kb_entries.version`），保存 +1；`updated_at` 跟随；`created_at` 不变。`kb_knowledge_revisions` 保留最近 20 版快照（主体＋实例＋关系），用于回滚/审计。更新用应用层显式赋值，不依赖 SQLite 触发器（易与批量迁移冲突）。

### D6 消费端改造：改读知识模型，不留双写

写法块、匹配、书级副本、备份、拆书导入全部改读知识模型（`KbKnowledge` 别名＋实例试图取数改造），表名不变；不保留旧口径兼容视图/双写（双写会分叉，且 SQLite 视图不可写）。

替代方案「保留 kb_entries 投影」被否：消费端仍需改关系与实例取数，投影只增加一层失真。

### D7 前端组件拆分

- `StarSeaPanel`：只吃 `genre` 与 `onSelectConcept`，动态 `import("3d-force-graph")` + three；`ResizeObserver` 跟容器；不接管页面 header/tab/搜索
- `KbKnowledgeView`（右侧 500）：知识属性＋正文
- `KbKnowledgeEditor`（右侧 600）：新建/修改共用
- 删除 `KbGraph`、`KbEntryGraphView` 及其 coverage 契约
- 页面 view：`list / starsea`

### D8 星图数据：概念图由矩阵生成，不聚合条目关系

星图节点是「题材×六类别」概念；边只取 D6 允许的概念对/方向（手法→文风/文笔 applies_to/derived_from/contradicts；手法→世界设定/角色设定 depends_on/applies_to）。条目关系（`kb_relations`）不聚合进星图，避免同概念自环与噪声；条目关系只在知识视图「关联知识」展示。

替代方案「按条目关系聚合成概念边」被否：会产生自环/权重失真，且与 D6 语义不一致。

### D9 迁移与回滚

启动期一次性迁移：`kb_entries` 原地加列（列在即跳）＋`kb_knowledge_instances` 建表＋为存量条目就地生成第 1 条实例（按知识 id 去重，幂等）；`kb_relations` 不动。迁移不搬移不删列——回滚以代码版本回退即可，新列/新表对旧代码不可见（旧代码不读即无影响），不依赖独立备份件。`kb_knowledge_migration_backup` 模型预留（随 create_all 建表）但现行迁移不写入。

### D10 依赖与许可

新增 `three`、`3d-force-graph`（MIT，过白名单）；星图场景复用 okf-galaxy-visualizer（MIT），在 `THIRD-PARTY-NOTICES.txt` 增加归属。原型用 CDN 仅为评审，实现落 npm 本地打包。

### D11 原型设计语言对齐

所有页面壳、抽屉、表单、属性表、实例编辑器、确认弹窗、Toast 一律用 `base.css` 的 oklch 令牌与语义组件（btn-primary/secondary/ghost、pill-tag/status、ListEditor、ConfirmGuard、Toast 底部右侧）；不引入第二种视觉语言。两处例外有先例：① 画布内的星点/连线必须用具体 hex（WebGL 不认 oklch），沿用 `KbGraph.tokenColors()` 的 token→canvas 实色口径；② 知识视图沿用现有 384 抽屉，编辑器为加宽变体（520），在 `prototypes/ADJUSTMENTS.md` 登记。

## Risks / Trade-offs

- **迁移破坏存量** → 原地加列不搬行不删列 + 幂等 + 真机库快照对拍；回滚＝代码版本回退
- **消费端漏改**（写法块/匹配/书级/备份仍读 kb_entries）→ 全仓 grep `kb_entries` 清单化，逐处改造并跑既有后端全量测试
- **星图性能/兼容**（WebGL、集显）→ 28 节点量级，动态 import；WebGL 不可用降级列表并给可点击出口；`prefers-reduced-motion` 停自动旋转
- **本体天花板**（矩阵只允许手法跨概念）→ 星图保持现状并在文档登记；扩矩阵另开 change
- **删除语义**（作家以为硬删）→ 只归档 + 确认弹窗写明可恢复；官方精选只给副本/隐藏
- **版本膨胀** → 只留最近 20 版快照

## Migration Plan

1. `kb_entries` 原地加四列（幂等 DDL：列在即跳）
2. 建 `kb_knowledge_instances` 表＋索引（幂等 DDL）
3. 就地生成实例：存量条目按 id 去重，instruction→实例 text、evidence/example→摘句（definition 留空待补）
4. `kb_relations` 不动（两端 id 即知识 id）
5. 真机库快照实跑：行数/实例数对拍（演练记录见 tasks 7.7）
6. 回滚：代码版本回退（新列/新表对旧代码不可见，存量行零改动）

## Open Questions

（无——范围与口径已在设计与 specs 中定；实现细节在 tasks 中拆解）
