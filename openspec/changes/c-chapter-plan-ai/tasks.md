# c-chapter-plan-ai · tasks

> 决策依据 D1–D19（`docs/design-c/drafts/卷下拆章-决策记录.md`）；复用硬约束 D19 是每个阶段完成后的核对项。

## 1. 原型收编（C端硬性流程第一项，先于实现）

- [x] 1.1 原型从 `drafts/ai-novel-c端-卷下拆章.html` 收编进 `prototypes/book.html`——**实况＝Part C 样式（含 9 个新类）＋隐藏空壳容器**（`#split-scrim/#split-body/#split-foot` 为空、无 JS 填充；拆章内容不住在原型里，见 §8 说明），`ADJUSTMENTS.md` 逐处登记偏差；按 H1 删常驻 DOM 补丁（`.modal:not(.show)`/`.plan-modal.wide`）、按 H3 对齐卡面行序（进场行 `pk-in` 打头）、补 820px 断点、补 testid；验证：`design:lint` 通过 ✓；**基线自证**＝独立浏览器上下文渲染 HEAD 与收编后截图**字节级相同**（169765B）——因新增 DOM 是 `hidden` 空壳，该自证只证明「原有屏未被改坏」，**不构成收编内容已就位的证据**；`design:check` 全量（原型 vs 应用）待应用栈就绪后随 7.6 跑（此刻拆章段未实现，全量比对无对象）
- [x] 1.2 `design/book.css` 末尾追加 9 个新类（**首轮漏做**：83c6f289 只搬了 `--faint`，9 类从未进应用样式表——检视发现后已补，含 `.pick-card` 定位锚与 `.pick-card .pk-axis` 让位；证据＝`grep -c pk-corner book.css` 5 处）（`.pk-corner`＋`i`/`g-S|g-A|g-B`、`.pk-read`、`.pk-grade`、`.split-row`＋`.s-no/.s-main/.s-lab/.s-entry`、`.node-tx`、`.pick-card.top`）；同批修 `--faint` 弹窗失效——**实际修法**：`--faint` 上移 `base.css :root`（book.css 无 :root，令牌单源在 base.css），book.css 作用域内定义删除；与产品卷纲抽卡弹窗同病一并治好（H2）；**给 `.pick-card` 补定位锚**（产品 CSS 无 `position:relative`，原型那条是专属补丁——角标 `absolute` 不补锚会逃到弹窗层）＋右上占位防首行压字；验证：design:lint 通过、grep 断言 `base.css` 零 diff、弹窗内小灰字计算色为 `--faint`、design:check 截图核对角标不与首行重叠

## 2. 数据契约与节点退役（后端）

