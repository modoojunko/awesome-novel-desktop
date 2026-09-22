# c-chapter-plan-ai · tasks

> 决策依据 D1–D19（`docs/design-c/drafts/卷下拆章-决策记录.md`）；复用硬约束 D19 是每个阶段完成后的核对项。

## 1. 原型收编（C端硬性流程第一项，先于实现）

- [x] 1.1 原型从 `drafts/ai-novel-c端-卷下拆章.html` 收编进 `prototypes/book.html`（拆章弹层＋右栏 AI 入口＋卷页派生视图），`ADJUSTMENTS.md` 逐处登记偏差；按 H1 删常驻 DOM 补丁（`.modal:not(.show)`/`.plan-modal.wide`）、按 H3 对齐卡面行序（进场行 `pk-in` 打头）、补 820px 断点、补 testid；验证：`design:lint` 通过 ✓；**基线自证**＝独立浏览器上下文渲染 HEAD 与收编后截图**字节级相同**（169765B，比 <0.2% 阈值更严）✓；`design:check` 全量（原型 vs 应用）待应用栈就绪后随 7.6 跑（此刻拆章段未实现，全量比对无对象）
- [ ] 1.2 `design/book.css` 末尾追加 9 个新类（`.pk-corner`＋`i`/`g-S|g-A|g-B`、`.pk-read`、`.pk-grade`、`.split-row`＋`.s-no/.s-main/.s-lab/.s-entry`、`.node-tx`、`.pick-card.top`）；同批修 `--faint` 弹窗失效（与产品卷纲抽卡弹窗同病，H2）；**给 `.pick-card` 补定位锚**（产品 CSS 无 `position:relative`，原型那条是专属补丁——角标 `absolute` 不补锚会逃到弹窗层）＋右上占位防首行压字；验证：design:lint 通过、grep 断言 `base.css` 零 diff、弹窗内小灰字计算色为 `--faint`、design:check 截图核对角标不与首行重叠

## 2. 数据契约与节点退役（后端）

- [ ] 2.1 三列落模型（`models/chapter.py`：`challenge VARCHAR(150)`／`chapter_acts TEXT`／`plot_stage VARCHAR(20)`）——随版本换代自动建出（新版本库 `create_all` 全量建出；旧库按 db-generation 指纹/版本分流留档只读；无显式版本常量或 DDL 步骤，`SCHEMA_VERSION`/`ADDITIVE_COLUMNS` 均已退役不得复活）；验证三条：**(a)** 新库 `PRAGMA table_info(chapters)` 三列可见；**(b)** ORM 写入回读；**(c)** `git grep ADDITIVE_COLUMNS` 仅命中「已退役」注释与测试
- [ ] 2.2 标量清单登记（`store.py`：`challenge`/`plot_stage` 入 (json_key, col, width) 三组；`chapter_acts` 照 `ladder_exit` 先例**清单外定制**——`_fit` 会把列表 str 化，join/拆行走同一归一函数）＋ `plot_stage` 六档闭集校验（越界 422）＋ `chapter_acts` 归一化（换行归一、去空白、丢空行、逐行 ≤60、上限 4 行，装配端复用同一归一）；验证：`assemble_chapter` 含三键、越界/超行 422、归一化单测
- [ ] 2.3 has-outline 判定补三格（`chapters/ai_draft.py`）：五段齐而六项必填未填的章判为「有现有章纲」，五段作为改写基底进素材包，起草只补缺不推翻；验证：单测「仅拆章的章被判有纲」「起草采纳后五段保留」
- [ ] 2.4 写正文素材三块（`write/chapter_writer.py`）：挑战＝【本章要撞的墙】、行动＝【本章必须发生的动作】、阶段＝【本章在卷剧情里的位置】；验证：单测断言已填章素材含三块、未填章不含、空段不出现占位符
- [ ] 2.5 备份往返：`test_backup_roundtrip` 扩展——排上章（五段齐）导出→导入后 summary/challenge/chapter_acts（列表同形）/plot_stage/ladder_exit 原样；验证：往返测试绿
- [ ] 2.6 节点表退役（D6）：删 `models/volume.py::VolumePlotNode`、`models/__init__.py` 导入、`volumes/service.py`（`_replace_children` 节点分支与装配 9 处）、`volumes/render.py` 节点行、`volumes/schemas.py` 节点 schema、`repositories/volume_repo.py` selectinload、`backup/importer.py` 节点还原；前端 `volume/types.ts`/`volume/form.ts`/`VolumeWorkspace.tsx` 节点段；测试清理（后端 3 文件＋前端 2 文件共 22 处断言）；验证：`git grep -n "plot_nodes\|VolumePlotNode"` 全仓零命中（决策记录与本文除外）、`create_all` 后 `PRAGMA` 无 `volume_plot_nodes`、pytest/vitest 全绿

