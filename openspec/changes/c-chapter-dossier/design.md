# c-chapter-dossier 设计

设计依据：2026-09-28 grill 三轮 12 项拍板 ＋ 架构/前端/提示词/产品四路评审（P0 全部吸收）。行号基于 09-28 工作区。

## D1 归档流水线：受理制（评审三案取 c）

现状：`archive/router.py:59-64` 同步 await `archive_chapter()`（内含一次 AI 摘要，read 超时 90s）；前端乐观置位 `chapter:archived`（`useChapterData.ts:277-303`）被 5 处消费（e-meta 徽标 ChapterWorkspace.tsx:1021、ProsePane 只读 :151、StyleShadowPane 锁 :140、右栏解锁链 NovelWorkspace.tsx:293、树刷新 useWorkbench.ts:220-224）。

**取案**：a 同步阻塞否决（最坏 5×90s 超时、重试不幂等双倍烧 BYOK）；b 加 `archiving` 中间态否决（违反 frontier.py:9-10「状态枚举不扩展」纪律，frontier/书架阶段/total_archives/重写解锁全部误判）。**取 c：受理＋后台线程＋成功原子收口**：

- `POST /archive` 受理：校验 ≥100 字正文、记正文 sha256、起 job、立即返回 `{accepted, model_ready}`；模型未就绪（`get_ai_client_for_novel` 抛 ValueError）→ 不起提取 job，同步走收口（archived、无章档）。
- 后台 job：一次四域 AI 调用（D3）→ 成功 → `finalize_archive()` 单一收口函数在一个事务内完成：四域待确认行（子表 pending）＋ archives 行＋`mark_hooks_mentioned`＋`status="archived"`/`archived_at`＋`total_archives` 记账。同步放行路径与后台成功路径**共用 finalize_archive**（save_chapter 单写入口纪律）。
- 失败：章保持原状态，job 落失败态＋错误摘要；重试只跑 failed 域（kinds 机制沿用 reconcile.py:89）。
- **job 状态落库**（daemon 线程内存态在 Electron 重启后蒸发）：新表 `chapter_dossier_jobs`（章唯一、state: extracting/ok/failed/skipped、per_domain 四域二值、error、prose_hash），启动 sweep 把 extracting 且无线程的置 failed(interrupted)。
- 单飞改**每章键控**：现 `_job` 全局单 dict（reconcile.py:38-39, 97-99）必须换 per-chapter dict＋锁；跨章并发信号量 2-3（AI 客户端是瓶颈）。已在提取中的重复受理返回当前 job 状态（幂等 200）。
- ghost 支线章（`ghost_of` 非空）受理 409「旧稿支线只读」（现状 service.py:42-50 无检查，新语义下必须堵）。
- threads.yaml 写入保持「commit 后尽力而为」，从失败路径隔离（写失败不回滚 archived 置位）。

## D2 数据形状：四张章作用域子表 ＋ 一列

照 `_ChapterChildMixin`（models/chapter.py:137-149），全部注册进 `models/__init__.py`，启动 `create_all` 自动建；**不给 chapters 加 NOT NULL 无 server_default 列**（migration/engine.py:140-158 整表跳过坑）。

```
chapter_setting_changes   chapter_id / area(50) / set_name(50) / content(500) / evidence(300)
                          / status(pending|accepted|rejected) / decided_at / sort_order
chapter_relation_changes  chapter_id / owner_name(50)+owner_character_id(FK SET NULL 可空)
                          / other_name(50)+other_character_id / rel_type(50) / change_note(300)
                          / evidence(300) / status / decided_at / sort_order
chapter_item_changes      chapter_id / item_name(100) / change_type(50: obtain|lose|transfer|modify|destroy)
                          / holder_name(50) / detail(300) / evidence(300) / status / decided_at / sort_order
chapter_knowledge_changes chapter_id / character_name(50)+character_id(可空 FK) / fact(300)
                          / learned(Boolean：得知=true / 确认不知=false) / evidence(300)
                          / status / decided_at / sort_order
```