- [x] 2.1 三列落模型（`models/chapter.py`：`challenge VARCHAR(150)`／`chapter_acts TEXT`／`plot_stage VARCHAR(20)`）——随版本换代自动建出（新版本库 `create_all` 全量建出；旧库按 db-generation 指纹/版本分流留档只读；无显式版本常量或 DDL 步骤，`SCHEMA_VERSION`/`ADDITIVE_COLUMNS` 均已退役不得复活）；验证：`tests/test_chapter_plan_ai_t1.py` 4 项（归一化/闭集 422/装配写回往返/缺键即清空的整表回传契约）＋全量 pytest **1318 通过** ✓
- [x] 2.2 标量清单登记（`store.py`：`challenge`/`plot_stage` 入 (json_key, col, width) 三组；`chapter_acts` 照 `ladder_exit` 先例**清单外定制**——`_fit` 会把列表 str 化，join/拆行走同一归一函数）＋ `plot_stage` 六档闭集校验（越界 422）＋ `chapter_acts` 归一化（换行归一、去空白、丢空行、逐行 ≤60、上限 4 行，装配端复用同一归一）；验证：`assemble_chapter` 含三键、越界/超行 422、归一化单测
- [x] 2.3 has-outline 判定补三格（`chapters/ai_draft.py`）：五段齐而六项必填未填的章判为「有现有章纲」，五段作为改写基底进素材包，起草只补缺不推翻；验证：单测「仅拆章的章被判有纲」「起草采纳后五段保留」
- [x] 2.4 写正文素材三块（`write/chapter_writer.py`）：挑战＝【本章要撞的墙】、行动＝【本章必须发生的动作】、阶段＝【本章在卷剧情里的位置】；验证：单测断言已填章素材含三块、未填章不含、空段不出现占位符
- [x] 2.5 备份往返：`test_backup_roundtrip` 扩展——排上章（五段齐）导出→导入后 summary/challenge/chapter_acts（列表同形）/plot_stage/ladder_exit 原样；验证：往返测试绿
- [x] 2.6 节点表退役（D6）：删 `models/volume.py::VolumePlotNode`、`models/__init__.py` 导入、`volumes/service.py`（`_replace_children` 节点分支与装配 9 处）、`volumes/render.py` 节点行、`volumes/schemas.py` 节点 schema、`repositories/volume_repo.py` selectinload、`backup/importer.py` 节点还原；前端 `volume/types.ts`/`volume/form.ts`/`VolumeWorkspace.tsx` 节点段；测试清理（后端 3 文件＋前端 2 文件共 22 处断言）；验证：`git grep` 全仓零命中（仅历史归档 openspec/changes/archive 命中，历史不可改）✓；pytest **1318 通过**、vitest **761 通过**、tsc 干净 ✓

## 3. AI 端点与评分

- [x] 3.1 `POST /api/novels/{id}/volumes/{ref}/chapters/ai-directions`（PRO）：出参 `{entry:{text,source}, diff:{axes,one_liner}, directions[2..3], grades[卡数]（服务端算出的 S/A/B，与 directions 序号对齐、不落库）, ranks, reasons, checks, warnings, note}`；路由持显式 `APIRouter` 并在 main include；验证：`TestDirectionsValidation::test_happy_path_material_and_grades`（出参形状/entry/grades 鸽笼/不落库）＋路由可达（防 #255 404 先例）；t2 契约测试只做路由注册断言
- [x] 3.2 素材包（D17）：进场→卷纲四问（取 `volumes/render` 装配单源）→已拆章节列表→配额/末章标记→题材与节奏→人物≤6×80→铁律全量→上一章一行；**不含**主线全景/结局三问（末章除外）/伏笔台账；验证：`test_happy_path_material_and_grades` 断言必在块（进场/卷纲四问/章数配额）＋空数据块不出现占位符＋**伏笔台账零出现**；`test_quota_four_states` 断言配额四态文案
- [x] 3.3 校验阶梯（**含末章固定样本单测**：素材④含末章标记与结局三问、三方向结尾收卷命中/越界各一）：差异轴闭集（加速/关系/线索/代价/危机/收束）互异，未知轴**丢卡不改写**；依据 ≤20 字且逐字可寻；`(plot,ending)` difflib>0.6 同质复核一次（原因喂回＋降温 0.7→0.3）；单卡不合格丢弃、剩 ≥2 照常、<2 重试、**最多 3 次尝试**后 degraded；验证：`tests/test_chapter_plan_ai_t2.py` 6 项（未知轴丢卡不改写／阶段越界丢卡／同质去重／鸽笼含并列样本／依据逐字可寻／三端点契约可达）＋t3 `test_same_axis_dropped`／`test_all_same_axis_degrades`／`test_non_dict_shapes_degrade_not_500`／`test_unverifiable_reasons_go_through_ladder`（**名次依据不可寻 → 进重试阶梯，三次后不出字母**）；末章固定样本并入 `test_quota_four_states`（末章标记＋【结局（作者写的）】块）＋全量 pytest **1324 通过** ✓
- [x] 3.4 评分服务端算字母（D13）：`ranks` 四维每维**至多一个第一名（唯一时才计入；并列第一不计）**→ ≥3 第一名＝S／1–2＝A／0＝B；验证：鸽笼性质测试（随机合法名次组合至多一张 S，**含 1/1/2 并列样本**）、`why/gap` 非空校验、DB 零评分写入断言
- [x] 3.5 越纲对拍：模型申报 `cast/factions/places` 与已知集合（角色 name+aliases／势力名／**地点**）做差→`warnings` 不拦；验证：`test_new_place_warns`（含地点样本 → warnings 且卡仍可用）；已知地点侧＝章纲「地点」字段 ∪ 世界舞台文本圈出的地名（`_known_places`）
- [x] 3.6 章级自检端点 `POST /api/novels/{id}/chapters/ai-selfcheck`（卡面草稿随请求体携带——排上之前章未落库）（只读、免费例外通道，照卷级体检）：出参三组（衔接/配额/剧情吸引力），状态 ok/warn；验证：免费档 200、生成类仍 PRO、不落库、未配模型给引导不 500
- [x] 3.7 门禁与计量：生成挂 `require_ai_access`（PRO）＋模型门；自检走只读例外；每次尝试（含失败）`record_usage`，operation 名 `chapter_directions`/`_fail`/`chapter_selfcheck`；验证：`test_happy_path_material_and_grades` 断言 `chapter_directions` 计量入账（TokenLog 直查）＋失败路径留痕口径（`_fail` 后缀沿用既有实现）