## 3. AI 端点与评分

- [ ] 3.1 `POST /api/novels/{id}/volumes/{ref}/chapters/ai-directions`（PRO）：出参 `{entry:{text,source}, diff:{axes,one_liner}, directions[2..3], grades[卡数]（服务端算出的 S/A/B，与 directions 序号对齐、不落库）, ranks, reasons, checks, warnings, note}`；路由持显式 `APIRouter` 并在 main include；验证：契约测试断言出参形状与 `entry` 必含、路由可达（防 #255 404 先例）、调用前后不落库
- [ ] 3.2 素材包（D17）：进场→卷纲四问（取 `volumes/render` 装配单源）→已拆章节列表→配额/末章标记→题材与节奏→人物≤6×80→铁律全量→上一章一行；**不含**主线全景/结局三问（末章除外）/伏笔台账；验证：假客户端断言块顺序 index 递增、预算上限、grep 断言伏笔台账零出现
- [ ] 3.3 校验阶梯（**含末章固定样本单测**：素材④含末章标记与结局三问、三方向结尾收卷命中/越界各一）：差异轴闭集（加速/关系/线索/代价/危机/收束）互异，未知轴**丢卡不改写**；依据 ≤20 字且逐字可寻；`(plot,ending)` difflib>0.6 同质复核一次（原因喂回＋降温 0.7→0.3）；单卡不合格丢弃、剩 ≥2 照常、<2 重试、**最多 3 次尝试**后 degraded；验证：固定坏样本单测（三张同轴／依据寻不到／两次后剩 1 张）
- [ ] 3.4 评分服务端算字母（D13）：`ranks` 四维每维**至多一个第一名（唯一时才计入；并列第一不计）**→ ≥3 第一名＝S／1–2＝A／0＝B；验证：鸽笼性质测试（随机合法名次组合至多一张 S，**含 1/1/2 并列样本**）、`why/gap` 非空校验、DB 零评分写入断言
- [ ] 3.5 越纲对拍：模型申报 `cast/factions/places` 与已知集合（角色 name+aliases／势力名／**地点**）做差→`warnings` 不拦；验证：喂含新地点样本断言 warnings
- [ ] 3.6 章级自检端点 `POST /api/novels/{id}/chapters/{ref}/ai-selfcheck`（只读、免费例外通道，照卷级体检）：出参三组（衔接/配额/剧情吸引力），状态 ok/warn；验证：免费档 200、生成类仍 PRO、不落库、未配模型给引导不 500
- [ ] 3.7 门禁与计量：生成挂 `require_ai_access`（PRO）＋模型门；自检走只读例外；每次尝试（含失败）`record_usage`，operation 名 `chapter_directions`/`_fail`/`chapter_selfcheck`；验证：单测断言计量与失败路径

## 4. 排上与撤章（后端）

