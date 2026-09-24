## 1. 片段文件与模板占位符（先文本后代码，对拍打底）

- [x] 1.1 落四个片段文件（文案照 spec 成稿逐字）：`client/backend/prompts/pos_ch1.prompt`、`pos_golden3.prompt`、`pos_vol_start.prompt`、`volume_pos_first.prompt`；每个文件加版本头注释（v1＋日期＋一句变更），验证：文件在、加载器 `prompts.load(name)` 逐个读出无异常
- [x] 1.2 `chapter_split.prompt` 加 `<<position_rules>>` 占位符一行（素材块之后、硬规则之前），主体十条硬规则/差异声明/评分契约逐字零改动；`volume_expand.prompt` 加 `<<volume_pos_rules>>` 占位符（`<<hard_rules>>` 之后），验证：git diff 仅各一行占位符
- [x] 1.3 `volume_rules.prompt`：七条硬规则扩八条（规则 8＝卷末点名高潮事件与位置（前/中/后），置于【体检判据】锚点之前）、体检判据新增「对节奏」组；验证：`_rules_sections()` 锚点切分照常，逐字对拍测试更新后绿
- [x] 1.4 既有对拍/快照测试防位置行打穿：凡钉渲染产物的用例改为剥首行「【本章位置】…」归一化再比（或按位置分快照），验证：既有用例全为包含式断言（无逐字全等钉渲染产物），后端全量 1386 绿＝未被位置行打穿

## 2. 拆章侧装配（chapters/ai_plan.py）

- [x] 2.1 选择器纯函数 `chapter_position_tags(global_ch, ch_no) -> list[str]`＋全局章号计算（前面各卷已拆章数滤 ghost＋卷内序号，`chapter_repo.list_by_project`）；单测钉边界：vol1ch1→ch1、vol1ch2→golden3、vol2ch1→vol_start、vol2ch2→无、全书第 3 章→golden3，验证：pytest 单测绿（边界参数表含「全局第 3 章＋卷首」双角色叠加合法态）
- [x] 2.2 `_blocks_chapter` 首插「【本章位置】全书第 X 章｜本卷第 Y 章（本卷共 Z 章）」数据行（未设章数目标省略括注），不占既有①→⑧任何预算；验证：单测断言位置行居首＋五大标记顺序（含式），既有①→⑧块文本零改动
- [x] 2.3 片段注入：按 tags 拼接 `pos_*.prompt` 渲染进 `<<position_rules>>`，无片段渲染空串（连标题不留）；多片段以空行双换行拼接（标题各占行首）；同章重拆幂等单测（同状态同输出），验证：pytest 渲染断言（无快照——本仓无渲染快照基线）
- [x] 2.4 升档提醒：本地判末 3 条 stage（全落 {开局铺垫,冲突初现,矛盾升级} 且无升档、卷内计数、非末章且剩余>1、含重要转折/高潮爆发不触发）→素材尾部注入提醒行（spec 文案逐字）；单测四态：触发/卷边界重置/到顶不触发/末章不触发，验证：pytest 绿
- [x] 2.5 排满提示：触达章数目标且已拆章 stage 序列不含「高潮爆发」→响应 `warnings` 追加「这一卷已排满但还没到高潮——回卷纲核对节奏」；断言不进重试链路、不拦卡；验证：单测＋sanitizer 硬校验三类（schema/长度/闭集）用例零改动仍绿
- [x] 2.6 提醒行升格为提示词契约的逐字对拍（提醒文案与 spec/specs 引文一致），验证：文案漂移测试红→绿

## 3. 拆卷侧装配（volumes/ai_plan.py）

- [x] 3.1 expand 端点注入 `<<volume_pos_rules>>`：vol_no==1 → `volume_pos_first.prompt`，否则空串；`<<hard_rules>>` 文本与 rules 单源逐字不混拼（断言两占位符各自渲染），验证：单测两场景＋对拍
- [x] 3.2 options 端点断言无节奏片段（渲染产物不含 pos/volume_pos 任何文本），验证：单测
- [x] 3.3 卷纲体检 prompt 注入「对节奏」判据组（随 `_rules_sections()[1]` 既有链路自动生效），端点返回的 groups 校验放行 ≥2 组既有逻辑不动；验证：契约测试（伪造四组输出→report 四组透传；两组仍合法）

## 4. 前端文案与提示（零结构改动）

- [x] 4.1 规划台规则作家语言清单（RULES_FOR_AUTHOR）七条→八条，验证：tsc 零错；⚠️记账=该常量当前在两处弹窗均未渲染（「展开时遵守的规则」折叠清单存量未接线，基线即如此）——数据层对齐，接线另行立项
- [x] 4.2 `warnings` 渲染链路复核＝`state.warnings.join("；")` 原样透传（ai-note），既有 vitest「越纲警告上屏」钉住渲染；新排满提示文案由后端测试钉住

## 5. 门禁与验证

- [x] 5.1 后端 pytest 全量＋前端 vitest 全量；对拍族（片段×4、volume_rules、提醒行）全绿，验证：pytest 1386 绿＋vitest 817 绿＋tsc 零错＋ruff 零新增（S110 为存量）
- [x] 5.2 出卡素材特征串断言（实做于后端 pytest 层——本仓 e2e 的 AI 全在 page.route 桩上，看不到后端系统提示词）：vol1ch1 含 ch1 片段、卷中普通章不含任何片段、vol2ch1（全局≥4）不含 golden3，验证：test_plan_pacing_rules 27 绿
- [ ] 5.3 确定性哨兵（一次性脚本，结果记 change evidence，不建常驻框架）：ch1 三卡 stage 铺垫占比趋零、JSON 契约零回归（解析率/字段超长/名次形态）、expand 卷末字段位置词（前/中/后）出现率，验证：报告落 `evidence/`（→ 验证尾巴移交主检出 todo.md 低优先段，2026-09-24 归档时移账；工具已备：哨兵脚本在 evidence/）
- [ ] 5.4 人工抽检 20 例盯 `diff.one_liner` 互换通过率与「小兑现」三卡互异（golden3 第 3 章），结论记 evidence；劣化则按 design 风险节单变量回退（收窄 ch1 第 3 条或 golden3 措辞），验证：evidence 有结论与回退决策（→ 验证尾巴移交主检出 todo.md 低优先段，2026-09-24 归档时移账；工具已备：哨兵脚本在 evidence/）
- [ ] 5.5 全量回归：C端 e2e 全量（隔离栈照 per-session 配方）＋相关 parity 无新增红，验证：跑批输出留痕（→ 验证尾巴移交主检出 todo.md 低优先段，2026-09-24 归档时移账；工具已备：哨兵脚本在 evidence/）