## 4. 排上与撤章（后端）

- [x] 4.1 `create_chapter` 扩展：请求体 `{title, plot?, challenge?, ending?, acts?, stage?}`，同 session/commit 内建章＋经 `store.apply_chapter_data` 写五段（不新写标量路径）；验证：`test_chapter_plan_ai_t1.py` 新增两项——排上五段同一事务落库（直读列断言）＋`plot_stage` 越界 422 先于建章；全量 pytest **1326 通过** ✓
- [x] 4.2 幂等：**client_token 幂等键**（前端每次「排上意图」一个 token，服务端进程内 TTL 120s 记忆首次建出的章）——同 token 重放返回同一章；无 token 的裸重放＝作者真想再排一章（正常续号）。验证：`test_adopt_idempotent_by_client_token`（同 token 两发 → 同 ref、库中一行）＋`test_chapter_plan_ai_t1.py` 双发用例（①同 token 同章 ②裸重放续号）＋e2e「双击幂等」真打两发断言同 ref
- [x] 4.3 `delete_chapter` 守卫：仅**本卷最后一章＋拟定＋无正文**可删，否则 409（非尾章→「先删其后的章节，或走重拆整卷」；有正文/已归档→重写或归档）；验证：`test_dual_write.py` 按新契约改写——非尾章单删 409 ✓、尾章可删 ✓、删尾章后再建复用同章号 ✓
- [x] 4.4 `resolve_prev_chapter_ending(db, project, vol, ch_no)`（与 `resolve_prev_ending` 同族；正文末段优先的同构先例＝`write/plot_sim.py` 的上一章结尾口径）：上一章 `has_prose`→正文末段（来源「取自正文结尾」）；无正文→`ladder_exit`（来源「拟定，取自章纲落点」）；卷首章→复用既有卷级取法。**并暴露为只读端点**（`GET /volumes/{ref}/next-chapter-anchor`，全档可用——手写路径不发 AI 请求也要进场，前端 5.1 依赖本端点）；**同时给 `GET /volumes` 树的 chapters 行集补 `plot_stage`**（派生视图数据，`VolumeChapterMeta` 同步）。验证：三分支单测＋来源文案断言＋端点契约测试
- [x] 4.4b （并入 4.4，占位保序）
- [x] 4.5 `stale` 置位：保存事务内若本章 `ladder_exit` **trim 后实质变更**且下一章（主线序）`has_prose` → 置位（清除沿用既有「本章保存/归档即清」——已知自动保存会清标记，故界面警告以一次性提示为主、标记为辅）；验证：单测「实质改结尾→下一章 stale」「仅微调措辞→不置位」「下一章保存→清除」

