# 卷的瘦身与三选一抽卡 — 任务（v2：三路评审合并版）

## 1. 数据与退役

- [x] 1.1 `volumes` 加列 `antagonist_type`（VARCHAR(20) 闭集）/`antagonist_line`（VARCHAR(150）：
  **登记进 `db_lifecycle.ADDITIVE_COLUMNS`（活注册表，DDL 长度与模型列型逐字一致）；删除
  `main.py` 的 ADDITIVE_COLUMNS 死副本**；迁移四条验证（照 plan_line 先例；类型非法 422）
- [x] 1.2 退役读写链：`VolumeUpdate` 对五键（template_name/plan_line/goal/plants/reveals）
  **显式 validator 422 拒收**（其余未知键维持 ignore）；`_DETAIL_SCALARS`/service 写停五键；
  **goal 并入落点＝`get_volume` 服务端组装时合并进 ending 尾句返回**（PUT 保存即固化，注明）；
  create/repo 链撤 plan_line 空串写入与 `VolumeCreate.plan_line`；验证：PUT 带五键 422、GET
  回读旧卷 goal 并入尾句、新卷无五键
- [x] 1.3 `get_volume` 的 cast_members 改聚合：卷下各章 `chapter_characters` 行集合集（去重
  保序）；**空态＝无章即空数组**（主角仅交集时置顶）；名字在 antagonist_line 命中（含
  characters.aliases）标反派；行形状 `{name, role}`（主角/反派标注进 role）；验证：单测
  四态（有章聚合/无章空/主角置顶/坎标反派）
- [x] 1.4 hooks 表 additive 加 `planned_volume_no`（可空 INTEGER，同批次登记）；`hook_to_dict`
  与 `_PATCHABLE` 带上；迁移验证随 1.1
- [x] 1.5 新增 `POST /api/novels/{id}/hooks/batch`：body `{items:[{description,
  planned_volume_no?}]}`，服务端与 active 台账 **difflib≥0.6 判同**（阈值常量单源），返回
  `created[]`（带 H-#### 编号）/`skipped[]`（带对齐编号）；逐条结果不整批 4xx；无 AI 门禁；
  验证：单测同条/近似条/全新条三态＋`planned_volume_no` 落库回读

## 2. 端点契约

- [x] 2.1 options：出参每套带 `antagonist_type/antagonist_line`（结构化，类型非法回退「人物」）
  ＋侧重轴结构化枚举字段；**入参扩已答四问约束**（`answered:{q1,conflict,antagonist_type,
  antagonist_line,q4}`，prompt 加「作家已答的照抄不改写」段与占位符）；实体差集只对
  antagonist（人物/势力型）点到的名字＋factions；验证：单测断言已答逐字入 system、四问
  字段、类型回退；**删死代码 `PlanPickBody`**
- [x] 2.2 expand：入参扩卡面四问（conflict/antagonist_type/antagonist_line/ending 可选——
  带入则 AI 不得覆盖）；出参撤 `plan_line` 键、草稿带 antagonist 两字段、plants/reveals 为
  台账建议；验证：单测断言带入字段不被覆盖、出参形状、不落库
- [x] 2.3 check：「对主线」组三判据（未填＝warn 不编造；递进结论带证据）；素材加上一卷/
  本卷对抗物两行；**boss 台阶提示落点＝`volumes/ai_plan.py` 按 genre 分支追加（不动
  `build_genre_section` 共享单源）**——断言写章链 system 无 boss 提示、玄幻/都市卷链含、
  其余不含；`volume_rules.prompt` **追加式**补对抗物判据段（【体检判据】标记与既有文本
  不动，保逐字对拍绿）
- [x] 2.4 T1 fixtures 随迁：`VALID_EXPAND` 补 antagonist/删 goal；断言改四问键；近似样本
  本地合成补齐（真模型产物无 antagonist 字段）

## 3. 前端 · 抽卡与四问

- [x] 3.1 新增 PickCardsModal（三选一）：940 宽横排三卡（窄屏纵排）、每卡四问答案＋侧重轴
  结构化字段渲染（**禁止展示串 split 反解析**）、busy/error/两卡 note 顶部态；点卡选中可换
  选；「确认这一套，成卷」未选禁用；付费打开规划入口即自动调 options；「↻ 换 3 套」重调
  清选中；error 态＝重试/转手写（模型未配＝引导去配置＋转手写）；aria（焦点圈/选中卡/
  busy aria-live）；验证：组件测试覆盖 busy/error/三卡互异/选中/换组/两卡 note/转手写
- [x] 3.2 确认链与 token 守卫：确认＝expand（带卡面四问）→建/更卷（含 chapter_target）→
  `hooks/batch` 入册（skipped 提示对齐编号）→关弹窗→**clearSelection** 落落点卡＋自查条
  可关闭提示（已排章书 toast）；写请求发出前 Esc/背景＝取消不落库（token 逐步校验）、
  发出后 locked；不可二次提交；验证：组件测试「确认中 Esc 后端零建卷请求」打桩断言
- [x] 3.3 VolumePlanModal 改四问页：撤单句输入与 Q4 角色；四问答区＋「让 AI 铺完剩下的
  问题」＋「直接创建这一卷」（免费，走 createVolume 四问扩展，卷名兜底）；坎输入新面孔
  quick-card（识别名字不在角色表→建卡提示，KNOWN 为角色表查询）；验证：组件测试三态
- [x] 3.4 回填链随迁：段序＝进场→1 主旨→2 冲突→3 坎→4 卷末→卷名/章数→角色聚合（只读）→
  伏笔台账建议（只读）→留到写→自查；撤 goal/plants/reveals 落值；touched/禁保存沿用；
  验证：组件测试段序与落下值
- [x] 3.5 AddVolumeModal 退役与统一入口：壳层去挂载与 addVolOpen、删组件；**三处空书入口＋
  树头「＋」统一接 openPlanVolume 按档分流**；`VolumeCreate` 扩可选四问＋antagonist＋
  chapter_target（共用）；验证：组件测试三处+树头同开规划流（两档各一）、grep 无「添加卷」
  弹窗与「初始章数」残留

## 4. 前端 · 卷纲页

- [x] 4.1 卷纲查看/编辑重写为四问一页纸：查看态无折叠块（进场→四问四行→角色聚合→伏笔指
  引→节点有值才显→留到写→进度线；头部卷名＋章数不设不显）；编辑态四问编号序（1→4）＋
  卷名/章数＋聚合只读＋伏笔台账建议预览；保存必填主旨+冲突；验证：组件测试两态/空态/
  保存回读/旧 goal 并尾句
- [x] 4.2 `volume_outline_text` 装配：撤「整体目标」与两条伏笔行、加「- 本卷对抗物：〈类
  型〉·〈一句话〉」；render 单测随迁（含伏笔行缺席断言）
- [x] 4.3 落点卡概要行沿用（主旨——坎）；体检报告 rp-row 新判据条；验证：组件测试断言
- [x] 4.4 聚合角色视图组件：只读行集（主角 pill/反派标注）、空态文案；类型与 `VolumeDetail
  .cast_members` 新形状 `{name,role}[]`；前后端类型对齐；验证：组件测试三态

## 5. 门禁与口径

- [x] 5.1 免费口径回归：四问手写与「直接创建」免费、抽卡/铺空缺 PRO、体检与 hooks/batch
  免费；grep 断言无「五个问题」「角色一问」「初始章数」「添加卷」残留、无内部术语；
  coverage 登记 PickCardsModal（与建议的 VolumeWorkspace/form.ts）；右栏主线空时入口变
  「先补主线」取数补齐
- [x] 5.2 存量断言随迁：volumePlan.test（~70% 重写）/NovelWorkspace/VolumeWorkspace；
  e2e：volume-plan.spec 三用例重写（抽卡链/免费四问/手写 AI 链）＋**workbench-features
  两处添加卷链**＋free-writing `writeFirstChapter` 改「＋新增一章」垫卷链＋creation-flow
  文案；全绿
- [x] 5.3 埋点与度量：PRD §7 事件全量（plan_entry_open/pick_drawn/redraw/select/
  confirm_ok|fail/desk_manual_create/expand/volume_saved/first_chapter_in_vol/check_run/
  hooks_registered{dupe_skipped}）本地可关；测试断言事件名

## 6. 端到端与回归

- [x] 6.1 e2e 重写「付费抽卡链」：点规划→三卡（打桩）→选 B→确认→后端直查卷行（含四问＋
  章数）＋hooks 表新增行（batch）→落点卡含卷名/章数/自查提示→卷纲四问一页纸含坎；
  「确认中 Esc 不落库」用例；免费链（四问→直接创建）；手写 AI 链保留
- [x] 6.2 全量门禁：pytest＋ruff；tsc＋vitest --coverage＋build；openspec validate
  --strict；design:lint；design:check（book.html 弹窗已撤——基线与实现同批改后回绿）；
  e2e 全量本机隔离栈
- [x] 6.3 ADJUSTMENTS 终版核对（抽卡弹窗/四问/退役/聚合/伏笔归台账/AddVolumeModal 退役）
  与实现一致性

## 7. 章层后续（不在本 change，todo 登记）

- 章纲点新名字→建卡提示；正文提示词「本卷在场的人」消费聚合清单；体检「登记没戏份」改读
  聚合；退役列/表（template_name/plan_line/goal/volume_cast_members/plants/reveals）物理清理
