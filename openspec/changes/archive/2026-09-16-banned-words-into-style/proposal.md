## Why

「禁止使用以下词汇」这行写章提示词目前有三个来源：禁用词句面板的 7 分类词表、文风卡的幽灵键 `fatigue_words`（6.0e 迁移遗物，v2 白名单外、UI 无入口但注入仍生效）、文风硬约束里点名具体词的禁令句。来源散落导致作者在禁用词句面板看到的只是三路之一，改了不生效、生效的看不见；且「禁用词句」作为独立菜单与文风在用户心智上高度重叠（同为文字禁忌）。本变更把禁用词整体收编为文风硬约束的子区，禁用词句面板退役，设定页少一个菜单，注入与体检单源化。

## What Changes

- **BREAKING**（书级数据 + 设定 UI）：`settings/anti-ai.yaml` 退役——7 分类疲劳词展平去重并入文风 KV 的 `banned_words`，`structural_tic_patterns` 平移为文风 KV 的 `tic_patterns`；迁移经统一迁移感知读路径完成，完成后落标记位防回灌；**anti-ai 原键原样保留**（回滚安全＋导出/导入兜底，清理属后续版本）。
- 文风硬约束区扩为三块：① 禁令（自然语言 3–5 条，现状不动）② 禁用词（词表编辑器，模板预填 AI 腔词，蒸馏自动并入）③ 句式规则（正则＋阈值＋严重度，TicPatternEditor 整体搬入）。
- `writing-style` KV 白名单四键→六键（新增 `banned_words`、`tic_patterns`）；幽灵键 `fatigue_words` 归一时并入 `banned_words` 后剥离。
- 写章提示词「禁止使用以下词汇／禁止以下句式」段单源化：只从文风 KV 取数；`chapter_writer` 的 `style_fatigue_words` 幽灵合并行删除。
- 蒸馏 commit 的禁用词服务端 append 目标从 anti-ai 面板改为文风 KV；共址后新增缓解——commit 成功后前端回读并只把词表两键合入表单态，防旧表单快照保存覆盖丢词（见 design D4）。
- quality.py 程序化体检（词命中＋正则句式）、auxiliary 辅助写作注入、AI 体检——全部改读文风 KV，检查能力不缩减。
- 设定页左栏菜单 8→7 项：`08 禁用词句` 退役，末项变为 `07 伏笔`；「确认即前进」推进顺序同步；readiness 检查 **8→7** 项（现表含 story-arc 共 8 项，去 anti-ai），jump 映射去 anti-ai 节点；`useOnboarding` 的 SETTINGS_TYPES 与工作台「设定 x/8」硬编码同步 8→7。
- 删除：AntiAiSettingForm.tsx、settings/router.py 的 `POST /anti-ai/words` 端点与通用 `/settings/anti-ai` 读写端点（机器写入收进文风侧服务端函数）、anti-ai.yaml.template 及 `filesystem/init.py` 的种子条目、`prompts/settings_anti_ai.prompt` 死文件、genres/presets.py 的 `fatigueWords` 死数据（全仓零消费方）、readiness 的 `_check_anti_ai`。anti-ai KV 的存储路由映射原样保留（迁移读＋导出/导入兜底＋回滚安全，见 design D3）。
- 题材蓝图不再携带疲劳词概念（presets 死数据清除后， genres 管线无 fatigue 字样）。

## Capabilities

### New Capabilities

- `style-banned-words`: 禁用词与句式规则作为文风硬约束子区的契约——数据落 writing-style KV（banned_words/tic_patterns）、硬约束三块结构与上限、存量 anti-ai.yaml 一次性迁移与 `_legacy` 留底、蒸馏并入目标、提示词注入与程序化体检单源、设定页不再有独立禁用词句面板。

### Modified Capabilities

- `intro-genre-settings`: 左栏设定菜单序与「确认即前进」推进顺序——08 禁用词句退役，末项改为 07 伏笔；后端 READINESS_CHECKERS 同序同口径。
- `readiness`: 内容检查 **8→7** 项（现表含 story-arc 共 8 项，去 anti-ai）；missing 文案与 jump 映射去除 anti-ai 节点；顺带修 readiness 基线 spec 的 story-arc 计数漂移。
- `style-quant`: 蒸馏 commit 的禁用词服务端 append 目标由 anti-ai 面板改为文风 KV `banned_words`（去重语义不变）。⚠️ 依赖 style-settings-v2 先归档（其 spec 为本 capability 基线，当前尚未 sync）。
- `prompt-crafting`: 「禁止使用以下词汇／句式」段数据源单源化为文风 KV；素材包要求中「通用反模式由禁用词句面板承接」改为由文风硬约束子区承接。

> design-system 不立 delta：本变更零新增词表/组件形态（复用 fblock/Cfg/ListEditor/sub-block 既有词汇），设定页菜单减项的契约归 intro-genre-settings；原型与 parity 基线更新属设计工件流程，见 Impact 与 tasks。

