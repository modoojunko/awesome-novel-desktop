<!-- c-og-fields-slim 设计：核心任务／读者当前状态退役，归档门槛六改四 -->

## 关键决策

### D1 DB 列「只留不读写」，不删列

`chapters.current_task` 与 `chapters.expectation_state` 是模型显式列（`models/chapter.py`）。SQLite 无迁移链、仓库纪律无 DDL 路径——删列不可行也无必要：两列留在 `create_all` 建表语句里（新库多两列空列，无成本），但**全链停读写**：

- `chapters/store.py`：dump（`_dump_chapter` 一族）不再输出 `current_task`/`reader_expectation.state`；apply（`_apply_memo` 一族）不再把 `memo.current_task`/`reader_expectation.state` 写回这两列（其余 memo 键照旧）。
- `models/chapter.py`：列定义保留，注释标「退役 c-og-fields-slim，只留不写」。

零用户基线（2026-09-18 拍板）→ 不做旧数据迁移：库中残留的列值与 memo 键读时忽略即可。

### D2 消费点逐一拆除（以 grep 清单为准，做完备证）

写正文链（`write/chapter_writer.py`）**本就不读**这两格——无需改动。要拆的消费点：

- `workflow/gates.py` 归档门槛：`current_task` 与 `reader_expectation.state` 两查删 → 门槛自然变四项（strategy/changes/mood/segments）。
- `write/ai_check.py`：体检「现有章纲」行的「核心任务：…」行删。
- `write/plot_sim.py`：`task = memo.current_task`、章节清单「核心任务：…」行、回落链「缺失回落核心任务」——全删；`reader_expectation.strategy` 消费保留（预期策略在册）。
- `chapters/ai_draft.py`：`_FILLABLE_KEYS` 删 `current_task`/`state`；`_existing_outline` 的 memo dump 照 JSON 原样（`memo` 整体序列化，两键自然为空——不需要特判）。

### D3 前端：表单键删除即门槛收敛

- `chapterForm.ts`：`OgForm` 删 `task`/`rstate`；`REQ_FIELDS` 六→四（rstrat/changes/mood/segs）；`GAP_TO_FILL_KEY` 删两项映射；`EMPTY_OG_FORM`、toBackend/fromBackend 映射（memo.current_task/reader_expectation.state 不再往返）；`ogFormIssues` 对应校验删。
- `OgPane.tsx`：删「核心任务」「读者当前状态」两个折叠组（含必填星标）；「还差 6 项」类文案不在此文件。
- `NovelWorkspace.tsx`：落点卡「还差 6 项才能开写：核心任务、读者当前状态、…」→「还差 4 项才能开写：预期策略、必须完成的变化、主情绪、段落规划」；「补这 6 项，开始写」→「补这 4 项，开始写」。
- 补缺链自动收敛：缺口清单由 `REQ_FIELDS` 驱动，`GAP_TO_FILL_KEY` 已同步删 → 前端不再下发两项。

### D4 原型与 parity

`book.html` 章纲视图若含「核心任务／读者当前状态」两组折叠 → 同批删除（设计文件化闭环：先改原型再改实现）；ADJUSTMENTS.md 登记一段。`design:check` 若章纲屏基线受影响（两组从原型与实现同批消失）→ 基线截图按管线重录；若章纲屏不在 parity 用例内则只需 design:lint。

### D5 拆章回改卡不受影响

回改卡（ChapterPlanModal）的 challenge/acts/stage 与本章剧情（summary）走「整表回传」，与本次删除的 task/rstate 无交集；`chapter-plan-ai` 的五段契约不动。

## Open Questions

（无——零用户基线下不做数据迁移与兼容读，已由 D1 定死。）

## 验证口径

- pytest：workflow/gates、plot_sim、ai_check、ai_draft（白名单）、store 往返相关用例同批改。
- vitest：chapterForm（REQ_FIELDS/ogFormIssues/patch 表）、useOutline、NovelWorkspace（落点卡文案）。
- e2e：落点卡「还差 4 项」断言、章纲页无「核心任务」格、归档门槛四项路径。
- design:lint + design:check（受影响基线重录）＋ tsc。
