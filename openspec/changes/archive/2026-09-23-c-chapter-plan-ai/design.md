# c-chapter-plan-ai · design

决策事实源：`docs/design-c/drafts/卷下拆章-决策记录.md`（D1–D19）。本文只写"怎么实现"，不复述动机。

## Context

- 卷纲（`volume-outline`）已定起止边界（进场/卷末/坎/章数目标）；写章纲（`chapter-data`，六项必填）填单章细节；两者之间无逐章拆分入口。
- 既有可复用件：卷纲抽卡全套（`PickCardsModal`＋`.pick-*`＋`useVolumePlan` 的 idle/busy/error/degraded/redraw 状态机）、`Modal`（`width`/`wbStyle`）、`FormField`（`.field`+`.input/.textarea`）、体检行（`.rp-list/.rp-row`）、卷页组件（`.fro/.rowx/.cols.cn/.cfg`）、右栏（`.ai-*`）、AI 调用链骨架（`require_ai_access`→`require_novel_model`→素材包→模型→sanitize→degraded）、进场取数（`volumes/service.resolve_prev_ending`，返回 `{text, source}` 事实优先）、schema 换代口径（`SCHEMA_VERSION`；`ADDITIVE_COLUMNS` 代内补列已随 #464 版本化命名退役——全仓无对既有库执行 DDL 的路径）、章纲标量装配（`store.assemble_chapter`/`_disassemble_scalars`——备份导出/导入直接复用这对函数）、frontier 排队门禁、`Chapter.stale` 失效标记。
- 无真实用户（零基线）：破坏性清理选干净方案，不写迁移、不做双轨。

## Goals / Non-Goals

**Goals**
- 逐章拆分三入口（两手写一 AI）与共用卡面；AI 四态；剧情吸引力评分（名次→服务端算字母）。
- 五段落库（两现成列＋三新列）并接进 has-outline 判定与写正文素材——拆章内容可被后续链路消费。
- 排上原子化＋幂等；拆后生命周期（回改/撤销/重拆）与删章守卫。
- `volume_plot_nodes` 表干净退役。

**Non-Goals**
- 不做批量拆章、不做"一次生成多章"（用户明确否掉，且会破坏相对评分与逐章语义）。
- 不做评分落库、跨章统计、按 S/A/B 排序筛选。
- 不做"半成品预填手写表单"（失败即失败，三出口）。
- 不改章状态枚举（拟定/草稿为派生态，`frontier.py` 头注释为契约）。
- 不动 S 端、不动 base.css 共享段。
- 不做事件埋点（D18）。

## Decisions

### 1. 节点退役而非修复（D6/D7）
`volume_plot_nodes` 从模型/契约/装配/导入导出全部移除，表从建表定义删除（无用户→不写迁移）。`PLOT_STAGES` 六档**保留并迁为章属性**（`chapters.plot_stage`），卷页节点块改为从章派生的阶段序列视图。
*取舍：曾考虑"节点加稳定 id＋外键＋快照"（照 hook 台账先例）——被用户裁定否掉：卷只定边界、剧情归章后，"章引用节点"这个方向不存在，整套身份机制是多余的。*

### 2. 复用卷纲抽卡的组件与状态机（D8/D12）
`ChapterPlanModal` 用 `<Modal width={940} wbStyle>`；卡面复用 `.pick-card/.pk-axis/.pk-title/.pk-row/.pk-picked/.pick-grid/.pick-foot/.pick-busy/.pick-error`；四态对齐 `useVolumePlan` 的 `idle/busy/error`＋degraded＋redraw 模式。手写与 AI 共用卡面：状态机加一个入口来源位（manual/ai），manual 时不发起请求直接渲染空白五段。
*取舍：曾考虑手写就地展开在中栏（不弹窗）——放弃：两路同卡面才能保证"升档不改心智"，且卷页不被长表单撑变形。*

### 3. 评分＝名次在模型侧、字母在服务侧（D13）
输出 schema：`diff{axes[], one_liner[]}` → `directions[{axis,title,plot,obstacle,ending,acts[],stage,cast[],factions[],why,gap}]` → `ranks{四维:[名次]}` → `reasons{}` → `checks[]`。服务端：断言 axes 逐字一致且互不相同 → 按 ranks 算 S/A/B（≥3 第一名→S）→ 校验依据逐字可寻。
*取舍：曾考虑模型直接给字母＋校验理由——否：无法检测"全给 S/按长度打分"，且四维每维恰一第一名使"三张全 S"在数学上不可能。轴闭集另立章级集合（反转/递增/推进/拉力是判据维度，不是卡面差异轴；卡面差异轴闭集＝加速/关系/线索/代价/危机/收束，未知轴丢卡不改写——卷级"静默改写"的教训）。*

### 4. 五段落库：一处登记管四条路（D10）
新列登记进 `store.py` 标量清单（`challenge`/`chapter_acts`/`plot_stage`）→ 章纲读/写、备份导出/导入自动覆盖；`SCHEMA_VERSION` 推进（新库 `create_all` 全量建出三列；旧库留档只读，无用户不迁移）；`ai_draft.py` has-outline 判定补三格；`chapter_writer.py` 素材包补三块。**前端章纲表单整表回传**（`_disassemble_scalars` 对缺键无条件写空——不同时改表单，保存一次章纲就抹掉拆章内容）。
*取舍：`chapter_acts` 用 TEXT 一行一条（≤4×60）而非子表——它是章纲素材，无需单独查询；将来要做角色出场聚合再升级。`plot_stage` 六档闭集服务端校验（422）。*

