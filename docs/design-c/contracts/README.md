# deconstruct-graph 契约变更史

> 正身＝`deconstruct-graph-6.schema.json`（本目录）。原型 v1–v7（`docs/design-c/drafts/`）为**示意物**，
> 不再是契约正文——契约正文散落原型注释是 graph/1→6 一天四升的根因（二轮评审判例）。
> 冻结规则：**additive 字段不升版本**；破坏性改动升 `graph/7` 并在本表写明迁移。
> 流程：图谱面任何后续变更＝先 openspec update-change 改 spec/design D8，再动码动测（tasks 10.0 闸）。

| 版本 | 日期 | 变更 | 触发 |
|---|---|---|---|
| graph/1 | 2026-10-14 | 首版：nodes（人/势力/物品）＋edges（kind/戏份/出处章号/原文一句）＋events＋hooks | 原型 v1 关系钉板 |
| graph/2 | 2026-10-14 | ＋places 归属树（parent）＋links 人↔地边 | 用户令：地点要有归属树形 |
| graph/3 | 2026-10-14 | ＋chapters 章索引（no/beat/at/who/ev）——章＝可导航节点 | 用户令：每章一个节点，地点/人物/剧情挂章 |
| graph/4 | 2026-10-14 | ＋chapters[].presence=[{who,where}]（逐章在场） | 用户令：地点为框·人在框中 |
| graph/5 | 2026-10-14 | 坐标出语义正身→独立 layout 块；where 允许 null（未知区）；＋meta.warnings/completion；派生字段代码盖章纪律 | 三路评审：全局 id 错位/不变量过强逼幻觉/坐标内嵌违哲学 |
| graph/6 | 2026-10-14 | ＋relTypes 封闭枚举（五组 19 型）；边＝稳定关系、动作归事件；同义归并/方向规则入表 | 用户令：人物关系要抽象出类型表 |
| （v7 视图令） | 2026-10-14 | 视图分工：关系网不表达地点（不涉契约——视图纪律不入数据） | 用户令：关系网不要体现地点 |

## 跨字段规则（schema 表达不了，归装配器 lint，见 tasks 10.2）

- `edges.kind` ∈ relTypes 扁平集，或 `{kind:"自定义", raw:"原文措辞"}` 逃生口；动作词禁入。
- `presence.where` ∈ places.id 或 null；`where=null` 只进未知区，不算违规。
- id 由装配层分配（label 排序＋序号），**append-only 永不重排**（续拆插入新实体不得平移旧 id）。
- 首现章号＝min(引用章) 代码盖章；`chapters.who/at`、`links` 基线「到过」＝presence 派生。
- parent：只认隶属直陈＋代码传递闭包＋环检测（有环边降 null 留痕）。
- quote 原文回验（去空白/标点模糊匹配）失败→剥 quote 留关系＋warning。
- 双指标：在场覆盖率（出场章有 presence 行）≥97% 硬指标；定位率（where≠null 占比）只报数不设死线。
