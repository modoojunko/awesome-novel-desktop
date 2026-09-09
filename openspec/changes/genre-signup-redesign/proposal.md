## Why

建书后设定面板的题材项太多、作家无从下手；简介「怎么写」缺乏引导，写完又拿不到体检反馈；AI 辅助反馈全堆在右栏、把右栏拉得很高；免费版用户在 AI 入口感知不到边界。创建期第一步「简介」、第二步「题材」的设定体验需要重设计。

## What Changes

- **创建期前两步重排**：SETTINGS_ITEMS 前两步定为 **① 简介 → ② 题材**（当前顺序是题材在前、简介在后，需对调），确认一步自动进下一步、可跳过可回改。
- **简介面板改造**：编辑框直接写（≤500 字，计数+徽标）＋「怎么写」六段模板**折叠文本指导**（默认收起、点开展开：主角身份/本来的生活/突发状况/必须面对的矛盾/不做的后果/做了的可能结局）＋右栏「AI 写作助手」卡片（PRO 徽标并头部）＝体检（六段逐项查+禁忌扫描）/ 补缺失 / 润色三个并列能力，**反馈统一落到简介框下方结果区**（采纳才写回）。
- **题材面板改造**：六格（口味胶囊/主要看什么/绝对禁止/吃苦指数滑块/主线战场/剧情轨道，每格编号+怎么填+成书视角去处）＋右栏「AI 写作助手」五行（对应 02-06 各字段，各答各题），**反馈落到左侧对应字段输入框下方**（采纳才写回对应控件）。题材定义收口：题材 = 读者预期 + 作者轨道 + 核心冲突的类型锁。
- **免费版门控**：AI 写作助手卡片对无套餐用户**可见 + 锁定**（降透明 + 锁徽 + 收益描述），点击给统一升级提示；免费版写作能力完整（人工路径零差异）。
- **数据契约**：简介 `{ synopsis: ≤500 }`；题材 **纯新契约**（推翻 genre_id）`{ core_promise(enum|custom), promise_note?, forbidden_list[](tagId|custom), cost_ratio(1-10), battlefield[], track? }`；`readiness._check_genre` 判据改新契约核心键非空；AI 字段说明与六段名/禁忌三元注册**共享常量模块**单源（`fieldGuide` 本仓库不存在，不依赖）。
- **AI 助手实现（本 change 内落地）**：简介体检/补缺失/润色 + 题材五行由 **C端后端** `settings/ai_router.py` 承载——扩展（`FIELD_GENERATABLE` 加 `genre`、新增 `settings/intro/{action}` 子路由），新增 `settings_intro_{action}`/`settings_genre_{field}` prompt 模板；前端 `lib/ai.ts` 新增 `introAi`/`genreAi` 封装。非 S端、不引入独立服务。无 C端用户、无迁移事项（题材改 4 张关系表，旧 KV 行废弃、存量库指纹不匹配→留档重建）。
- **本书模型设定（AI 前置）**：**用 AI 前必须先给本书选模型**。模型配置是**人工路径能力，不锁会员**——免费版也能看、也能配（配好升级 PRO 后直接可用），免费版与会员的差别**只在右侧 AI 助手全灰**。**复用已存在的 `ModelSettingForm`**（`SettingsView` 已渲染 `ai-model` 面板；不新建模型项、不进 `SETTINGS_ITEMS`），选择控件改为**按 API 配置分组的卡片列表**（多供应商 × 多模型、radiogroup 语义、选择与生效分离加确认键）。未设本书模型的（会员），该书 AI 能力不可用：AI 行提示「先在本书选择模型」+ 跳转；后端 `require_novel_model` 前置校验，未设返回 503 `missing_model`。**AI 端点全仓库统一走 `get_ai_client_for_novel`**（实测 14 处（替换 12 + 豁免 2），含章纲起草/提示词润色/归档摘要；建书预填豁免），`project.ai_model` 为唯一权威模型源。

