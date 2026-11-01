# c-kb-organize · Tasks

## 批A 关系整理核心（后端，可独立合入；等 write-block 批F 合入后再开工——共同编辑面 models/kb.py＋kb/router.py）

- [x] A1 三新表 models/kb.py：kb_organize_outputs（run_id,kind,count）/ kb_organize_findings（kind,subject,subject2,payload_json,status,signature,run_id）/ kb_organize_feedback（kind,signature,entry_id）；kb_entry_merges（surviving_id,merged_id,run_id）；backup `_kb_account_section`＋importer 白名单同步扩＋roundtrip 断言（running 行 sweep 口径写明）
- [x] A2 `kb/organize.py`：触发三通道（collect-to-kb 与 to-library 两 router 路径 commit 后唯一入口函数／lifespan 7 天／手动端点）；asyncio.create_task 载体＋进程死语义写明；singleflight（user+genre running 即跳过）＋启动僵尸 running sweep（含恢复包）；一次一题材＋零条目跳过＋genre="" 并入候选池；runs 落库（error fail-soft）＋runs/outputs 保留策略（每 user+genre 最近 50 条，收尾顺带清）
- [x] A3 增量范围：新条目集按 rev/updated_at 口径；候选对（新×全库∪新×新）→确定性预筛（相容矩阵∪标签命中）→短名单 ≤200 对（条目投影 id+title+instruction[:120]，截断计数入 run）；手动全量按 concept 分桶分批＋进度
- [x] A4 LLM 候选生成：kb_organize 模板对接（json_mode=True／finish_reason=length 判截断／usage・operation 留痕／PromptPackMissing→run error／max_retries=0）；产物校验（白名单/两端存在且 active/自环/重复应用层查重/merged 不作端点）
- [x] A5 确定性特征打分：章号归一正则（缺章中性值 0.5 写死）/同题材/别名共现（走 alias tag）/相容矩阵决策表（D6）/负反馈签名降权 ×0.5；三级落位（active/pending/archived）＋5× 上限淘汰（口径＝spec 钉死版）
- [x] A6 别名物化：`_tags_for` 增 dim="alias"＋rebuild_tag_index 同步（零迁移）
- [x] A7 写入分批 commit（≤50 行/批）；关系状态词表落位（active/pending/archived）
- [x] A8 单测：触发矩阵与 singleflight／增量对边界／特征分确定性（同输入同分，含无章中性值）／三级落位／上限淘汰双排序／坑闸逐条／模板缺失 fail-soft／预筛短名单 ≤200 与截断计数／runs 保留清理
- [x] A9 性能预算钉（test_kb_perf 口径）：10 万条目下 organize 预筛＋打分耗时过闸（增量对 + 短名单路径，SHALL NOT 因全量对退化）

## 批B 合并·纠偏·标注＋merged 跨端（后端，依赖批A）

- [x] B1 合并建议：相似判据（名/别名 tag/槽位重合）＋provenance 线索（双出口平行条目）；findings 落库＋候选对签名忽略记忆（rev 变可再提）
- [x] B2 合并确认：kb_entry_merges 落行＋status=merged；**排除回归断言**（列表/计数/快照/图聚合/建卡预填已钉；选择器与 write_block 两端在 c-kb-write-block 分支——合入后由其批F 补钉，本批已留跨端清单 design D11）＋角色库 revive 跳过 merged＋collect-to-kb 幂等「merged 不复活不重建、跳过计数单列」＋merged 不再入 candidates
- [x] B3 merged 追溯：get_entry include_merged 分支（原载荷＋merges 指向）；恢复（merged→active）留 P1 只留数据路径
- [x] B4 纠偏建议：错位判据（payload 键 × 注册表＋infer 词叶分差阈值）＋采纳删建（溯源键防撞后缀）＋单测
- [x] B5 子概念建议（提案制）＋质量标记（指令 <20 字/无证据/标题与已归档重复——阈值常量入码）——仅展示层；标记不进选择器断言
- [x] B6 负反馈端点语义：「这条不对」落 kb_organize_feedback 签名；采纳/忽略即落 findings.status
- [x] B7 单测：平行条目合并全链/合并不删数据/B2 七端逐一/纠偏删建防撞/质量标记不影响打分/忽略签名不再提出（rev 变再提）

## 批C 端点与条目图（后端，依赖批A/B）

- [x] C1 端点：手动整理触发（幂等）/运行状态/待确认清单（pending 关系＋findings 汇聚）/建议采纳与忽略/关系反馈——全部信封风格＋权限
- [x] C2 条目图端点 `/graph/entries?genre=`：active 条目节点＋active 关系边（≤500 按 confidence 降序 cap，截断计数返回）；聚合视图端点零改动
- [x] C3 单测：端点权限幂等/边 cap 与截断/pending·merged·merged_into 三不入图/genre="" 候选池归属

## 批D 前端（依赖批C）

- [x] D1 知识库页「整理」入口＋运行状态行（info/ok/warn/err；触发中禁重复点击；待确认清单计数徽标）
- [x] D2 条目图视图：节点边渲染（六类 --chart-* 分色）＋边点击浮层（类型/说明/证据）＋cap 提示；聚合/下钻视图不动
- [x] D3 待确认清单：pending 关系＋四类 findings 逐条「采纳/忽略」；条目详情关系列表＋「这条不对」钮＋merged 追溯入口
- [ ] D4 入约（coverage-contract）＋组件测试＋design-language §13 自查；e2e：整理触发→清单采纳→条目图见边→反馈降权全链

## 批E 提示词与验收（依赖批A；随批B/C 并行）

- [ ] E1 prompts 仓 kb_organize 模板（短名单批产候选；输出契约 JSON；占位符/配额按 prompt-pack 惯例）＋冒烟
- [ ] E2 CQ 六问回归落 tests（D1 各一断言）＋真机走查单（拆书入库→自动整理→条目图见边→反馈降权→平行条目合并建议全链）
