<!-- c-og-fields-slim 任务清单：核心任务／读者当前状态退役，归档门槛六改四 -->

## 1. 后端：消费点拆除与门槛收敛

- [x] 1.1 `workflow/gates.py`：归档门槛删 `current_task` 与 `reader_expectation.state` 两查（六项→四项）；对应用例改（pytest gates）
- [x] 1.2 `chapters/store.py`：dump 不再输出 `current_task`/`reader_expectation.state`；apply 不再把两键写回列（其余 memo 键照旧）；往返用例改
- [x] 1.3 `write/ai_check.py`：删体检「现有章纲」行的「核心任务：…」；用例改
- [x] 1.4 `write/plot_sim.py`：删素材/章节清单的核心任务行与「缺失回落核心任务」回落支；strategy 消费保留；用例改
- [x] 1.5 `chapters/ai_draft.py`：`_FILLABLE_KEYS` 删 `current_task`/`state`；起草响应 memo 不再含两键；用例改
- [x] 1.6 `models/chapter.py`：两列保留，注释标「退役 c-og-fields-slim，只留不写」

## 2. 前端：表单与文案

- [x] 2.1 `chapterForm.ts`：OgForm 删 `task`/`rstate`；REQ_FIELDS 六→四；GAP_TO_FILL_KEY 删两映射；EMPTY_OG_FORM/toBackend/fromBackend 同步；ogFormIssues 对应校验删
- [x] 2.2 `OgPane.tsx`：删「核心任务」「读者当前状态」两折叠组（含必填星标）；补缺缺口清单随 REQ_FIELDS 自动收敛
- [x] 2.3 `NovelWorkspace.tsx`：落点卡「还差 6 项才能开写：…」→「还差 4 项才能开写：预期策略、必须完成的变化、主情绪、段落规划」；「补这 6 项，开始写」→「补这 4 项，开始写」
- [x] 2.4 全仓 grep 收尾：`核心任务`/`current_task`/`rstate`/`reader_expectation.state` 在 client 的残留引用清零（历史归档文档除外）

## 3. 测试同步

- [x] 3.1 vitest：chapterForm（REQ_FIELDS 四项/ogFormIssues/ogPatchFromFills/往返映射）、useOutline、NovelWorkspace（落点卡文案）用例改＋新增「不再出现核心任务/读者当前状态」断言
- [x] 3.2 pytest：gates（门槛四项通过/缺失拒绝）、plot_sim（素材与回落链）、ai_check（体检行）、ai_draft（白名单拒绝两键）、store（往返不含两键）全绿
- [x] 3.3 e2e：落点卡「还差 4 项」与「补这 4 项」断言；章纲页无「核心任务」格；四项门槛归档路径走通

## 4. 原型与 parity

- [x] 4.1 `book.html` 章纲视图删「核心任务」「读者当前状态」两折叠组；ADJUSTMENTS.md 登记一段（c-og-fields-slim）
- [x] 4.2 `design:lint` 0；`design:check` 受影响基线重录（章纲屏若在用例内）或确认不在用例内
- [x] 4.3 `tsc --noEmit` 0；全量 vitest／pytest 绿；chapter-plan-ai e2e 与章纲相关 e2e 绿

## 5. 收尾

- [ ] 5.1 门禁汇总＋PR（base main），正文列 478 后续：规格五 capability MODIFIED 的 sync 说明
- [ ] 5.2 归档前置核对：改完后 `openspec validate c-og-fields-slim` 仍通过；ADJUSTMENTS/规格措辞与实现一致