### 5. 排上＝create_chapter 扩展＋同事务（D9）
`POST /volumes/{ref}/chapters` 请求体扩展为 `{title, plot?, challenge?, ending?, acts?, stage?}`；实现走既有 `create_chapter` ＋ `store.apply_chapter_data`（**同一 session/commit**，不新写建章路径）；唯一约束冲突捕获→重读返回既有章（幂等，#457 卷上只修了前端的服务端补课）。落点卡＝"已带入 5 项＋还差 6 项必填"。

### 6. 进场派生：按 `has_prose` 分流（D15）
新函数与 `resolve_prev_ending` 同族：章级 `resolve_prev_chapter_ending(db, project, vol, ch_no)`——上一章 `has_prose=True` → 正文实际收尾（正文末段优先——同构先例 `write/plot_sim.py` 的「上一章结尾：正文末段优先，无正文回退章纲」；回退字段有意选 `ladder_exit` 而非 summary）；无正文 → 上一章 `ladder_exit`；卷首章 → 复用既有卷级函数。返回 `{text, source}`，界面小字沿用既有文案口径。进场**永不落库**。上游改落点 → 下一章复用 `Chapter.stale` 置位（改结尾的保存事务内判断下一章 has_prose）。

### 7. 撤销/重拆走既有删章＋守卫（D14）
`delete_chapter` 加守卫：仅 `status=='outline' and not has_prose` 可删，否则 409 引导重写/归档。删章守卫含**尾章限定**（服务端：`chapter_no`＝当前最大才可删——堵「删中间拟定章留永久空洞」；重拆整卷按章号降序逐章删，每步满足守卫；卷级删除沿用既有级联不受单章守卫约束）——`MAX+1` 自然复用章号，不引入重排（`ref` 被 `ghost_of` 按字符串引用）。重拆整卷＝既有盘点确认交互＋逐章走同一守卫删章。

### 8. 免费例外扩一条（D16）
`volume-plan-ai` 门禁 Requirement 已 MODIFIED：章级**只读检查**并入免费例外通道（与卷级体检同一条 `require_ai_access` 例外），生成类（3 方向）仍 PRO。自检手动触发（照卷的验证）。

## Risks / Trade-offs

- **[新列被章纲表单抹掉]** → `chapterForm.ts` 同批加三格并整表回传；加回归测试（保存章纲后三格原样）。
- **[schema 换代机制]** → `SCHEMA_VERSION` 与 `ADDITIVE_COLUMNS` 均已退役（db-generation：版本号即库文件身份）；三列直接进 `models/chapter.py`，新版本库 `create_all` 全量建出、旧库留档只读，无 DDL 步骤，验收＝新库 `PRAGMA` 可见＋ORM 回读。
- **[模型名次不可靠]** → 依据逐字可寻校验＋difflib 同质复核（沿用卷级 0.6 阈值）＋单卡丢弃/3 次重试阶梯；T2 车道加"同输入 3 次，S 归属 ≥2/3 一致"稳定性样本。
- **[删章守卫破坏既有用例]** → 既有"删除有正文章"的 e2e/单测改为走 409 断言或先清正文；守卫文案给出口（重写/归档）。
- **[卷级闭集静默改写的旧病传染]** → 章级 sanitize 未知轴**丢卡不改写**；卷级那条不改（超出本 change 范围），但已知集合扩到地点供章级对拍。
- **[弹窗常驻补丁误入产品]** → H1 两条仅在 drafts 原型；收编任务显式列"删除"清单。
- **[stale 被自动保存消解]** → 保留"本章保存即清"既有语义，警告以一次性提示为主、标记为辅；置位加 trim 后实质变化判定（微调措辞不触发）。
- **[右栏排他条款]** → `volume-plan-ai` 卷级验证 Requirement 已同步白名单（规划＋拆章两入口），否则两条规格互斥。
- **[互斥验收的"互换读不通"无法机器判定]** → 机器只校验可判部分（axes 闭集/互异/依据可寻/difflib 同质），语义互斥交给 diff 声明＋同质重试兜底。

## Migration Plan

1. 后端先落数据契约（三列＋登记＋退役表删除）→ 启动期自检零告警；`volume_plot_nodes` 直接从 `create_all` 消失，旧库残留表无害（无引用）。
2. AI 端点与守卫随后（新端点独立，可灰）。
3. 前端原型收编（`prototypes/` ＋ ADJUSTMENTS 登记，`design:check` 全绿）→ 实现切换（新弹窗/入口/派生视图）→ e2e。
4. 回滚：功能未合前各 PR 独立可回滚；合入后节点表已退役，回滚需带回三个 revert（数据契约不可逆——无用户，可接受）。

## Open Questions

无——D1–D19 已全部对齐。提示词模板全文与逐字段 schema 见 `prompt-draft.md`（附录），其自评的三处实现期校准点中，**并列名次已按稠密读法定入规格**（合法 1/1/2、非法 1/1/3——spec 示例已改）；其余两处（末章结尾 difflib 阈值 0.4–0.6、超长丢卡松紧）实现期用真实样本校准，实现期用真实样本校准；响应包络新增 `grades[]`（服务端算出的字母，与 directions 序号对齐，不落库）。
