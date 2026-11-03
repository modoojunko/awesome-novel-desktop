# c-kb-organize · Design

方法论来源（立项前公开实践研究）：Gruber 能力问题（CQ＝本体必须能回答什么，兼评估判据）；METHONTOLOGY/NeOn/SAMOD 的生命周期分层与「轻量优先」；Ontology Design Patterns（模式约束内建模）；LLM 知识图谱构建的多阶段管线（extraction→splitting→abstraction）与 HITL；OOPS! 坑目录＋OQuaRE；实体消解（ER）与增量维护实践。本文只记方法论落到本仓库的决策。

**评审状态**：架构师＋后端工程师双评审后修订（2026-11-01）。P0×3 已消化：D10 持久化三新表、D7 条目图视图（boss 拍板）、D5 别名物化；全部 P1 落进 D2/D3/D4/D6/D11 与 tasks。

## D1 能力问题（CQ）显式化＝整理的目标函数

整理做什么、做到什么程度，由这组 CQ 定义（验收与回归都对它们）：
1. 「写这场打斗，该用库里哪些手法？」（applies_to/depends_on 关系服务写法块上下文）
2. 「这两条是不是同一个写法？」（合并建议）
3. 「这条知识放对格子了吗？」（纠偏建议）
4. 「这类新写法该归进哪个子概念？」（子概念建议）
5. 「哪几条是垃圾/占位？」（质量标记）
6. 「跟这条相冲/相承的知识有哪些？」（contradicts/refines——条目图边）

组织原则（Gruber）：CQ 之外的一律不做——不发明第六类之外的关系、不为「可能有用」建推理。

## D2 置信分＝确定性特征合成；LLM 只产候选与理由，只见短名单

- **确定性预筛**（LLM 之前）：题材 ∩ 概念相容矩阵白名单对 ∪ 标签索引命中 → 候选短名单 **≤200 对**（照 kb/match.py 两段式先例）；条目投影只发 id＋title＋instruction[:120]；超短名单按 id 序截断并在 run 记 truncated 计数。**LLM 永远不见全库**——10 万条目题材的批预算问题在预筛层消解。
- LLM 调用（kb_organize 模板）只输出候选三元组＋自然语言说明＋证据引用；json_mode=True，meta finish_reason=length 判 JSON 截断不原样 parse，usage/operation 留痕，捕 PromptPackMissing 转 run error，max_retries=0 自管重试（对齐拆书链）。
- **置信分由 `kb/organize.py` 确定性特征合成（0–1）**，SHALL NOT 采信模型自报置信：
  - 证据章接近度：章号从 evidence/evidence_json.quotes[].loc 归一化抽取（正则「第?N章?/纯数字」，支持自由串）；任一端无章号取中性值 0.5（写死进公式保证可测）
  - 同题材命中：两端 genre 相等（含同为 ""）
  - 别名共现：走 `kb_entry_tags` **新增 dim="alias" 物化**（见 D5），SHALL NOT 读 payload_json
  - 概念相容矩阵：六类关系 × 概念对的显式决策表（见 D6），表外组合直接零分
  - 负反馈降权：特征签名命中反馈表即 ×0.5（见 D10）
- 特征权重常量入代码；同输入同分数可单测（特征清单不含墙钟项）。

## D3 触发、增量与并发

- 触发三通道：拆书入库钩子（collect-to-kb 与 to-library 两条 router 路径 commit 成功后调 `kb/organize.py` 唯一入口函数）；启动距上次 >7 天（main.lifespan，照 import backfill 先例）；手动立即（端点）。载体＝asyncio.create_task（进程死丢触发由 7 天启动钩兜底——写明语义）。
- **singleflight**：run 起步查该 user+genre 是否已有 status="running" 的 run，有即跳过（应用层互斥）；启动 sweep 僵尸 running（照 deconstruct startup_sweep 先例），备份恢复后的 running 行同 sweep 忽略。
- 增量对：run 记本轮新条目集（按 **rev/updated_at** 口径，非 created_at——revive 不改 created_at）；候选对＝新×全库 ∪ 新×新，且全部过 D2 预筛。全量深度整理仅手动，按 concept 分桶分批＋进度。
- **SQLite 写锁**：关系写入分小批 commit（≤50 行/批），避免大事务挤压生成链写锁（busy_timeout 5000 下防用户侧 503）。
- 一次一题材：按 kb_entries 分组取「有新条目」者；genre=""（跨题材通用）**参与整理**（并入触发题材的候选池，不单独立 run）。
- runs/outputs 保留策略：每 user+genre 留最近 50 条 run（outputs 随 run 级联清），清理在 run 收尾顺带执行——防无界增长。

## D4 合并语义（merge 不删行；独立合并表）

- `status` 三态：active / archived（既有）/ **merged（新）**——被并条目载荷原样保留。
- 指向：**独立表 `kb_entry_merges`（surviving_id, merged_id, run_id, created_at）**——不用 merged_into 塞进 kb_relations：六类白名单纯度保住、5× 上限计数免过滤、未来关系消费端零「记得排除」负担（评审 P1 收敛）。
- 排除口径：全部消费端 `status == "active"` 过滤天然排除 merged（现状核实为真），但**例外与补丁面见 D11**。
- 忽略记忆：候选对签名（两端 id 排序拼接 hash）落 `kb_organize_feedback`（kind=ignore）；任一端 rev 变化后可再提。
- 恢复（merged→active）＝P1。