- **实体命名统一（本 change 包含）**：DB 表 `projects`→`novels`、列 `project_id`→`novel_id`、后端 URI `/api/v1/projects/*`→`/api/v1/novels/*`、前端残留同批改——一物三名已收敛两处（类名 `Novel`、路由 `/novels`），表名是唯一残留；Change C D1 原判「不动」的前提（已分发数据）已因「无 C 端用户」失效。
- **题材完全关系化**：推翻 KV JSON，改 4 张关系表（`genre_vocab` + `novel_genre` + 两张关联表）——候选源需稳定 slug 主键（原 index 编号会随常量顺序漂移致数据损坏）、列表需外键、约束应由 DB 保证；**对外 API 契约不变**（五字段 JSON）。

## Capabilities

### New Capabilities
- `intro-genre-settings`: 创建期前两步（① 简介 → ② 题材）的设定面板——简介六段模板引导 + AI 写作助手（三能力/五行）+ AI 反馈落输入框下方 + 免费版锁定 + 简介/题材字段数据契约。

### Modified Capabilities
- `design-system`: 新增「AI 写作助手」卡片与 `.ai-sink` 结果区两个组件词汇，并复用 §11「可见 + 锁定」的会员门控锁定态（降透明 + 锁徽 + 收益描述）——作为组件/状态语言的增量定义。

## Design Impact

- **受影响端**：C端（`client/frontend`）＋ C端后端（`client/backend`）。S端 无改动。
- **受影响屏/弹层**：工作台「设定」视图的**简介面板、题材面板**、右栏「AI 写作助手」卡片、简介框下方 / 题材对应字段下方的**.ai-sink 结果区**；C端后端 `settings/ai_router.py`（扩 genre + 新增 intro 子路由）、`prompts/settings_intro_*`/`settings_genre_*` 模板、`readiness._check_genre`。
- **对象状态**（对照 design-language §5.1）：简介/题材 未填（ghost 徽标）→ 进行中/草稿（warn 软底，改「已填」语义）→ 已确认（ok 绿）；免费版 AI 能力走 §11 锁定态（可见 + 降透明 + 锁徽 + 收益描述）。**明确修正**：现「已填」误用 ok 绿 —— 应为「进行中」warn。题材确认判据由 genre_id 改为新契约核心键非空。
- **是否触碰两端共享段**：否（仅 C端 UI + C端后端 AI，不触碰 `base.css` 共享令牌/组件类；`.rail-assist`/`.ai-sink` 为 C端局部组件类，只复用共享令牌）。
- **是否需要原型先行**：是——C端 需新增/更新 `docs/design-c/prototypes/`（当前评审稿在 `drafts/genre-signup-draft.html` v8.5，收编后转正）并在 `ADJUSTMENTS.md` 登记偏差。
- **设计工件产出**：设计侧会话（PM 设计稿 + 评审稿已定稿（v8.5，待用户最终拍板），转正为原型）。

## Impact

- 前端：`client/frontend/src/components/novel/workbench/SettingsView.tsx`（SETTINGS_ITEMS 前两步重排、确认即前进、简介/题材面板接线）、简介面板（六段折叠）、题材面板（六格 + AI 五行）、`.ai-sink` 结果区组件、`AiWriterAssistant` 卡片、`lib/ai.ts`（新增 `introAi`/`genreAi`）。
- 后端：`client/backend/settings/ai_router.py`（扩 `FIELD_GENERATABLE` 加 genre + 新增 `/settings/intro/{action}` 子路由）、`prompts/settings_intro_{action}`/`settings_genre_{field}` 模板、`client/backend/workflow/readiness.py`（`_check_genre` 判据改新契约）、`genre_vocab` 表 + `genres/vocab_presets.py`（候选源字典，**不复用 presets 现成键**）。
- 契约：简介/题材 payload 键控（纯新契约，无 genre_id）；`GenrePickerModal`/`data/genres.ts`/`DEFAULT_GENRE_ID` 随纯新契约弃用或改造。
- 免费版：AI 入口可见 + 锁定（前端 `useFeature('settings-ai-fields')` + 后端 `require_ai_access`）。
- 设计系统：新增组件词汇（design-system spec 增量）；无共享段改动。
