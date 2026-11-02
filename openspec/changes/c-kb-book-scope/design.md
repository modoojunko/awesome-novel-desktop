# c-kb-book-scope · Design

设计权威＝整体方案 §8（四来源/书内三表）＋c-kb-write-block 批F 已固化的选择器语义。本文件记实现决策。

## D1 数据模型

- 新表 `kb_book_entries`（novel_id 域，照书内 3 表惯例注册 models/kb.py）：列＝账号级条目同构镜像（信封＋payload_json＋payload_version＋instruction/example/negative_example＋when_json＋evidence/evidence_json＋concept/concept_id/title/genre＋src_kind/src_ref/src_key（复制来源：src_kind="book_copy"、src_ref=novel_id、src_key=源条目 id——增量导入幂等键）＋status/rev/created_at/updated_at）。标签物化照 kb_entry_tags 同构一张 `kb_book_entry_tags`（entry_id/novel_id/user_id/dim/value）。
- 无 FK（kb 家族松约束惯例）；novel 删除级联在应用层（删书清副本）。
- 反馈权重：沿用 kb_prefs（user_id, entry_id）——副本 id 独立 ⇒ 标记天然书级，零表改动。

## D2 开书导入链

- 挂点＝开书/建书选题材确认事务（两处入口：手动建书向导确认步＋拆书产物建书确认）。`import_genre_knowledge(db, novel_id, genre)`：
  1. 查账号级条目（genre==选定题材 OR genre==""，status=active，全概念）
  2. 逐条复制进 kb_book_entries（新 id；src_kind="book_copy"/src_ref=novel_id/src_key=源 id；payload/标签原样克隆）
  3. 基线面：题材默认库（rule_kind=auto，genre 命中）的文风/文笔/世界基线条目 → apply_members 落本书 style/world KV（复用 kb/snapshot.apply_members，来源「知识库·题材」）
  4. 幂等：src_key 已存在跳过（增量导入同函数复用）
  5. 呈现「已从知识库导入 N 条」toast
- 空库：第 1 步零行 → 直接跳过，无 toast。
- 原型条目（角色设定）照复制（建卡挑原型改读书范围——一致化）。

## D3 选择器切源

- `digest_candidates`/`select_block` 加 `book_scope` 入参（novel_id）：候选查询从 kb_entry_tags（账号）切 kb_book_entry_tags（书级）；条目行读 kb_book_entries。
- 批F 语义全保持：text_snapshot/竞态复用/回声闸/结构消毒/量化影子转写（影子 dim 映射读副本条目同函数）。
- 库域指纹简化：副本表 `updated_stamp` 列（每次增量导入/书内变化刷新）——复用守卫比账号期更简单。
- kbPrefs 读取不变（user_id+副本 entry_id）。

## D4 双向隔离与同步出口

- 书内副本删除/标记 → 零回写（无回写代码路径即天然隔离）。
- 作家库新增 → 老书不自动进：设定面板来源行扩「知识库有 N 条新增（题材命中未导入）」＋按钮「导入」→ 调 import_genre_knowledge（幂等，只补新条）。
- P1 LLM 选择器候选域自动跟随书范围（digest_candidates 已公开化，切源后 P1 零适配）。

## D5 备份

- 单书备份 kb-book.yaml 扩 `book_entries` 段（行序列化同账号段口径，含 tags 投影）；恢复重建行＋rebuild 标签。兼容键不升 format_version。
- 账号配置包（config.yaml）knowledge_base 段不动（作家库照旧）。

## D6 存量书补平

- 设定面板来源行区新增「导入题材知识」按钮（仅未导入过/有新增时显示）→ import_genre_knowledge → toast。
- 不做自动后台迁移（避免静默改存量书——作家显式点击）。

## D7 明确不做

- 不做书内 AI 整理（⑦ 的书级演化另立变更）；不做书间知识搬运；不做部分概念选择性导入（首版全概念一把梭，后续按反馈收）。

## D8 四角色评审决议（2026-11-02 后端/架构/测试/提示词 40+ 发现合并）

### 挂点修正（P0）
- 手动建书弹窗只问书名（2026-09-10 裁定），题材确认实际在书内设定 PUT /settings/genre（可重复/可改题材）→ **2026-11-02 改口径**：保存成功后前端弹「从知识库导入 / 我自己设定」二选一（不静默导入）；选导入走 SSE 进度（`/book-scope/import/stream`），选自己设定落 `kb-import.declined` 不再自动弹。**改题材**＝清 declined 重新征询＋补新题材副本（旧副本保留＋来源行提示可清理），不叠加同题材；导入失败不阻塞题材保存。拆书建书入口挂**书自有设定写入之后**（put_style 整替会清 genre 基线——次序钉死＋A5 锁序单测）。

### 反馈/原型端点双域（P0）
- set_pref_api/prototype_use 现校验账号表 → 副本 id 打点必 404。改按 book_scope 切校验表（KbBookEntry＋novel_id 归属校验防跨书打标）；tasks B3 展开。

### 启用闸门书域方案（P0）
- `_binding_domain` 要求 enabled bindings——导入不落 bindings → 副本满仓但块永不出（批3 enabled=False 假绿同型）。裁决：**导入即开**（块使能＝书副本非空）；bindings 收窄为快照面（style/world KV）＋中途加库＋「库有 N 条新增」差异行；书级停用开关＝设定面板清空副本或显式开关（批F「停用无块」语义迁移到此）。

