## Context

c-og-slim-v2 已完成章纲页面字段与「无消费者提示词格子」的退役，但保留了三张同类历史子表（`chapter_knowledge_states`／`chapter_downtime_functions`／`chapter_key_choices`，当时列为非目标）。本次按同一判据复核确认零消费方后拆除。机制完全复用 c-og-slim-v2 已验证的套路（模型摘除、拆装三处收口、备份删键升版、旧包忽略计数、迁入列交集），本文件只写差异点。

## Goals / Non-Goals

**Goals**
- 三张子表随模型与拆装链摘除；章装配不再输出 `memo.downtime_functions`/`memo.key_choices`/`knowledge_states`。
- 备份包 FORMAT_VERSION 5→6；v5 及更早包的这三个键按忽略处理并计入导入报告的「忽略 N 处」。
- 旧库迁入走列交集（三张子表整表不搬），无 DDL。

**Non-Goals**
- 不动 `chapter_payoff_items`（must_resolve/must_hold 两档活跃）与五张留存子表。
- 不做旧数据兼容搬运（零用户口径不变）。
- 不清理 c-og-slim-v2 已退役的其余字段（已完成）。

## Decisions

**D1 与 c-og-slim-v2 的差异：只有「删」，没有「搬」。**
c-og-slim-v2 删的页面格大多有提示词消费点要换源；这三张子表零读取点，拆装链摘除后没有任何消费方需要改代码。风险集中在拆装收口的完整性（三处同批：装配停输出、`_CHILD_ATTRS` 去项、`_replace_children_impl` 删显式赋值——漏一处即「停发即清空」或「输出脏键」）。

**D2 `_split_labeled` helper 保留。**
该 helper 同时被**留存的** `required_changes` 子表拆装使用（store.py ~352 行）——初稿误判为 downtime_functions 独占，grep 更正后保留（删了会把「关系：与地头蛇撕破脸」拆成 change_type＋content 的逻辑砸掉）。随本 change 只删三张子表的拆装赋值与模型类。

**D3 retired-key 计数集合扩容，不新造机制。**
c-og-slim-v2 在 `backup/importer.py` 落了 `_RETIRED_CHAPTER_TOP`/`_RETIRED_OUTLINE`/`_RETIRED_EMOTIONAL` 三组计数集合；本批把三张子表键加进 `_RETIRED_CHAPTER_TOP`，`memo.downtime_functions`/`memo.key_choices` 加进 memo 级计数。导入报告沿用「忽略 N 处」口径。

**D4 备份 v6 只删键、不加键。**
c-og-slim-v2 的 v5 没有加任何新键（只删），v6 同样纯删——读窗策略沿用「N-1 及更早包可过版本门槛、退役键忽略」。

## Risks / Trade-offs

- [拆装收口漏一处] → 三处同批改 ＋ 专项测试（含三子表键的章保存一次 → 装配不含三键 ＋ 留存字段逐字不变）。
- [旧包内容永久丢失] → 零用户口径下属预期；导入报告计数让丢失可核对（D3）。
- [规格漂移] → delta 只动 `chapter-data`（本章能力）；`chapter-plot-items`／`chapter-plan-ai` 等其他 capability 不受三张子表影响（grep 确认零引用）。

## Migration Plan

单批落地（模型摘除＋拆装收口＋备份升 v6），随下一个 C端 版本生效（与 c-og-slim-v2 同批或其后均可——若同批发布，v6 直接覆盖 v5 的读窗）。回滚＝revert。

## Open Questions

（无）