- 关系双方照 `ChapterCharacter`「名字快照＋可空 id」先例（models/chapter.py:169-175）。物品无实体、无 FK（拍板 8）。
- `chapters.dossier_stale` Boolean server_default "0"——完全照 `Chapter.stale` 先例（上游重写置位、单写入口清除）。
- Index：各表 `(chapter_id, status)`。
- **三条单源链必须接全**（漏一条＝静默丢数据）：
  1. `assemble_chapter`/拆装（chapters/store.py:81-168）加 `dossier` 键（照 outline.character_states 加键兼容先例 :123-130），子表替换走 `_CHILD_ATTRS`+`_child_replace_plan`（:222-245）并**必须 presence-gate（缺键保持现值）**；
  2. 备份往返：导出自动随 assemble（backup/export.py:140）；导入端 `_disassemble`/`_replace_children` 补 dossier 拆装（importer.py:691,739-744 对未知键静默丢弃，不接即丢）；roundtrip e2e 断言四域形状；
  3. `revert_to_chapter` 清理清单（chapters/frontier.py:173-231 手工枚举）扩四子表删除——章行转 ghost 不触发 CASCADE。

## D3 提取：一次调用、真分层模板、确定性宽松校验

**一次调用不拆四**（跨域一致性——同一情节事件四域各记一条不重复；输入省 3 倍；重试粒度在二值终态下是伪收益）。

- 新模板 `prompts/chapter_archive_extract.prompt`（**必须落文件**——现收尾五类是内联 f-string＋`system=""`（reconcile.py:165,195-224），整体逃逸 test_prompt_layering.py 闸门，不得照抄）：
  - `<<system>>`（恒定）：角色＝小说连续性管理员；约束＝只依据正文提取不脑补、名字只取【本书专名册】（name_canon 片段文本）、无变化输出空数组、每域最多 6 条、evidence 必须正文原句、不评论不重复「现有设定/既有章档」已有条目；输出契约＝单个 JSON 四键。
  - `<<user>>`（动态）：世界现状摘要（`world_summary_text`，≤1200 字，world_model.py:372）＋上章累计章档（accepted 全量，见 D5 查询单源）＋cast（outline.characters）＋专名名册（roster_text，name_registry.py:72-83）＋本章正文（≤6000 字）＋四键 schema 示例。
- 调用：`load_layers("chapter_archive_extract")`＋`json_mode=True`（ai_client.py:239-240 先例）＋`max_tokens=1600`（四域满负荷 ≈900-1100，留 50% 防截断；现 600 必截断→截断 JSON→解析失败风暴）。
- 输入 token 估算 ≈7-9k（正文 5-6k＋世界 1k＋累计章档 0.8k＋名册/schema 0.8k）；对比现收尾五调用 ≈25-30k，省 ~3 倍。
- 解析纪律（修 reconcile.py:169-171 静默 continue）：解析失败→四域 failed（`_mark_failed` 形态）可重试；某域缺键→该域空数组 extracted（parse_lore_suggestions 白名单归一先例 world_model.py:385-400）。
- 证据句：剥空白/引号/句读后 ≥12 字连续子串或 bigram 重叠 ≥80% 判匹配；不匹配**保留条目＋标 evidence_unverified**（UI 黄标「证据待核」），**永不驱动重试**（_reasons_verifiable 禁尸，test_chapter_plan_ai_t2.py:92-93）。
- 角色名三件套（规则＋名册＋集合差）：system 引用 name_canon＋user 带 roster＋后处理别名映射（chapter_writer.py:557-574 `_resolve_character_row` 反向）；名册外名字保留＋标 unregistered 交作者处置，不搬词尾扫描。
- 上限：每域 ≤6 条按输出序截断、content/evidence ≤60 字 clamp；超限不重试。
- 记账：`_record_ai_usage`，operation 区分四域＋`archive_extract_fail`。

## D4 采纳：子表行内状态翻转（不走 reconcile payload 二次搬运）

