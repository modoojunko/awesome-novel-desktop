# c-chapter-plan-ai —— 卷下拆章（逐章拆分链路）

决策依据：`docs/design-c/drafts/卷下拆章-决策记录.md`（D1–D19，2026-09-22 与用户逐条对齐）；原型：`docs/design-c/drafts/ai-novel-c端-卷下拆章.html`。

## Why

卷纲规划（`volume-plan-ai`）定了"这一卷讲什么、坎是什么、收在哪里"，写章纲（`chapter-data`）填单章细节，但**中间缺一环**：作者建好卷之后，"这一卷的剧情怎么一章一章拆出来"没有任何入口。五岗位评审确认这个方向成立，但同时认定原设计里"章必吃剧情节点"的机制不成立（节点无稳定身份、新卷无节点、节点数与章数对不上）。用户裁定（D5/D6）：**卷只定起止边界，剧情由章定义；`volume_plot_nodes` 表退役**。本 change 产品化逐章拆分链路，并清掉这张表。

## What Changes

- **逐章拆分链路（新）**：一次只拆下一章。三个入口按档位分家——左树卷行「＋添加章节」（手写，现有行为不动）、中栏卷纲顶部「拆下一章」（手写五段，全档）、右栏「拆下一章（AI）」（3 个剧情方向抽卡，PRO）。
- **卡面**：进场（只读，自动接上一章结尾）＋ 五段（本章剧情／碰到的挑战／本章结尾／本章行动）＋ 阶段（六档，章自己的属性）。手写与 AI 共用同一张卡面、同一个弹窗。
- **AI 抽卡四态**（D12）：正在想／出卡失败（三出口：重试、自己写这一章、先不拆回卷页）／只出两套（降级 note）／换 3 个方向。免费档右栏入口为锁定态，中栏手写不调 AI。
- **剧情吸引力评分**（D13）：标准名"剧情吸引力"，四维（反转／冲突层层递增／剧情推进／结尾拉力）各绑定唯一判据字段；**模型只给四维相对名次，S/A/B 由服务端计算**（鸽笼保证三张不可能全 S）；评分与理由不落库。
- **两步模型**（D9/D11）：第一步＝关键剧情字段（拆章时定），第二步＝其他重要字段（写章纲六项必填时补）；落点卡显示"已带入 N 项（AI 全填时 5 项）、还差 6 项才能开写"。
- **进场派生真值**（D15）：上一章有正文取正文实际收尾，没正文取章纲落点，卡上标来源小字；进场不落库。
- **拆后能改**（D14）：拟定章可回改（三处入口同一张卡）；撤销排上（仅本卷最后一章且无正文）；重拆整卷（盘点确认）。单章删除守卫统一为「本卷最后一章＋拟定＋无正文」（防中间删章留永久章号空洞）。
- **BREAKING（数据）**：`volume_plot_nodes` 表退役，卷纲字段集撤出「关键剧情节点」段；无用户，不写迁移。
- **章新增三列**（D10）：`challenge`(150)／`chapter_acts`（一行一条 ≤4×60）／`plot_stage`(20，六档闭集)；`summary`/`ladder_exit` 复用现有列。
- **排上原子化**：建章＋写五段同一事务；建章改幂等（重复点击不撞 UNIQUE 500，#457 同类事故的服务端根治）；删章加守卫（仅"拟定且无正文"可删）。
- **免费档**（D16）：章级 AI 自检（只读检查）免费可用——`volume-plan-ai` 免费例外条款扩展。

## Capabilities

### New Capabilities

- `chapter-plan-ai`：卷下拆章——入口归属（三入口两手写一 AI）、拆章弹窗（手写/AI 共用卡面、AI 四态）、剧情吸引力评分（四维名次→服务端算字母，不落库）、进场派生真值（按 `has_prose` 分流并标来源）、排上/撤销/回改生命周期、拆后派生视图（卷页阶段序列）。

### Modified Capabilities