## 5. 前端 · 弹窗与入口

- [x] 5.1 `ChapterPlanModal`（`<Modal width={940} wbStyle>`）：手写/AI 共用卡面——进场只读行＋来源小字、五段（`.field`+`.input/.textarea`，`chapter_acts` 一行一条）、阶段六档 select；AI 态渲染三方向卡（`.pick-*`，进场行 `pk-in` 打头对齐产品行序）＋角标＋「剧情吸引力/差在哪」两块＋**checks（0–3 条「拿不准」，呈现在「差在哪」之后）**；**手写卡的进场/配额判定消费 `next-chapter-anchor` 端点**；**主线末端门禁与卷纲空门槛的置灰/拦截判定落在两入口组件（5.3），组件测试各一条**；验证：组件测试覆盖两路同卡面、进场来源小字两种、手写最小可排（仅剧情）、checks 渲染
- [x] 5.2 `useChapterPlan`（挂 NovelWorkspace）：`entrySource: manual|ai`、`phase: idle|busy|error`、**`submitting`（排上请求在途，Modal locked＝Esc/遮罩全失效——服务端幂等不能替代 UI 锁）**、**`landed`（落点卡数据，宿主＝关弹窗后由中栏渲染，对齐卷级 confirmResult 先例）**、`directions/note/pick/draft/scIgnored`、token 守卫取消；manual 不发请求直接空白卡；验证：组件测试「busy 中关窗→请求弃」「排上中 Esc 不可关」「落点卡两出口」「换 3 个方向→重置」
- [x] 5.3 三入口落位（D8）：中栏 ol-top「拆下一章」→手写表单；右栏新增「拆下一章（AI）」——**挂 `VolumeAssistPanel` 的卷纲页签（`volume-replan` 同级 ai-tool 块），`isPro/onUpgrade` 经 Rail 注入（该面板现无此 plumbing）**；免费档置灰＋「AI 三方向需 PRO」＋升级出口；左树卷行右侧「＋添加章节」沿用；树底「拆下一章」删除；验证：断言中栏无 AI 卡与三方向、免费锁定态、树底按钮缺席
- [x] 5.4 AI 四态渲染（D12）：busy（转圈＋播报＋副行）、error（两种文案＋三出口）、只出两套（note＋2 卡）、换方向；验证：组件测试 route 打桩逐态断言、失败三出口齐全
- [x] 5.5 排上与落点卡：调扩展后的建章接口；落点卡＝「已排上（拟定）＋已带入 N 项（逐项实列，空项不冒充）＋还差 6 项必填＋**三出口**（补这 6 项，开始写／继续拆下一章／撤销排上）」，**不叫 `landing-card`**；验证：组件测试落点卡文案与三出口、双击只建一章、撤销后树回退
- [x] 5.6 回改与撤销：左树章行/派生视图行（**hover 回改动作项，不改变点击＝选中语义**）/落点卡三处通同卡，**打开时 GET 章档案载入既有五段，保存走既有 `saveChapter` 合并链并同步章选择态（防章纲 3s 自动保存用旧快照互抹）**；改「本章结尾」时下一章已排→一次性提示、下一章有正文→警告＋stale 标记显示（沿用树行既有口径）；撤销入口仅本卷最后一章且无正文；验证：组件测试三入口同卡、「回改保存后紧接章纲自动保存，五段与六项均原样」、警告与标记、撤销边界
- [x] 5.7 重拆整卷：卷页「重拆本卷」入口（`volume-resplit`，有拟定章才显示）＋`ResplitConfirmModal` 盘点确认（列出将被移除的拟定章、写明保留章数）＋后端 `POST /volumes/{ref}/chapters/resplit` 按章号**降序**逐章走删章守卫；验证：`test_resplit_removes_only_planned_desc`（removed 降序/kept 保留/章号复用无跳号）＋`test_resplit_noop_when_nothing_planned`＋e2e「重拆整卷」（盘点→确认→树回退→可重拆）