- 待确认清单直接读四子表 pending 行；采纳＝行内编辑校正（可选）后置 accepted；驳回＝rejected 留痕。**不进 chapter_reconcile 表**（payload→子表二次搬运会让两表各存状态、重提清两处、证据列无 schema）。
- `chapter_reconcile` 收缩为 hooks/lore 专用；`apply_accept` 两分支（create_hook/patch_hook、lore_apply_entries）；KINDS 收缩两键；char_states 半提案怪胎清理（reconcile.py:176-288 直写 state_change 不走确认）——kind 退役，`state_change` 列保留为章纲域，存量 pending 行置 rejected（数据已在 state_change）。
- 存量 set_changes/relations pending 行按 payload 物化成子表 pending 行（无证据句置空）；已决历史行原地留痕不搬。
- 已采纳行删除：DELETE 端点＋confirm；驳回行可恢复 pending。采纳 UPDATE 检查 rowcount，0→409「章档已重新提取，请重新确认」（重归档竞态；SQLite 单写者已串行化事务，rowcount 够用）。
- 端点族：`GET/POST /novels/{pid}/chapters/{ref}/dossier`（单章 rows+extraction+progress+stale 一次往返）、`PATCH /dossier/rows/{id}`（采纳/驳回/恢复）、`DELETE /dossier/rows/{id}`、`GET /novels/{pid}/dossier/preview?up_to_ref=`（累计预览=消费装配的只读版，前端不重算口径）、`POST /chapters/{ref}/dossier/extract`（补提取/重提）。

## D5 消费：故事状态块单源渲染

- 新查询单源 `build_story_state_upto(novel_id, ref)`（建议 write/ 或 prompt/ 下新模块）：每域一次 SELECT join chapters+volumes，`(volume_no, chapter_no)` 排序，过滤「主线 ∧ status=='archived' ∧ not dossier_stale」章的 accepted 行，Python 折叠：设定按 (area,set_name) last-wins、关系按 (owner,other) upsert、物品按名取最新持有者、认知按 (character,fact) 状态翻转覆盖。300 章 × 4 域 ≈1-3 万行，mixin FK 索引够用，fold <20ms。
- 渲染 `_story_state_block(rows)`：照 `_plot_block` 单源纪律（chapter_writer.py:117-128 注释明文「两路唯一渲染入口」）；在 material_markdown（剧情块后、角色块前）与 to_prompt 同位注入；无行返回空串（golden 回归逐字不变）。格式：定位句＋◆设定/◆关系/◆物品/◆角色认知 四小节＋防泄底规则行（「标『（乙不知）』的信息，乙不得表现出知情、不得提前摊牌」）。
- 预算：每域 ≤6 条、单条渲染 ≤40 字（对齐 WRITE_STATE_PER_CELL_MAX=40，chapter_writer.py:719-722）；认知域新事实线性增长，按「章近优先＋cast 相关优先」截断；整块 >1500 字硬闸截断＋logger.warning（不静默）。每章消费段 ≈900-1200 tok，50 章书总组装 2943→约 4000-4200。
- `validate_polished_prompt`（:141-158）加条件锚：有状态块时润色产物须保留段标题。
- prompt-sources 端点加第七来源（消费同源函数）＋缺口标注（缺 N 条未确认/上一章未归档）。

## D6 重写级联

- 下游定义复用 rewrite 既有判据（chapters/rewrite.py:83-94：跨卷（卷号,章号）有序、has_prose、ghost_of IS NULL）；级联进**同一重写事务**（:96 单次 commit）：源章四子表行删除＋下游 `dossier_stale=True`。
- 语义矩阵：重写源章＝行删＋重归档重建；下游＝stale 角标（章档页签横幅带「重新提取」动作＋树 tag-stale 样式角标，只提示不拦截）；unarchive＝行保留、消费按章现态过滤天然排除、页签置灰横幅「未归档态仅供参考」；重归档成功＝四域 pending 整体替换＋dossier_stale 清＋status=archived 一事务。
- 重归档受理前查已采纳行数，>0 时前端 ArchiveModal 警示「将清空并重提 N 条（含已采纳 M 条）」；覆盖事务对 accepted 行删除写 audit_log（先例在）。

