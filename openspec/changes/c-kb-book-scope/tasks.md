# c-kb-book-scope · Tasks（四角色评审决议已吸收——批0 上游事实源先行，D1-D7 条款以 design.md D8 修订为准）

## 批0 上游事实源（先于一切——题材词汇不干净，复制范围查询是空中楼阁）

- [ ] 0.1 共享归一器：拆书三侧（collect_to_kb/import_book/导入查询）genre 统一经 THEMES 归一，miss 落 ""（降级通用）；修 collect_to_kb `task.genre` 存量 500（DeconstructJob 无 genre 列——读产物 genre 维度）
- [ ] 0.2 parity 钉：kb.concepts.THEMES == genres.theme_catalog.THEME_NAMES（21 类逐字对拍，现无守卫）
- [ ] 0.3 单测：拆书产物 genre 非目录词 → 条目降级通用、开书仍可命中

## 批A 数据模型＋开书导入链（后端；design D8 修订条款全部吸收）

- [ ] A1 `kb_book_entries`＋`kb_book_entry_tags` 建模＋**部分唯一索引 uq(novel_id, src_key) WHERE src_ref<>''**（并发双击防重）＋副本 stamp＝每书一行状态（非行级列；pref 标记不刷新）
- [ ] A2 `import_genre_knowledge`：**批量克隆**（预查已有 src_key → 批量 add 单 flush 单 commit，禁逐条 create_entry）；范围＝题材命中＋跨题材通用（通用照复制——书自包含口径，量级记账 M6 治理）；**world 白名单只落 stage/power/cost**（factions/history/extra/constraints 不落 KV）；style_samples 落 KV 带 source="kb-genre"；量化合成保守基线（confidence=40/source=kb-synthesized/剥限定词/下限跳过）；导入时播种源 pref 摘要为副本初始权重（经验继承）
- [ ] A3 挂点：手动入口＝PUT /settings/genre **首次定题材**分支（改题材＝补新题材副本不叠加、导入失败不阻塞）；拆书入口＝书自有设定写入**之后**（锁序单测）；「同一事务」改可实现口径（先 DB commit 再落 KV，失败标记差异行可重试）
- [ ] A4 书级标签物化＋重建；删书＝软删保留副本（按 novel_id 天然隔离）；书内删副本＝软删 archived（补平 diff 排除）
- [ ] A5 单测：复制范围/幂等/空库/基线落 KV **读 yaml 实文对账**/隔离（源删不影响副本）/题材降级/**锁序**（拆书建书后 role=拆书值、genre 基线不丢、列表无重复）/**量级**（1000 条复制单事务）/并发双 import（索引守卫）/复制×首章生成竞态（不提交不半块）

## 批B 选择器切源（后端，依赖批A）

- [ ] B1 切表面清单：digest_candidates/select_block/**_load_run_items 双域（副本优先 miss 回退账号标 legacy）**/影子转写读副本/is_quantitative 消费
- [ ] B2 域指纹＝每书 stamp；**增量导入 SHALL NOT 改写既有章 run**（只影响未来选择——F3 覆盖分支仅限显式启停触发）；refill 补指纹校验
- [ ] B3 **pref/prototype_use 端点双域**（副本 id＋novel_id 归属校验防跨书打标；现打副本 id 必 404）
- [ ] B4 闸门书域化：块使能＝书副本非空（自动导入即开）；bindings 收窄快照面＋中途加库＋差异行；书级停用开关（停用后影子清零——批F F4 语义迁移）
- [ ] B5 块首 v3 补句（参考书专名不进正文）＋短名单截断 title 序＋基线列表导入上限（rules≤12/banned≤20）
- [ ] B6 单测：账号库新增不混入/源删不影响/增量导入不改写既有 run/停用影子清零/pref 双域 404 面/消毒照旧

## 批C 存量书补平＋备份（后端＋前端）

- [ ] C1 设定面板「导入题材知识」入口（差异计数 N＝未复制 active 题材命中；一键导入幂等；确认文案「从下一章生成开始生效，已写章节不变」——补平静默改 system 恒定层的缓存/漂移代价显式化）
- [ ] C2 单书备份 kb-book.yaml 扩 book_entries 段＋恢复照 characters 先例**重生成 id＋重映射 match_items**（src_key 不重映射）；export 空段条件加 book_entries；prefs 书级投影进单书包
- [ ] C3 单测：备份往返（选择行为字节一致）/旧包无段跳过/补平幂等

## 批D e2e＋真机走查

- [ ] D1 e2e：新人漏斗全链（注册→拆书入库（喂固定产物投影跳过 LLM）→开书选题材→首章生成带块（**entry_id 全为副本 id**——enabled=False 类假绿的唯一真防线）→标记 pref 200）——隔离栈口径
- [ ] D2 真机走查：脚本跑绿后人工只验 UI 层（开书 toast「已导入 N 条」/空库 CTA/来源行出现消失时机/备份恢复后只读条还在）；数据断言归脚本，分工写进 checklist 头部