## Impact

- **C端后端** `client/backend`：`settings/style_model.py`（normalize/put 扩两键＋tic_patterns 专用 dict 归一＋fatigue_words 并入剥离＋NFKC 归一＋append_banned_words 改目标）；统一迁移感知读路径（chapter_writer/quality/auxiliary/ai_router 共用）；`write/chapter_writer.py`（注入单源＋删幽灵合并）；`write/quality.py`、`write/auxiliary.py`（改读文风 KV）；`settings/ai_router.py`（蒸馏 commit 改目标＋AI 体检改读）；`settings/router.py`（/anti-ai/words 删除＋通用 /settings/anti-ai 退役分支）；`workflow/readiness.py`（_check_anti_ai 删除、检查表 8→7）；`filesystem/paths.py`（anti-ai 映射保留不动）；`filesystem/init.py`（种子条目删除）；`prompts/settings_anti_ai.prompt`（死文件删除）；`reference/anti-ai.yaml.template` 删除、`reference/writing-style.yaml.template`（删 fatigue_words 幽灵键、预填 banned_words 37 词＋tic_patterns 8 条）；`genres/presets.py`（fatigueWords 清除）。测试矩阵：style v2 存量用例改写＋迁移/单源/体检/回读合并新增约 20 例。
- **C端前端** `client/frontend`：`AntiAiSettingForm.tsx` 删除；`StyleSettingForm.tsx` 硬约束区扩三块（禁用词 ListEditor maxLength 50＋TicPatternEditor 搬入接 maxItems 20/补 data-od-id；style GET/PUT 内联读写扩两键——styleApi.ts 现仅量化/蒸馏端点不动）；commit 后回读合并两键＋脏快照同步；`SettingsView.tsx`（anti-ai 页签注册/面板渲染/normalizePanel 映射改指 style/AI 体检锚与 footNote/「AI痕迹控制」死文案删除）；`useOnboarding.ts`（SETTINGS_TYPES 8→7）；`NovelWorkspace.tsx`（「设定 x/8」硬编码）；e2e：`settings-forms.spec.ts`（anti-ai 段改写）、`creation-flow.spec.ts`（/settings/anti-ai 注入与 8 键 status 循环改 7 键）、`design-parity-book.spec.ts`（stub 键＋基线重录）、`foreshadow-settings.spec.ts`（注释随手改）；`workbench-features.spec.ts`/`style-quant.spec.ts` 仅回归不改写；vitest：`NovelWorkspace.test.tsx`（「禁用词句」断言锚）、`useOnboarding.test.tsx`（键数/文案）、`StyleSettingForm.fewShots.test.tsx`（PUT body 键断言 4→6）。
- **设计工件**：三个原型文件先改＋ADJUSTMENTS 逐文件登记——`prototypes/book.html`（antiAI 注册/nav/desc/疲劳词渲染器）、`prototypes/style-settings.html`（11 处 anti 引用：稿头注记/硬约束 hint/锚定体检/lexicon note/AI 体检）、`prototypes/foreshadow-settings.html`（nav 项/hookOkNote/toast 与新推进序矛盾）；settings parity CASE 现仅覆盖左栏＋默认简介面板，评估为文风面板新增 parity CASE；parity 基线重生成。
- **归档顺序依赖**：style-settings-v2（已完成未归档）需先归档 sync，本 change 的 style-quant delta 才有基线可对。
- **迁移**：无 schema 变更（KV 内部）；导出全树打包自动带新键（免升 FORMAT_VERSION）；存量书在任一禁用词取用点（文风面板读写/写章组装/体检）经统一迁移感知读路径完成 anti-ai→文风迁移，anti-ai 原键保留（回滚安全）。

## Design Impact

- 受影响端：**仅 C端**（S端无此域）。
- 受影响屏/弹层：设定页三栏——左栏菜单（8→7 项）；右栏文风面板（硬约束区扩容：禁用词块＋句式规则块）；原禁用词句中/右栏整体退役。无新弹层。
- 对象状态：沿用 settings-v 页签词表（ptabs/ptab）与 fblock/fb-head 家族、Cfg sum 位、ListEditor（含上移/计数）；句式规则块沿用 sub-block/sub-row.tics 既有词汇，不新增组件形态与状态档位；文案遵循 design-language §13（按钮动词、无内部术语）。
- 是否触碰两端共享段：**否**（纯页面级类名与既有组件；若实现需新增类名，走 design-system 词表登记，不动 base.css）。
- 是否需要原型先行：**需要**——设定页原型含文风卡部分先改＋ADJUSTMENTS 登记每处偏差，再动实现。
- 设计工件产出方：实现侧自查（有 style-settings-v2 原型与词表先例，改动局部）。