## D5 别名物化（零迁移）

- `kb/service._tags_for` 新增 dim="alias"：条目 payload.aliases 逐条 ≤50 字物化进 kb_entry_tags（value 列 String(80) 容得下）；`rebuild_tag_index` 同步；merged/archived 条目的 tags 不清（消费端全带 status join，无害——口径写明）。
- 别名共现特征＝两短名单条目的 alias tag join，SHALL NOT 读 payload_json。

## D6 坑自检＋概念相容矩阵（显式决策表）

- 前置闸（每条产出过闸）：两端存在且 active、无自环、（from,to,rel_type）无既有 active 重复（**应用层闸——kb_relations 无 unique 索引且存量库加不了，更正「既有硬约束」的错误表述**）、类型在白名单、merged 条目不作端点。
- 概念相容矩阵（rel_type × 有向概念对；✓=允许入特征打分，空=零分）：

| | 文风→文风 | 文笔→文笔 | 世界→世界 | 角色→角色 | 手法→手法 | 手法→文风/文笔 | 文风/文笔→手法 | 跨大格（角色↔世界等） |
|---|---|---|---|---|---|---|---|---|
| applies_to | | | | | ✓ | ✓ | | |
| depends_on | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| refines | ✓ | ✓ | ✓ | ✓ | ✓ | | | |
| contradicts | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| derived_from | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| instance_of | —（条目→概念级，条目间禁用） | | | | | | |

（instance_of 由条目 concept 字段隐式承担——既有约定，整理不产。）

## D7 全局图：新增条目图视图（boss 拍板 2026-11-01）

- **新增「条目图」视图**：题材内 active 条目为节点、生效关系为边（六类分色，--chart-* token），边点击出说明＋证据浮层；**硬 cap ≤500 边**（按 confidence 降序取，超出具数入浮层提示），节点超限聚合提示不再下钻。
- 聚合视图（题材×概念格）与格子下钻**保持现状不动**；待确认关系不进任何图；merged 条目/merged 关系不进图。
- 数据：新增 `/graph/entries?genre=` 端点（条目节点＋边一次下发，cap 内）；聚合视图端点零改动。

## D8 与 write-block 的边界

- 本变更产出关系数据；写法块消费关系是 c-kb-write-block 的事——本变更不动 write/。
- **跨变更义务（知会 write-block 会话）**：其 `write/write_block.py:_load_run_items` 按 id 直取无 status 过滤——merged/archived 条目会经旧 run 复用继续进块；修法一行（补 `status=="active"`），归其批F。
- kb_organize 模板一枚进提示词仓；缺失 fail-soft 记 run error。

## D9 明确不做

不做自动合并/自动纠偏（作家确认制）；不做跨题材关系；不做本体结构演进（概念注册表封闭）；不做推理机/传递闭包；不做向量检索。

## D10 持久化模型（评审 P0 收敛：三新表，全部 create_all 零迁移）

| 表 | 列 | 装什么 |
|---|---|---|
| `kb_organize_outputs` | run_id, kind(trigger/suggestion_merge/suggestion_reclass/suggestion_subconcept/quality/pending_relations/…), count | run 明细计数（现 KbOrganizeRun 只有关系三计数且加列死路——spec 措辞「运行记录（含关联明细表）」） |
| `kb_organize_findings` | id, user_id, genre, kind(merge/reclass/subconcept/quality), subject_id, subject2_id, payload_json(建议快照), status(proposed/adopted/ignored), signature, run_id, created_at | 合并/纠偏/子概念/质量四类建议与待确认项（跨 run 持久；忽略记忆用 kind+signature） |
| `kb_organize_feedback` | id, user_id, kind(relation|merge), signature, entry_id, created_at | 「这条不对」负反馈的特征签名（降权查它；SHALL NOT 塞 kb_prefs——那是条目有用率语义） |

- 关系状态词表：kb_relations.status ∈ active（生效，图/计数只算它）/ pending（待确认，只进清单）/ archived（淘汰或否决）。淘汰＝status→archived（不删行）。
- 备份：三新表进 `_kb_account_section` 白名单＋importer kb_models＋roundtrip 断言；kb_organize_runs 的 running 行恢复后由启动 sweep 收拾（口径写明）。
- 5× 上限口径钉死：**per user+genre 的 active 关系数 > 同账号同题材 active 条目数 ×5 时，按 confidence 升序、created_at 升序淘汰（status→archived）至限额内**。

## D11 merged 三态跨端清单（评审实勘的补丁面，B 批回归即对这张表）

| 消费端 | 现状 | 动作 |
|---|---|---|
| 列表/计数/快照/全局图聚合/选择器/建卡预填 | active 过滤 | 零改动（天然排除）——B5 逐端断言 |
| write_block run 复用（write/write_block.py） | **无过滤**（第六端） | 知会 write-block 会话补一行；本变更 B5 加跨端断言钉住 |
| kb get_entry 详情 | active 过滤→merged 404 | 新增 merged 分支（`?include_merged=1` 返回载荷＋merges 指向）——C1 |
| 角色库 revive（library/service.py） | include_archived 会复活 merged | revive 分支显式跳过 merged（提示「已合并」）——B5 |
| collect-to-kb 幂等查 | 无过滤（merged 挡重收） | 统一「merged 不复活不重建＋跳过计数单列」——B5 |
| kb_entry_tags | merged 残留 | 无害（消费端全带 status join），口径写明 |