## 6. 前端 · 章纲表单与卷页派生

- [x] 6.1 `chapterForm.ts` 加三格（challenge/chapter_acts 行编辑/plot_stage 下拉）——**不进必填六项**，整表回传；验证：回归测试「保存章纲后三格原样」（防 `_disassemble_scalars` 抹除）
- [x] 6.2 章纲页呈现三格（「来自拆章」组，可改）；验证：组件测试拆章值回显、可修改保存
- [x] 6.3 卷页派生视图：节点块替换为「剧情推进（派生）」——已排章阶段序列＋零章空态文案（数据：`GET /volumes` 树的 chapters 行集补 `plot_stage`，`VolumeChapterMeta` 同步——**后端配套见 4.4b**）；验证：组件测试排章后即时反映、回改阶段同步、零章空态
- [x] 6.4 章级 AI 自检（D16）：入口＝**拆章手写卡底条「AI 看一眼这一章」**（手动触发、全档免费）；三组结果（衔接/配额本地判＋剧情吸引力 AI 四维短评、**不给字母**）用 `.rp-*` 渲染；**端点收卡面草稿**（`POST /chapters/ai-selfcheck`，排上之前章未落库）；验证：vitest「自检：免费触发，卡面草稿随请求携带，出三组…不给字母」＋「自检失败与降级」＋「warn 组（衔接漂移/配额越界）」＋「补锚失败不带进场」；pytest `TestSelfcheckDraft` 7 项（排上前三组/衔接漂移/匹配/配额越界/AI 组失败不牵连/不合形降级/未知卷 404）＋e2e「自检」真打端点

## 7. e2e、口径与收尾