- [ ] 4.1 `create_chapter` 扩展：请求体 `{title, plot?, challenge?, ending?, acts?, stage?}`，同 session/commit 内建章＋经 `store.apply_chapter_data` 写五段（不新写标量路径）；验证：排上后五段齐、注入失败不留半章（事务回滚断言）、`plot_stage` 越界 422 且未建章、**PUT /chapters 同值同 422**（防「排上是 422、章纲保存是截断落库」的双语义）
- [ ] 4.2 幂等：唯一约束冲突捕获→重读返回既有章；验证：并发双发单测两次响应同章、库中一行、无 500
- [ ] 4.3 `delete_chapter` 守卫：仅**本卷最后一章＋拟定＋无正文**可删，否则 409（非尾章→「先删其后的章节，或走重拆整卷」；有正文/已归档→重写或归档）；验证：非尾章拟定章 409、有正文 409 且正文/归档/版本保留、删尾章后再建复用同章号（无跳号）
- [ ] 4.4 `resolve_prev_chapter_ending(db, project, vol, ch_no)`（与 `resolve_prev_ending` 同族；正文末段优先的同构先例＝`write/plot_sim.py` 的上一章结尾口径）：上一章 `has_prose`→正文末段（来源「取自正文结尾」）；无正文→`ladder_exit`（来源「拟定，取自章纲落点」）；卷首章→复用既有卷级取法。**并暴露为只读端点**（`GET /volumes/{ref}/next-chapter-anchor`，全档可用——手写路径不发 AI 请求也要进场，前端 5.1 依赖本端点）；**同时给 `GET /volumes` 树的 chapters 行集补 `plot_stage`**（派生视图数据，`VolumeChapterMeta` 同步）。验证：三分支单测＋来源文案断言＋端点契约测试
- [ ] 4.4b （并入 4.4，占位保序）
- [ ] 4.5 `stale` 置位：保存事务内若本章 `ladder_exit` **trim 后实质变更**且下一章（主线序）`has_prose` → 置位（清除沿用既有「本章保存/归档即清」——已知自动保存会清标记，故界面警告以一次性提示为主、标记为辅）；验证：单测「实质改结尾→下一章 stale」「仅微调措辞→不置位」「下一章保存→清除」

## 5. 前端 · 弹窗与入口

- [ ] 5.1 `ChapterPlanModal`（`<Modal width={940} wbStyle>`）：手写/AI 共用卡面——进场只读行＋来源小字、五段（`.field`+`.input/.textarea`，`chapter_acts` 一行一条）、阶段六档 select；AI 态渲染三方向卡（`.pick-*`，进场行 `pk-in` 打头对齐产品行序）＋角标＋「剧情吸引力/差在哪」两块＋**checks（0–3 条「拿不准」，呈现在「差在哪」之后）**；**手写卡的进场/配额判定消费 `next-chapter-anchor` 端点**；**主线末端门禁与卷纲空门槛的置灰/拦截判定落在两入口组件（5.3），组件测试各一条**；验证：组件测试覆盖两路同卡面、进场来源小字两种、手写最小可排（仅剧情）、checks 渲染
- [ ] 5.2 `useChapterPlan`（挂 NovelWorkspace）：`entrySource: manual|ai`、`phase: idle|busy|error`、**`submitting`（排上请求在途，Modal locked＝Esc/遮罩全失效——服务端幂等不能替代 UI 锁）**、**`landed`（落点卡数据，宿主＝关弹窗后由中栏渲染，对齐卷级 confirmResult 先例）**、`directions/note/pick/draft/scIgnored`、token 守卫取消；manual 不发请求直接空白卡；验证：组件测试「busy 中关窗→请求弃」「排上中 Esc 不可关」「落点卡两出口」「换 3 个方向→重置」
- [ ] 5.3 三入口落位（D8）：中栏 ol-top「拆下一章」→手写表单；右栏新增「拆下一章（AI）」——**挂 `VolumeAssistPanel` 的卷纲页签（`volume-replan` 同级 ai-tool 块），`isPro/onUpgrade` 经 Rail 注入（该面板现无此 plumbing）**；免费档置灰＋「AI 三方向需 PRO」＋升级出口；左树卷行右侧「＋添加章节」沿用；树底「拆下一章」删除；验证：断言中栏无 AI 卡与三方向、免费锁定态、树底按钮缺席
- [ ] 5.4 AI 四态渲染（D12）：busy（转圈＋播报＋副行）、error（两种文案＋三出口）、只出两套（note＋2 卡）、换方向；验证：组件测试 route 打桩逐态断言、失败三出口齐全
- [ ] 5.5 排上与落点卡：调扩展后的建章接口；落点卡＝「已排上（拟定）＋已带入 N 项（逐项实列，空项不冒充）＋还差 6 项必填＋**三出口**（补这 6 项，开始写／继续拆下一章／撤销排上）」，**不叫 `landing-card`**；验证：组件测试落点卡文案与三出口、双击只建一章、撤销后树回退
- [ ] 5.6 回改与撤销：左树章行/派生视图行（**hover 回改动作项，不改变点击＝选中语义**）/落点卡三处通同卡，**打开时 GET 章档案载入既有五段，保存走既有 `saveChapter` 合并链并同步章选择态（防章纲 3s 自动保存用旧快照互抹）**；改「本章结尾」时下一章已排→一次性提示、下一章有正文→警告＋stale 标记显示（沿用树行既有口径）；撤销入口仅本卷最后一章且无正文；验证：组件测试三入口同卡、「回改保存后紧接章纲自动保存，五段与六项均原样」、警告与标记、撤销边界
- [ ] 5.7 重拆整卷：卷页「重拆本卷」入口＋既有盘点确认交互（列出将被移除的拟定章）＋按章号**降序**逐章走删章守卫；验证：组件测试盘点清单不含正文/归档章、确认后树回退且章号无跳号