- `volume-outline`：卷纲字段集换代（BREAKING）——撤出「关键剧情节点」段（编辑态行增删、查看态节点块退役），查看态改为"已拆章阶段序列"派生视图；`PLOT_STAGES` 六档迁为章属性。
- `chapter-data`：章档案新增 `challenge`/`chapter_acts`/`plot_stage` 三列的持久化与导出（加键兼容）；has-outline 判定纳入新列；章纲表单整表回传约束。
- `volume-chapter-service`：`create_chapter` 支持随建章写五段（同一事务、find-or-insert 幂等）；`delete_chapter` 加"拟定且无正文"守卫。
- `volume-plan-ai`：免费例外条款扩展——章级只读检查（AI 自检）纳入免费，与卷级"体检免费"同口径。
- `outline-ai-draft`：「有现有章纲」判定覆盖拆章三格；拆章五段作为改写基底进入素材包，起草只补缺不推翻。

## Impact

- **后端**：`volumes/`（节点退役：`models/volume.py`、`models/__init__.py`、`service.py`、`render.py`、`schemas.py`、`volume_repo.py`、`backup/importer.py`）；`chapters/`（三列＋`create_chapter` 扩展＋`delete_chapter` 守卫）；`chapters/ai_draft.py`（has-outline 判定纳入三格）；`write/chapter_writer.py`（素材包三行：挑战/行动/阶段）；`models/chapter.py`（三列随版本换代自动建出，无 DDL 路径）；测试 5 文件 22 处断言随节点退役调整。
- **前端**：`workbench/VolumeWorkspace.tsx`（节点块→派生视图、ol-top 按钮改手写）、新 `ChapterPlanModal.tsx`（复用 `Modal`＋既有 `.pick-*`＋`.rp-*`＋`.cfg`）、`Rail.tsx`（AI 入口＋免费锁定态）、`volume/types.ts` 与 `volume/form.ts`（节点退役）、`chapterForm.ts`（三格＋整表回传）、`design/book.css` 末尾追加 9 个新类（`.pk-corner/.pk-read/.pk-grade/.split-row/.s-*/.node-tx/.pick-card.top`）。
- **规格**：1 ADDED ＋ 5 MODIFIED。
- **e2e**：新增拆章用例（手写路径、AI 四态、评分呈现、撤章守卫、回改 stale）；`volume-plan.spec` 的 `landing-card` 断言不受影响（拆章落点卡不叫 `landing-card`）。
- **不做埋点**（D18 用户拍板）：不新增拆章相关事件，不动前端事件白名单——留此护栏防 scope creep。
- **越纲对拍的已知集合扩到地点**（角色/势力之外）——AI 素材构造的实体集合随批扩展。
- **评分卡面为有意精简**：D13 原设的「自查条」并入卡尾「剧情吸引力/差在哪」两块（四维依据已在卡尾逐条可查）；`.rp-*` 体检行样式的消费者＝章级 AI 自检（D16）。
- **不触碰两端共享段**：`base.css` 零改动；新类仅追加 `book.css` 末尾（业务层），不新增胶囊/提示形态。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：书工作台（卷页、左树、右栏、中栏卷纲）＋ 拆章弹窗（新，`Modal width={940} wbStyle` 同卷纲抽卡）。
- **对象状态**：章沿用既有派生态（拟定/草稿/已归档，枚举不扩展）；提示语气仅 info/ok/warn/err——降级 note＝info、超配额提示＝warn、出卡失败＝err；无新增胶囊形态、无第四种语气。
- **共享段**：不触碰（见上）。
- **原型先行**：设计原型已完成并经用户逐轮评审（drafts，5 态＋AI 四态）；按硬性流程，**实施第一项任务**是把原型收编进 `docs/design-c/prototypes/`（拆章弹层并入 book.html 屏）并在 `ADJUSTMENTS.md` 登记偏差，`design:check` 全绿后才动实现。收编时执行决策记录 H1–H3（删常驻 DOM 补丁、940 用 `Modal width`、卡面行序对齐 `pk-in` 打头、`--faint` 弹窗失效与产品同批修、角标占位、820px 断点、testid 清单且落点卡避开 `landing-card`）。
- **文案**：按钮全动词（拆下一章／排上这一章／换 3 个方向／重试／自己写这一章／先不拆／撤销排上／重拆本卷）；称呼「你」；无内部术语（"剧情吸引力"是作者语言；"四维名次/ranks"不出现在界面）。
- **复用硬约束（D19，检视必查）**：前端全部复用既有组件与词表（仅追加 9 个业务类到 `book.css` 末尾）；后端复用既有分层与机制（加法列、标量装配、AI 调用链骨架、`resolve_prev_ending` 函数族、frontier 口径、stale 标记、盘点确认），**不得为拆章另起平行栈**。
