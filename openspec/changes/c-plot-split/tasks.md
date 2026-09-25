# c-plot-split 任务

## 1. 原型先行（C端，硬性流程第 1 步）

- [x] 1.1 按 `docs/design-c/drafts/ai-novel-c端-章内剧情拆分.html`（v3.4）把「剧情」区（空态直接输入框/列表编辑/加删条/200 字上限）、右栏「AI 帮写剧情」动作（免费态 locked）、三版选一弹窗（共用首尾三卡＋S/A/B 角标＋换一批/自己写/就填这版）、采纳回执（常驻撤销）落进 `docs/design-c/prototypes/book.html`；验收＝浏览器手点六态（空/已填/免费/AI 出 3 版/失败/填好）与设计稿一致（证据：Playwright 六态冒烟 20/20 PASS＋design:lint 0 违规＋截图 docs/design-c/drafts/c-plot-split-shots/）
- [x] 1.2 在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记本功能每处相对基线的偏差原因（新类 .plot-sec/.pi-row/pick-* 复用说明、940px 弹窗、200 字 maxLength）；验收＝ADJUSTMENTS.md 出现本 change 条目（已登记，含免费态口径裁定与两处共享 helper 顺手修）

## 2. 后端数据与保存契约

- [x] 2.1 `models/chapter.py` 增 `plot_items` 列（Text、default `[]`、server_default `[]`），装配输出（空串/损坏按 `[]`）＋导出导入（加键兼容）；验收＝新增 pytest 覆盖 round-trip、损坏 JSON 不阻塞、导入缺失键按 `[]`（tests/test_plot_items_save.py：round-trip 含换行条目单条完整、损坏 JSON/空串/非数组不阻塞、真导出→真导入往返、导入缺失键按 []；全量 pytest 1445 绿）
- [x] 2.2 保存契约：presence-gate（缺键保留现值、显式 `[]` 清空）＋schemas 形状校验（字符串数组、单条 ≤200 截断不报错、≤12 条）；验收＝pytest 覆盖缺键不清空/显式空清空/含换行条目不切条，且既有缺键清空测试改按新口径钉住（test_plot_items_save presence-gate 三态＋非列表不误清；test_chapter_plan_ai_t1 缺键清空测试同批钉住：标量族旧口径不变、plot_items 例外）
- [x] 2.3 预算校验不进 ogFormIssues 类整表问题清单；验收＝测试证明超长输入不产生保存错误、自动保存不被冻结（vitest chapterForm.plotBudget.test.ts：超预算 plots 的 ogFormIssues 与不带 plots 逐字一致、恒空；pytest test_over_budget_save_is_silent_not_error：500 字×21 条走完整保存链不报错、静默夹 200×12）

## 3. AI 帮写剧情端点（PRO）

- [x] 3.1 生成端点（复用 ai_plan 骨架）：单次调用出 3 版（每版 2–6 条×≤200 字），三版共用进场条与结尾条、中段互斥；`_generate` 加 `max_tokens` 参数（默认 4096 不动，本端点 8192）；验收＝pytest 覆盖响应形状 `{ok, versions, grades, warnings}`、共用首尾、生成预算上限（tests/test_plot_ai.py：POST plot/ai-draw 四键形状＋三版 items[0]/[-1] 逐字共用首尾＋中段互斥；fake client 捕获 kwargs 断言 max_tokens==8192、temperature 0.7；素材四块齐）
- [x] 3.2 名次→字母（缺名次不出角标、卡照出不重抽）＋可用版本不足 3 判失败（重试封顶、失败二分）＋越界按句读截断不重试；验收＝pytest 覆盖 2 版→失败、缺名次→无角标、205 字条目→句读截断且末句不腰斩（test_plot_ai：2 版 ok:False 单调用不重抽、缺名次/并列名次 grades 空串卡照出、clip_plot_item 句读截断＋无句读硬截＋207 字条目进 warnings、0 可用版本才重试 temp 0.3 记 _retry 账）
- [x] 3.3 门槛三要素（概要/挑战/结尾）422 拦截＋生成素材口径（进场单源取数、不带伏笔台账）＋计量 `chapter_plot_fill` 族；验收＝pytest 覆盖三要素缺口 422、素材包含进场不含伏笔台账、记账留痕（test_plot_ai：缺挑战 422 大白话且零模型调用、种 NovelHook 断言其描述与「伏笔台账」均不进 system 而正文结尾进场块在、token_log 出现 chapter_plot_fill）
- [x] 3.4 `outline-ai-draft` fill-gaps 白名单显式排除 `plot_items`；验收＝pytest 覆盖携带 plot_items 的缺口清单被丢弃且其余键照常补全（test_plot_ai：missing 带 plot_items 时 fills 只回其余键、system 不含 plot_items；单独 plot_items 与越界键同待遇 400；_FILLABLE_KEYS 注释显式注记）