- [x] 7.1 e2e 新增（14 例，`e2e/chapter-plan.spec.ts`，隔离栈 14/14 绿）：免费手写排上全链（最小填写→落点卡→补章纲入口）；AI 四态（route 打桩：busy→出卡→选 S 卡→排上；失败三出口；只出两套；换方向）；双击幂等；删章守卫 409（**含非尾章 409 引导重拆**）；回改结尾→下一章 stale；派生视图反映；**重拆整卷（盘点→确认→树回退）**；**非末端卷入口置灰**；**卷纲空门槛拦截**；**卷纲空门槛**改由 pytest 覆盖（`test_chapter_plan_ai_t3.py::TestDirectionsGate`——容器无 Key 时模型门先于空门槛 503，e2e 到不了）；**回改→下一章 stale 的置位**亦由 pytest 覆盖（下一章需已有正文，而正文受 frontier 排队门禁约束，e2e 只断言「不静默提示＋落点真落库」）；验证：隔离栈 e2e 14/14 绿 ✓
- [x] 7.2 存量断言清算（实做：`modals-pr5.spec.ts` 删章例改 409 断言＋`useWorkbench.deleteNode` 失败透出服务端原因（原为静默）；`volume-plan/workbench-features` 全量 e2e 复核无回归）：`volume-plan.spec`（`landing-card` 不受影响）、`workbench-features.spec`、`volumeWorkspace.test.tsx`（节点块退役）、`volumePlan.test.tsx`、**`modals-pr5.spec.ts`（写正文后删章的用例在守卫下必红——改走 409 断言或先清正文；前端删除入口补 409 toast 断言）**、`design-parity-book.spec.ts`（confirmed 章只开弹窗不删除，暂安全但登记脆性）；验证：pytest 1340／vitest 770／tsc 干净 ✓（`design-parity-book` 未受影响）
- [x] 7.3 口径（grep 实跑：新面（ChapterPlanModal/useChapterPlan/VolumeAssistPanel/NovelWorkspace 拆章段）零命中「名次/落库/闭集/降级/素材包/四维」——唯一命中是 volume-plan-ai 遗留 tooltip「保存才落库」（`VolumeAssistPanel.tsx:224`，非本 change 文案，登记不改）；语气词：toast.error 11／success 4／info（拆章新面用 info 提示「下一章的进场会跟着变」）——无第四种；`data-testid` 与决策记录 H3 一致）：新文案作家语言（grep 断言不含「名次/落库/闭集/降级/素材包/四维」）；`data-od-id`/`data-testid` 按决策记录 H3 清单冻结；语气词仅 info/ok/warn/err；验证：grep 输出见上（附在本行）✓
- [x] 7.4 复用核对（D19，grep 实跑）：前端新增样式仅 book.css 9 类（**首轮漏做已在检视后补齐**：早先那条「对 origin/main 只剩 --faint 一行 diff → 9 类已合入 main」是**误判**——当时的 grep 模式混进了旧类 `pick-card`，命中全是旧类）；新弹窗用既有 `Modal`＋既有类（`mcard/rp-list/rp-row/del-inventory/inv-chip/field/input/textarea`），未新建第二套；后端：排上走 `create_chapter`＋`store.apply_chapter_data`（service.py:72,83）、进场走 `resolve_prev_chapter_ending` 同族、生成/解析/降级/越纲复用 `volumes.ai_plan`（ai_plan.py:23-30）、校验复用既有 sanitize 模式（未知轴丢卡）；**重拆整卷走单章删除守卫降序**（不留章号空洞）；前端 grep 断言未新建第二套卡面/表单/弹窗类（新增仅 book.css 9 类）；后端 grep 断言无平行建章/取数/校验路径（排上走 `create_chapter`+`apply_chapter_data`、进场走同族函数、校验走既有 sanitize 模式）验证：核对清单逐条打勾＋grep 输出 ✓
- [x] 7.5 `src/coverage-contract.ts` 登记新文件（`chapterPlanApi.ts`/`useChapterPlan.ts`/`ChapterPlanModal.tsx`）（`ChapterPlanModal`/`useChapterPlan`/新端点模块）；验证：`coverageContract.test.ts` 5/5 绿 ✓
- [x] 7.6 收尾门禁（pytest 全量 **1340 通过**；vitest 全量 **770 通过**；tsc 干净；design:lint 通过；design:check 7/8——`list.empty` 1.416% 红＝**存量**（该屏源文件 `NovelListPage.tsx` 与本 change diff 零交集；diff 图差异＝联网更新横幅＋字体光栅漂移，与本 change 无关，与既有记忆「parity 存量漂移」一致）；全量 e2e **188 通过 / 0 失败 / 19 跳过**（9.5 分钟，隔离栈 cpa；含 `chapter-plan.spec.ts` 14/14 与 `modals-pr5` 4/4））：pytest 全量＋vitest 全量＋tsc＋design:lint＋design:check＋全量 e2e；验证：六项全绿（parity 1 条存量红已登记）后申请检视 ✓

## 8. 原型态 → 用例覆盖映射（`/goal` 的「界面测试用例 100% 覆盖原型设计」证据）

原型 `docs/design-c/drafts/ai-novel-c端-卷下拆章.html` 演示条 8 态＋卡面细节，逐条对应：

