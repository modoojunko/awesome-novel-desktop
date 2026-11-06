# c-kb-summarize · Design

## Context

`kb_entries` 是知识主表（v2：`definition/version/origin/archived_at` 四列＋`kb_knowledge_instances` 1:N 实例表）；手录（`create_entry` 手录默认装载把一句话塞概念默认槽位）与拆书收录（`collect_task_to_kb` 建知识＋第 1 条实例）都直接产知识行；AI 整理（`run_organize`）只产关系与建议；提示词仓 sibling `awesome-novel-prompts/prompts/` 平铺 `.prompt` 文件（`kb_organize` 先例：缺失 fail-soft 记 error 不阻断）。

约束：SQLite 无 alembic（DDL 走启动期 ensure 通道，`ensure_kb_knowledge_v2` 先例）；整理面板已有候选确认先例（pending 关系采纳/否决）；单用户桌面。

## Goals / Non-Goals

**Goals:**
- 录入两链路（手录/拆书收录）改产素材行（`origin='material'`）
- 总结管线：聚类素材 → LLM 提炼候选知识 → 确认制采纳 → 建知识（`origin='summary'`）＋素材转实例
- 消费端一致排除素材行；整理面板接总结入口与候选清单
- 存量知识行豁免（不回扫）

**Non-Goals:**
- 不改 AI 关系整理的产关系链路（总结产知识后，关系整理照旧吃知识行）
- 不做素材自动去重/合并（合并建议链路已有，后续可吃素材态）
- 不做跨题材总结（单题材单次，同整理口径）
- 不动星图/选择器逻辑（只新增素材过滤谓词）

## Decisions

### D1 素材态＝`origin='material'` 行，不建新表

素材行用 `kb_entries` 现有形状承载：`origin='material'`＋`instruction`=素材原文＋`evidence/src_*`=出处＋`concept/genre`=归组信号。理由：素材本就是「未来知识的实例内容」，行形状同构；不新增表与同步逻辑。消费端过滤谓词统一为 `origin != 'material'`（星图装配、选择器、写法块、书级副本四处收口在一个查询 helper）；**列表是素材的展示面**——默认视图含素材行（带「素材」标），不滤。

被采纳后素材行转正路径：新知识行建好 → 素材内容写入 `kb_knowledge_instances`（text=素材原文、source_kind/source_novel/source_chapter/quote 随素材行字段）→ 素材行置 archived。审计可回溯。

### D2 总结运行独立落表 `kb_summarize_runs`（ensure DDL 通道建）

不混入 `kb_organize_runs`（语义是关系整理）。字段：id/user_id/genre/status(running/done/error)/materials_scanned/candidates_created/error/created_at。候选落 `kb_summarize_candidates`：id/run_id/genre/concept/proposed_title/proposed_definition/material_ids(json)/status(pending/adopted/dismissed)/created_at。同 genre 单飞（running 存在即跳过，同整理 singleflight 口径）。

### D3 聚类确定性，提炼交 LLM

聚类在应用层：按 `genre+concept` 分桶（素材行已有归组），桶内素材全量给 LLM。提示词 `kb_summarize.prompt` 输出 JSON 候选数组（proposed_title/proposed_definition/material_ids），应用层校验：material_ids 必须属于本桶、标题非空、定义长度闸（≤500 字同示范段闸先例）。LLM 失败/模板缺失 → run 记 error fail-soft，不阻断知识库其他功能。

### D4 确认制采纳，不自动生效

候选 pending 清单进整理面板（复用 pending 关系清单交互先例）：采纳＝建知识行（`origin='summary'`、`status='active'`、`version=1`）＋素材转实例＋素材行归档；忽略＝dismissed（同候选不重复提出）。同一素材被多个候选引用时以先采纳者为准，后采纳的候选自动剔除已用素材 id（应用层校验）。

### D5 触发：手动＋积压自动

手动＝整理面板「总结知识点」按钮；自动＝启动期检查各题材素材积压 ≥5 条时触发一次（复用整理启动钩挂点风格）。触发方式落 runs（同整理 runs 记 trigger 先例）。

### D6 手录与拆书收录改产素材

- 手录：`create_entry` 走 `origin='material'` 路径（concept/genre 保留作归组信号；默认槽位装载逻辑退役——不再用一句话塞示范段槽）；表单提交文案「素材已收录，总结后成为知识点」
- 拆书收录：`collect_task_to_kb` 建素材行（每产物卡一行），不再建知识行＋实例；「收进知识库」幂等键口径不变
- 两条链路的幂等键/去重语义原样保留（src_ref/src_key）

### D7 知识层级＝`kb_entries.parent_id`（树内嵌），关系表保持六类横向

层级是**树**不是图：`kb_entries` 加 `parent_id`（NULL＝直接挂概念根；非 NULL＝挂父知识 id，父知识须同 genre+concept 且非素材行）。**枝干无限嵌套：层级深度不设上限**（boss 拍板 2026-11-06）——唯一约束是环防御：应用层写入闸（parent 链回溯自己即拒）——同 active 唯一「应用层闸」先例，DDL 不落约束。星图的折叠计数是**展示策略**（超深子树默认折叠、点开即展全层），SHALL NOT 变成数据层的深度限制。选择器打分按子树聚合可后续迭代，首版按行打分不变。

### D8 星图树形化：概念根星 → 知识枝干（层级边）＋六类关联边（横向）

`StarSeaPanel` 数据装配从「题材×概念两层」改为「概念根 → 按 parent_id 逐层展开的知识星树」：层级边实线（父子）、关联边虚线（六类，沿用现有配色）；实例不进图，点叶子知识开卡看实例群（知识卡已有实例段）。首屏全层展开口径不变（有多少层显示多少层）；WebGL 不可用降级到列表（口径不变）。Deep 超过 3 层的子树折叠计数（防视觉爆炸），点折叠星展开。

### D9 消费端过滤收口在一个谓词

`kb/query_scope.py`（新）：`visible_knowledge_filter()` 返回 `origin != 'material'` 谓词，五处消费端（列表默认视图、星图装配、选择器、写法块、书级副本）统一引用；列表「素材」行通过显式参数 `include_material=True` 单独取。

## Risks / Trade-offs

- **LLM 总结质量**：确认制兜底（候选不采纳不生效）；提示词模板随提示词包迭代
- **素材行被误删**：删除素材＝真删（无消费价值）；确认弹窗文案写明
- **候选与存量知识撞名**：首版不查重（存量豁免口径下，撞名由作家采纳时肉眼判）；合并建议链路后续可吃撞名对
- **拆书收录「即时可见」口径变化**：收录后立即可见的是素材行（列表带标）；v2 spec「收录后星图即时可见」场景随本 change MODIFIED（星图吃知识行，素材不进星图——总结采纳后进）

## Migration Plan

1. ensure DDL 建 `kb_summarize_runs`/`kb_summarize_candidates`（幂等）
2. 录入两链路切素材态（存量行不动）
3. 消费端过滤收口
4. 总结管线＋面板入口
5. 真机走查（手录→总结→采纳→星图出现 全链）
回滚：代码版本回退；素材行为新 origin 值，旧代码查询按 origin 精确匹配的路径不受影响（无 origin 过滤的老查询会带出素材行——回滚版本需接受此噪声或手删素材行）。
