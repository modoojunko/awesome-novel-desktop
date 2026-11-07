# c-kb-instance-list · Design

## Context

知识库列表当前按「知识条目」组织（一行一个 title）。boss 模型（实例是事实层）下，列表应每行一个实例。数据已就绪：`kb_knowledge_instances`（346 条，归属 6 个 summary 知识点）＋素材行（origin='material'，待归属）。现有 `list_instances(knowledge_id)` 只按单知识查询；列表页需要跨知识实例列表。

现状事实（已核实）：
- 素材归属后被**归档**而非删除（summarize 写 `m.status='archived'`）；知识归档只写 `archived_at`、不动 `status`（archive_knowledge）。两类「已消失」的过滤条件不同。
- summarize 建的知识点 `parent_id` 恒为 `''`（挂概念根），爷/父层是树编辑器之后的形态——链解析必须容错孤儿。
- 素材态入库允许 `concept='情节'`，但 summarize 与知识树都排除情节——情节素材**永不归属**。
- `concept` 列即六类类别值（文风/文笔/世界设定/角色设定/手法/情节），`kb_knowledge_instances.source_kind` 存实例来源标（拆书/手录），素材行的 `src_kind ∈ {manual, deconstruct}`。
- 存量 `GET /entries/{entry_id}/instances` 不校验 entry 归属（IDOR）——本 change 不修存量，但新端点不得复制该模式。

约束：SQLite 无 alembic（走 ensure DDL 通道）；实例表无 user_id（靠 knowledge_id JOIN kb_entries 过滤）。

## Goals / Non-Goals

**Goals:**
- 跨知识实例列表端点（genre/concept/q 过滤＋后端拼好的归属链）
- 知识库「我的收录」侧列表改实例行（知识级链可点下钻＋素材标）
- 计数按实例口径（全量返回，计数＝行数）
- 「官方精选 / 已隐藏」臂边界：保留知识行列表，与实例行列表并存

**Non-Goals:**
- 不做手工归属/调树位（编辑器 v2）
- 不改知识详情抽屉；不做「点行后定位到抽屉内具体实例」（抽屉仍按实例群列表展示）
- 不动星图、选择器、CharacterInstanceView（角色设定视角）、写法块消费链
- 不修存量 `/entries/{entry_id}/instances` 的归属校验洞（另立）

## Decisions

### D1 单端点返回扁平行，归属链由后端拼好

`GET /kb/instances?genre=&concept=&q=`：全量返回（无分页/游标——单用户桌面量级数百行，计数行口径自然诚实；量级上来再加分页，挂账 Risks）。每行：

```
{ "row_kind": "instance" | "material",
  "id",                 # instance → kb_knowledge_instances.id；material → kb_entries.id
  "knowledge_id",       # material 行为 ''
  "knowledge_title",    # material 行为 ''
  "chain": [ {"id","title"}, … ],  # 知识各级（末段＝所属知识点 → 逐级父 → 顶层）；material 行为 []
  "genre", "concept",
  "text",               # instance → 实例文本；material → instruction
  "quote",              # instance → 实例摘句；material → evidence
  "source_novel",       # instance → 实例出处书名；material → src_novel_name
  "source_chapter",     # instance → 出处章号；material → ''（kb_entries 无章号列）
  "src_kind",           # 后端归一为「拆书/手录」两个界面值
  "created_at" }
```

- **chain 由后端拼**：查询时预载 kb_entries id→title 映射（**只取本 user、status='active' 且 archived_at IS NULL 的行，素材行不入映射**），从所属知识沿 parent_id 逐级上溯；孤儿/断链/不可达跳级不炸。**不入题材段**——题材不可点且行上已有 genre，前端自行渲染为非链接首段。理由：链中间层常是纯容器知识（无实例无素材行），在实例流水里永不出现，且分页会把父行切出页外——前端沿 parent_id 拼链在这两种情况下都断链，行内自带 chain 数组则零额外往返、fixture 确定。
- 行形状按 `row_kind` 判别（instance/material），前端不再靠 origin 推断；统一 `id` 字段。**注意：instance 行的 `id` 是实例 id，不是 kb_entries id**——点行取数见 D5。
- **列表行不带 fields_json**：列表只渲染一句话＋出处，抽屉点开走既有单知识 `listInstances(knowledge_id)` 重取。带它纯属冗余。
- **出处行空值容错**：拆书链路现状拿不到书名/章号（deconstruct_import 落素材时 `src_novel_name=''` 且建卡无书名入参，summarize 建实例不写 source_chapter）——出处行按值渲染，空片段不渲染、整行无值不渲染出处行。素材出处回填与章号提取另立挂账（Risks）。