## 4. 提示词层接线

- [x] 4.1 素材包【本章剧情走向（分条）】块：单一渲染 helper，`material_markdown` 与 `to_prompt` 两路同调＋定位句（首尾以章卡为锚、中间以条目为主干、场景原材料定焦点）；验收＝parity 测试两路逐字一致＋golden 回归「空剧情两路逐字不变」全绿（write/chapter_writer.py `_plot_block` 单源（块名＋定位句钉死、单条内换行折叠为空格），两路插【场景原材料】之前；tests/test_plot_prompt.py parity 两路逐字同块＋3 条各占一行；golden fixture tests/golden/plot_empty_*.txt 抓自注入前产物，空剧情对拍逐字一致）
- [x] 4.2 润色骨架补第 10 要素（条目逐条保留不改写）＋`validate_polished_prompt` 条件锚（非空缺剧情段判不合格、为空不要求）；验收＝pytest 覆盖非空润色产物含剧情段、空剧情不校验该段、存量提示词优先级不变（prompts/prompt_crafting.prompt 十段要素＋第 10 要素「与约束红线同级不得改写」＋锚词条件行；test_plot_prompt 条件锚单测；test_write_prompt_polish TestPlotPolish 端点四态：缺段 502 不落库且素材包含剧情块／含段 200 落库／空剧情不要求／存量 write-prompt 优先级不变；模板指纹更新 九段要素→十段要素）
- [x] 4.3 `prompt_sources` 组装来源投影：「本章章纲」行含剧情条目（一条一行，空不计）；验收＝端点测试 chars/preview 含剧情文本、六处行序不变（write/prompt_sources.py ③补「剧情条目：」行；test_prompt_sources_api test_plot_items_in_outline_source 三条文本进 preview、chars 计入、total 对账、LABELS 行序不变＋空则不计钉住）

## 5. 前端（C端）

- [x] 5.1 chapterForm/OgPane 剧情区：`plots: string[]` 直传（禁 \n 拼串）、`ogToPartial` 恒带空存 `[]`、maxLength=200＋满 12 禁加、稳定列表 key（不用 index）；验收＝vitest 覆盖 round-trip 恒带键、含换行不切条、超长硬夹
- [x] 5.2 三版抽卡弹窗：复用 pick-* 词汇＋Modal 常驻挂载＋代际守卫（换一批清选中、关窗丢晚到响应）＋失败二分三出口（去模型配置/再试一次/先自己写）；验收＝vitest 覆盖换一批清选中、关窗后晚到响应不落表
- [x] 5.3 采纳/撤销语义：列表非空按钮明示「将替换已写的 N 条」、回执常驻到下次编辑、撤销恢复填写前列表（含非空）、「自己写」退回原列表；验收＝vitest 覆盖替换明示条数、撤销只回滚 plots、编辑收掉回执
- [x] 5.4 门槛拦截（大白话＋点击跳补填）＋已润色章改剧情软提示（不自动重算）＋免费态 locked（rail-locked＋升级出口）＋fill-gaps 请求不带 plot_items；验收＝vitest 覆盖三态（可用/缺要素/免费）与软提示出现条件

## 6. 回归与门禁

- [x] 6.1 后端全量 pytest 通过；验收＝在该命令输出末行贴出通过数（含本 change 新增用例）
- [x] 6.2 前端 vitest 全量通过＋`npm run design:lint` 全绿＋`tsc --noEmit` 通过；验收＝贴出三条命令的实际输出结论
- [x] 6.3 C端 `npm run design:check` 全绿（像素差 <0.2%）；验收＝贴出各场景像素差百分比（本 change 不触两端共享段——依据 proposal Design Impact：新增样式只落 C端 book.css 业务层，design-cross 不涉及）
- [x] 6.4 相关 e2e 更新并通过（剧情区编辑/抽卡三版/采纳撤销/免费锁定）；验收＝在本会话独立环境（独立容器名/端口/数据目录）跑绿并贴出用例数，收尾清理环境
