# c-kb-instance-list · Tasks

## 1. 后端

- [x] 1.1 `kb/service.py` 新增 `list_instances_flat(db, *, user_id, genre, concept, q)`——跨知识实例行（JOIN kb_entries），全量返回、无分页；每行含 row_kind/id/knowledge_id/knowledge_title/chain/genre/concept/text/quote/source_novel/source_chapter/src_kind/created_at；**chain 由后端预载 id→title 映射沿 parent_id 逐级上溯拼好**（映射只取本 user、status='active' 且 archived_at IS NULL 的行，素材行不入映射；孤儿/断链/不可达跳级），题材段不入链；过滤边界逐条落实：JOIN 侧 `user_id` 隔离、实例行要求知识行 `origin != 'material' AND status='active' AND archived_at IS NULL`、素材行 `status='active' AND origin='material' AND concept != '情节'`、`q` 覆盖 text/quote/source_novel＋所属知识名（素材行 instruction/evidence/src_novel_name）、genre/concept 过滤语义与 list_entries 一致；两条查询＋应用层按 created_at 归并倒序（key 对 None 容错）。验证：单测覆盖——genre/concept/q 过滤、instance/material 两类行形状与 row_kind 判别、**已归属素材（archived）不再以素材行出现**、**已归档知识（archived_at 非空）与 merged 知识的实例被排除**、情节素材不出现在列表、孤儿 parent 链跳级不炸、src_kind 归一只出「拆书/手录」两值、created_at 倒序、**跨 user 隔离用例必须 userB 建知识＋其下实例、userA 发请求断言不可见**（不能只造孤立实例行）
- [x] 1.2 `kb/router.py` 新增 `GET /kb/instances` 端点挂该查询（不复制存量 `/entries/{id}/instances` 缺归属校验的模式）。验证：接口测试覆盖过滤参数、空库返回空数组、**响应无 cursor/分页字段（锁死全量返回口径）**

## 2. 前端

- [x] 2.1 `kbApi.ts` 加 `instancesFlat(params)` 封装与行类型（row_kind 判别联合类型）。验证：tsc 通过
- [x] 2.2 `KnowledgeBasePage.tsx` 实例侧列表改实例行列表（每行：行顶归属链——题材段非链接文字、知识各级 accent 色可点带 `data-testid`；行级 `kb-inst-row`/`kb-material-row`、素材标 `kb-row-material-badge`；实例一句话＋出处行——按值渲染空片段不渲染；右侧收录日期＋来源标；素材行「待归属素材」标）；「官方精选/已隐藏」两臂保留现知识行列表（分组/baseline 空态/同步重试/隐藏管理不动）；实例臂内来源（拆书/手录）与「跨题材通用」档客户端过滤、游标「加载更多」只在回退臂、实例臂不跑 entries 主查询（genres 照发）；计数行按实例口径（N 与分类分布同口径、含素材行）；排序控件（最近收录/名称——名称按所属知识名客户端排、素材行排末位）；筛选无命中空态＋「清空筛选」出口；页头副标题更新为原型文案。验证：组件测试——mock 补 `instancesFlat` 进 hoisted api 对象与 mock 展开（防真实现裸奔假绿）；**存量用例迁移：知识行点击类用例改 instancesFlat fixture 或 pin 到官方精选臂、素材提示卡用例改走素材行 fixture**；覆盖行渲染、归属链渲染与可点性、素材标、排序（名称含素材行末位）、空态（零内容题材＋题材/类别/关键词筛选无命中）、官方精选臂回退知识列表、角色设定视角不受影响
- [x] 2.3 点行交互：点实例行 → `kbApi.entry(row.knowledge_id)`、点链上知识级 → `kbApi.entry(chain[i].id)` → 现有知识抽屉（复用 KbEntryRelations 兜底路径）；点素材行 → `kbApi.entry(row.id)` → `setSelected` → 抽屉 material 分支渲染素材提示卡（扁平行不得直接塞 setSelected）。验证：交互测试覆盖两路点击与行内 id 语义

## 3. 回归与验收

- [x] 3.1 后端 kb 子集全绿＋ruff；前端 coverage 契约绿＋tsc 干净
- [ ] 3.2 真机走查：拆书收录 → 素材行出现 → 总结归属 → 素材行消失且实例行出现；官方精选/已隐藏两臂回归；记录截图