## 6. 前端 · 章纲表单与卷页派生

- [ ] 6.1 `chapterForm.ts` 加三格（challenge/chapter_acts 行编辑/plot_stage 下拉）——**不进必填六项**，整表回传；验证：回归测试「保存章纲后三格原样」（防 `_disassemble_scalars` 抹除）
- [ ] 6.2 章纲页呈现三格（「来自拆章」组，可改）；验证：组件测试拆章值回显、可修改保存
- [ ] 6.3 卷页派生视图：节点块替换为「剧情推进（派生）」——已排章阶段序列＋零章空态文案（数据：`GET /volumes` 树的 chapters 行集补 `plot_stage`，`VolumeChapterMeta` 同步——**后端配套见 4.4b**）；验证：组件测试排章后即时反映、回改阶段同步、零章空态
- [ ] 6.4 章级 AI 自检（D16）：入口＝**拆章手写卡底条「AI 看一眼这一章」**（手动触发、全档免费、不进 workbench 六类检查口径）；三组结果（衔接/配额本地判＋剧情吸引力 AI 四维短评、**不给字母**）用 `.rp-*` 渲染；验证：组件测试免费可触发、未配模型给引导、结果无 S/A/B 字母

## 7. e2e、口径与收尾

- [ ] 7.1 e2e 新增：免费手写排上全链（最小填写→落点卡→补章纲入口）；AI 四态（route 打桩：busy→出卡→选 S 卡→排上；失败三出口；只出两套；换方向）；双击幂等；删章守卫 409（**含非尾章 409 引导重拆**）；回改结尾→下一章 stale；派生视图反映；**重拆整卷（盘点→确认→树回退）**；**非末端卷入口置灰**；**卷纲空门槛拦截**；验证：本地隔离栈全量 e2e 绿
- [ ] 7.2 存量断言清算：`volume-plan.spec`（`landing-card` 不受影响）、`workbench-features.spec`、`volumeWorkspace.test.tsx`（节点块退役）、`volumePlan.test.tsx`、**`modals-pr5.spec.ts`（写正文后删章的用例在守卫下必红——改走 409 断言或先清正文；前端删除入口补 409 toast 断言）**、`design-parity-book.spec.ts`（confirmed 章只开弹窗不删除，暂安全但登记脆性）；验证：三条命令（pytest/vitest/tsc）全绿
- [ ] 7.3 口径：新文案作家语言（grep 断言不含「名次/落库/闭集/降级/素材包/四维」）；`data-od-id`/`data-testid` 按决策记录 H3 清单冻结；语气词仅 info/ok/warn/err；验证：grep 断言脚本
- [ ] 7.4 复用核对（D19，检视必查）：前端 grep 断言未新建第二套卡面/表单/弹窗类（新增仅 book.css 9 类）；后端 grep 断言无平行建章/取数/校验路径（排上走 `create_chapter`+`apply_chapter_data`、进场走同族函数、校验走既有 sanitize 模式）；验证：核对清单逐条打勾并附 grep 输出
- [ ] 7.5 `src/coverage-contract.ts` 登记新文件（`ChapterPlanModal`/`useChapterPlan`/新端点模块）；验证：`vitest run --coverage` 不因未登记变红
- [ ] 7.6 收尾门禁：pytest 全量＋vitest 全量＋tsc＋design:lint＋design:check＋全量 e2e；验证：六项全绿后申请检视