### D2 素材行混排与过滤边界

素材行（origin='material'，未归属）以 `row_kind=material` 混排，带「待归属素材」标；归属后从素材查询中消失（被归档），同时以实例行出现——行语义闭环。

过滤条件（tasks 验证清单逐条对应）：
- 实例行：JOIN 侧知识行 `origin != 'material' AND status='active' AND archived_at IS NULL`（只滤 status 会漏归档知识；排除素材行防「给素材 id 塞实例」的脏数据以知识行身份混入——照 query_scope.visible_knowledge_filter 先例）；JOIN `kb_entries.user_id = 当前用户`（不复制存量 IDOR 模式）
- 素材行：`status='active' AND origin='material' AND concept != '情节'`（不滤 active 会让已归属素材永远挂待归属标；情节素材永不归属，排除而不是永远混排——界面已有「情节 · 即将上线」页签承接）
- `genre=''` / `concept=''` 参数＝不过滤；题材/类别过滤语义与既有 `list_entries` 完全一致（含未定题材的现口径），不新造。**例外**：「跨题材通用」档在现 `/entries` 链路是 no-op（genres 回 key='' → 前端不发包 → 全量返回），实例臂不照抄——前端客户端过滤（D4）
- `q`：LIKE，实例行覆盖 text/quote/source_novel＋所属知识名（kb_entries.title），素材行覆盖 instruction/evidence/src_novel_name（与搜索框占位「搜名字、内容、来源书名」对齐）

### D3 排序与查询机制

两条查询（实例 JOIN 素材两态）＋应用层按 created_at 归并倒序——无分页故无「先 limit 再归并乱序」问题；排序 key 对 None 容错（datetime.min 兜底）。实例行 created_at 是归属时刻（每次总结后该批实例靠前）、素材行是收录时刻：语义不同但都是「最近进列表的时间」，可接受；后续要按素材收录时间排再迭代。前端「名称」排序（按所属知识名）为客户端排序（数据已全量在内存）；**素材行无所属知识名，名称排序恒排末位**。

### D4 双数据源臂：实例行列表只服务实例侧

来源筛选臂切换数据源：实例侧来源（现状的 全部来源/拆书/手录）→ **实例行列表**（本 change 新形态）；「官方精选」或「已隐藏」→ **沿用现有知识行列表**（基线层 layer/hidden 语义只住知识行，`/kb/instances` 结构上返回不了基线条目；现有 baseline 空态/同步重试/隐藏管理、题材×类别分组全部不动）。角色设定视角（CharacterInstanceView）由既有 viewMode 门控，不受本改造影响。

实例臂内的筛选分工（数据全量在内存，客户端过滤与 D3 排序同一理由）：**来源「拆书/手录」＝前端按行 src_kind 过滤**（端点不带 src 参数）；**「跨题材通用」档＝前端只留 genre==='' 的行**（现 /entries 链路该档是 no-op，不照抄）；题材/类别/关键词仍走端点参数。侧栏题材与计数（/kb/genres）不动，口径统一不在本 change 范围。游标「加载更多」只在回退臂维护渲染，实例臂不跑 entries 主查询（genres 照发）。

### D5 点行交互：复用既有兜底路径，注意行的 id 语义

**行 `id` 不一概是 kb_entries id**（instance 行 id＝实例 id），点行取数规则：
- 点实例行本体 → `kbApi.entry(row.knowledge_id)`；点链上知识级 → `kbApi.entry(chain[i].id)`；取回 KbEntry → `setSelected` 打开现有知识抽屉（页面里 KbEntryRelations 的跳转兜底已示范该路径）
- 点素材行 → `kbApi.entry(row.id)`（素材行 id 即 kb_entries.id）→ `setSelected` → 抽屉按既有 origin='material' 分支渲染素材提示卡（扁平行缺 payload/rev，不得直接塞 setSelected）

不做抽屉内滚动定位（Non-Goals）。

## Risks / Trade-offs

- 实例数增长后全量列表变长 → 后续加分页/虚拟滚动（当前单用户桌面量级可控，挂账）
- 批量归属后实例行按归属时间跳顶（D3 已定性可接受）
- 拆书链路出处书名/章号现状为空（D1 已容错渲染）——素材出处回填与章号提取另立挂账
- 快照消费链（写法块）不走此列表——选择器/写法块继续按知识行消费，不受影响

## Migration Plan

纯查询新增＋前端改造，无数据迁移。