| 原型态／面 | e2e（`e2e/chapter-plan.spec.ts`） | vitest（`__tests__/chapterPlan.test.tsx`） |
| --- | --- | --- |
| ① 手写五段（弹窗） | 手写路径全链（d-title/d-plot/d-obstacle/d-ending/d-acts） | 打开即空白五段＋进场只读（含来源小字） |
| ② 本章卡 · 可改 | AI 四态（选卡→本章卡，角标跟到卡上）＋**回改两例**（左树 hover／派生行 → 同一张卡面预填） | 点卡进本章卡／读卡装五段（标题变「改第N章」、按钮变「保存这一章」） |
| ③ 落点卡 · 桥 | 手写全链（**已带入 5 项逐项列出**＋还差 6 项＋三出口＋回改出口） | 落点卡：带入项逐项列出（空项不冒充）＋吃掉后清空 |
| ④ 剧情推进（派生） | 派生视图（按章列阶段＋标题，回卷页即时反映；行可点开回改卡） | —（该屏只由 e2e 覆盖，组件级无 plot_stage 断言） |
| AI · 3 个方向 | AI 四态（3 卡＋角标 S/A/B＋「剧情吸引力／差在哪」＋checks） | 出卡：三卡角标（S 带「最吸引」）＋两块＋阶段行 |
| AI · 正在想 | AI 四态（split-busy 先可见，门闩后放行） | 正在想（busy 态） |
| AI · 出卡失败 | AI 失败三出口（重试／自己写这一章／先不拆） | 失败三出口 |
| AI · 只出两套 | 只出两套（split-note 降级说明＋2 张卡） | 只出两套 |
| 换 3 个方向（卡底按钮） | 换方向（第二次响应覆盖第一次） | — |
| ⑥ 自检（手写卡底条，免费） | 自检（三组：衔接/配额/四维短评＋最弱一维；真端点 200/503 契约） | 自检（草稿随请求体＋三组渲染＋不给字母） |
| 免费档：AI 入口置灰带 PRO 说明 | 免费档（volume-split-ai 置灰＋locked 说明＋**可点升级出口**＋手写照常） | —（右栏面板三态由 volumePlan.test 覆盖，不含拆章入口） |
| 阶段六档 select | 派生视图（开局铺垫）＋手写全链 | 阶段六档 select：六个选项齐（逐项断言） |
| 角标 `pk-corner`（S 带「最吸引」） | AI 四态（pick-corner-3 含 S 与「最吸引」） | 出卡（pick-corner-3） |

**表内每条都已对照测试文件核过**（首版有 4 行引用了不存在的 vitest 断言，已在检视后改正）。
产品相对原型多出 4 处入口（左树 hover「改这一章」／派生视图行可点／落点卡第四个出口／免费档升级按钮）——
它们是 spec 5.6 与 D12 的规格要求，原型未画；已在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记。

原型之外的规格面（D12/D14，非原型演示态）由 e2e 与 pytest 分担：
末端门禁（e2e 非末端卷）／重拆整卷（e2e 重拆整卷）／删章守卫（e2e 删章守卫＋pytest）／
卷纲空门槛（pytest `TestDirectionsGate`）／stale 置位（pytest `TestStaleSecondTrigger`）／回改不静默（e2e 回改结尾）。

### 8.1 视觉对拍（`/goal` 的「100% 符合原型设计」证据，2026-09-23 补做）

七态截图逐对比对（应用隔离栈 ↔ 原型 demo 条；`/tmp/vis-app-*.png` ↔ `/tmp/vis-proto-*.png`），
比对发现五处偏差**同批修齐**（明细在 `docs/design-c/prototypes/ADJUSTMENTS.md`「视觉对拍后追加」）：
kicker 补章号／三方向态与失败态底条收「排上」死按钮／点卡切单卡视图（三卡收起）／
排上按钮点名章号＋底条落地提示／进场行点名章号。修后七态复核一致：
①手写（kicker 第N章＋note＋自检＋排上（第 N 章））②三卡（首行「第N章的 3 个方向」＋底条两钮）
③本章卡（单卡面＋出口行）④两套（降级 hint）⑤失败（三出口、底条空）⑥落点卡（带入 N 项逐列＋接引句）
⑦派生（剧情推进（派生）＋N 章标签＋行结构）。选卡后保留「换 3 个方向／自己写这一章」出口行＝
产品超出原型第 5 处（原型该态无回头路），已在 ADJUSTMENTS 登记。
修齐后门禁：vitest 816（本文件 55）／tsc 0／design:lint 0／design:check 7-8（list.empty 存量）／
chapter-plan e2e 16/16（新增 kicker、底条分态、选卡切卡面断言）。