### 部分唯一索引（P1）
- `uq_kb_book_entries_src(novel_id, src_key) WHERE src_ref<>''`（照账号表先例）——并发双击防重；导入 catch IntegrityError 计 skipped；补平端点幂等靠它。

### 拆书次序（P1）
- 拆书建书入口 import 固定放**书自有设定写入之后**（put_style 对 rules/craft 整替会静默清 genre 基线——锁序单测钉「role=拆书值、genre 基线不丢、列表无重复」）。

### 题材词汇归一（P1，含存量 bug）
- 共享归一器（→THEMES，miss 落 ""降级通用）用于 collect_to_kb/import_book/导入查询三侧；**修 task.genre 存量 bug**（DeconstructJob 无 genre 列，现网 500 潜伏）——此修复挂账项就地解决。

### 世界白名单（P0，提示词 F-2）
- 基线自动落 KV 只收 **stage/power/cost** 三题材语法面；factions/history/extra/constraints（源书事实＋铁律位）SHALL NOT 自动落 KV（副本保留供写法块/整理消费）。spec 增句照提示词稿。

### style_samples 标签（P0，提示词 F-1）
- style KV 加 source="kb-genre"；system 渲染分支：「文风示范段（题材文风示例，提炼自参考作品——只学句式、节奏、对话密度与段落质感；示例中的专有人名、地名、组织、功法名一律不得出现在正文）」＋「模仿以上示范的笔法写本书的故事」。作者手填（manual/空）沿用旧文案。

### 量化合成基线（P0，提示词 F-3）
- 导入时书级量化未蒸馏（confidence=0）→ 以副本量化条目按维度归类合成保守基线：confidence=40（±30% 最保守档）、剥掉「不超过」类限定词、「不少于」类下限跳过、source="kb-synthesized"（style_quant_model 白名单扩）；作者后续蒸馏覆盖合成值。兜底：块尾【数值弹性】常量行（若未走合成路径）。

### run 重建双域＋refill 指纹（P0）
- `_load_run_items` 双域：副本 id 优先查 kb_book_entries，miss 回退账号表（legacy run）；refill 补域指纹校验（切源/导入后旧 run 不静默空块）。

### prefs 经验继承（P1）
- 导入时把源条目 pref 摘要（有用率）播种为副本初始权重（母本经验继承——「开书立刻高质量」的唯一已积累质量信号）；书内标记只累积本书副本。原型 adopt 计数语义变化记账。账号/书双 id 域混居 kb_prefs 的结构性问题→M6 晋升通道变更重构（书级 kb_book_prefs），本变更不表。

### 通用条目常驻＋复制并集（P1 裁决）
- 题材命中条目复制进书；**跨题材通用（genre=""）也复制**（boss 口径「书的范围自包含＋单独推演」——书内通用标记独立积累正是「书的知识」字面含义；量级记账：通用几十条×书数线性，SQLite 无压力；M6 治理膨胀）。

### 其余采纳
- 「同一事务」改可实现口径：先 DB 复制 commit → 再落 KV → 失败标记「基线未落」进差异行可重试（KV 文件写不在 DB 事务）
- 批量克隆约束：预查已有 src_key → 批量 add 单 flush 单 commit（**禁逐条 create_entry**——千次 commit 拖死确认路径）；失败整体回滚
- 删书＝软删保留副本（方案 a：按 novel_id 天然隔离零泄漏；prefs 孤儿行注明不清理）
- run 覆盖分支仅限显式启停/导入触发；**增量导入 SHALL NOT 改写既有章 run**（只影响未来选择）；书内删副本＝软删（status=archived，幂等键保留，补平 diff 排除 archived）
- stamp＝每书一行状态（非行级列——行级写放大＋破坏 freshness 半衰）；刷新白名单：书内条目增/删/改；**pref 标记不刷新**（保重试字节一致）
- 表数 SHALL 枚举化（账号域/书级域列表，替代计数——计数必然腐坏）＋本 delta 补 MODIFIED 三条（数据模型/选择留痕反馈/写法块选择器——与 write-block spec 的「停用/账号级全局」对撞句一并对齐）＋models/kb.py 头注释 stale 修
- 块首补句：「以下条目提炼自参考作品，只取其写法；条目中出现的专有人名、地名、组织与术语属于原参考书，不得出现在本书正文。」
- 短名单截断 sorted(id) 随机刀 → title 序（与批E tiebreaker 同源）
- 增量导入基线列表单次上限（rules≤12/banned≤20）
- P1 摘要模板带「本书题材＋候选提炼自参考作品」语境（登记 D4）
- 存量书补平确认文案显式生效点：「导入后从下一章生成开始生效，已写章节不变」
- design 权威引用漂移修正（§8→§5/§9）

### golden 重构（测试方案采纳）
- 母本 seed 不变＋插复制步（import_genre_knowledge）＋选择域换书副本；REGEN 两段式（先 diff 落 last_mismatch 再覆盖）；确定性三锁迁移（副本表冻结/now 注入/prefs 不 seed）；四不变式保留＋影子泄漏换副本 id

### M 路线修订（架构师版采纳）
M0 批F（已落）→ **M1′ book-scope 批A+B（必须先于/同批批D 前端定型——entry_id 域只有一次机会定对）** → M2 批E 书域口径 → M3 双变更对齐归档（write-block 先归档，book-scope 出 MODIFIED）→ M4 P1（零适配）→ M5 ⑦（范围收紧：关系/整理全账号域永不进书，书 diff 加「源已合并」类目）→ M6 书域演化（新增：副本管理面＋晋升通道＋prefs 双层重构）