## D7 前端

- 页签：ChapterWorkspace.tsx:172-174 chTab 联合类型＋:1050-1076 页签数组插「章档」（伏笔后、操作前）＋条件挂载 DossierPane（**不学 ProsePane 常驻**——轮询只在页签可见时跑）；徽标 cnt 模式放待确认数；头部「八页签」注释顺手改对；`.ch-tabs` 加 overflow-x:auto 兜底。
- 归档状态机：`useChapterData` 加 `archiveJob`（受理只置 job 不动 status；`chapter:archived` 只在真置位后派发；失败经 archiveJob 暴露）；进度 UI 两处——操作页签归档卡原位（「提取中…」分步进度：受理→AI 提取→写入章档→置归档）＋章档页签顶部进度条；轮询 hook 挂 ChapterWorkspace 级、终态即停；切章返回从章 GET/dossier 端点恢复。
- 软锁：archiveJob=提取中 → 编辑器禁用＋归档/取消归档禁用（全程锁到终态，用户拍板）。
- 失败态：错误摘要＋「重试提取」＋「跳过提取仍归档」（首败即出，confirm 写明代价）；模型未配置：ArchiveModal 文案三分叉（提取预告/未配置放行说明＋配置入口/免费档占位），以后端受理返回 `model_ready` 为准不用前端预判。
- DossierPane：抽 `ProposalRow` 共用行组件（status/kind/summary/evidence/actions 五槽，ReconcilePane 同骨架不同数据）；证据句点行展开；批量动作（按域全采纳/驳回＋全章一键采纳）；已采纳删除（confirm）；未提取/未归档态横幅。
- 双向指路：操作页签 lead 行「设定/关系/物品/认知已迁至章档页签（N）→」；章档页签尾「伏笔/世界要素提案在操作页签（M）→」。Rail.tsx:164-181 三入口收敛（伏笔保留改文案；设定/关系入口退役）。
- stale 呈现：树角标复用 tag-stale（OutlineTree.tsx:316-319、useWorkbench.ts:202 加字段）＋页签横幅带重提动作；树级只聚合数。
- 章档行**不进** useChapterData 本地 store（服务端权威＋轮询，照 StyleShadowPane 独立拉取先例）；只有 archiveJob 进 store。

## D8 门控与成本

- 新提取不挂 `require_ai_access`（摘 archive/router.py:57 会员判断）；只看模型就绪；免费档配 key 引导＝设定页 AI 配置入口对免费档可达可保存（现免费档无任何 AI 场景），叙事「生成新内容是 PRO，整理你已写的内容全档」进付费墙文案。
- `ai_client.py:504-508` 门禁 grep 纪律：新调用文件所在路由模块须出现 `require_novel_model`，豁免名单同步。
- 去抖：同章刚归档成功短窗（如 60s）内重受理需前端 confirm；跨章信号量 2-3。
- 指标基线（token_log 可用，audit_log 不可用）：提取成功率（`archive_extract` vs `archive_extract_fail`）≥90%；分域采纳率 ≥70%（子表 status/decided_at 聚合）；静默缺失率 ≤30%（prompt_sources 缺口标注埋点）；归档动作量降幅 ≤10%。

## D9 迁移与兼容

- 新表全量 create_all 自动建；release 换库时源库无新表→列交集自然跳过，存量归档章空章档（「未提取」态＋补提取入口承接）。
- 存量 `chapter_reconcile` pending 的 set_changes/relations 行一次性物化进子表 pending；char_states pending 置 rejected；已决行留痕。
- 旧三 kind API 兼容：run 端点对退役 kind 返回 400＋提示语。

## 非目标（本期不做）

主线体检对章档对勘、物品实体化、行内编辑（进阶，删除先行）、拆书/导出侧透出、认知识别外的「误解」细分结构（fact+learned 布尔已够 v1）、e2e 之外的自动化质量评测流水线。
