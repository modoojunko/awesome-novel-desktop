## Context

现状：`SettingsView.tsx` 的 `SETTINGS_ITEMS` 现为 `[genre, intro]`（题材在前）；简介是 `SettingsView.tsx` 内联的 `IntroPanel`（`:384-462`），题材是 `components/novel/settings/GenreSettingForm.tsx`。AI 辅助现有字段行内「AI 帮我填」就地给出建议。**C端 AI 能力由 `client/backend/` 承载**：`settings/ai_router.py` 提供 `POST /api/novels/{id}/settings/ai/{stype}/{field}`（`FIELD_GENERATABLE={world,style,hooks,characters}`），走 `prompts/settings_*.prompt` + `AIClient.chat`；**目前没有 intro/genre，也没有对应 prompt 模板**。设计稿 `docs/design-c/drafts/genre-signup-draft.html` v8.5 已定稿（v8.5，待用户最终拍板）（含简介/题材两窗 + AI 写作助手 + 免费版锁定）。本次把设计落进 C端 工作台「设定」视图，并把简介/题材 AI 接进 C端后端这条 AI 链路。**用户拍板：AI 助手实现补进本 change；题材数据契约推翻 genre_id、改用纯新契约。**

## Goals / Non-Goals

**Goals:**
- SETTINGS_ITEMS 前两步重排为 ① 简介 → ② 题材；确认自动进下一步、可跳过可回改。
- 简介面板：六段模板折叠引导 + AI 写作助手（体检/补缺失/润色）+ 反馈落简介框下方 `.ai-sink`；「已填」徽标改进行中 warn 语义。
- 题材面板：六格 + 五行 AI 写作助手 + 反馈落各字段下方 `.ai-sink`；题材定义措辞收口。
- AI 写作助手对免费版可见 + 锁定；简介/题材字段契约与**共享常量单源**（`fieldGuide` 本仓库不存在，属待建）。**AI 助手实现（后端端点扩展 + prompt 模板 + 前端调用）在本 change 内落地。**
- **题材契约：推翻 genre_id，纯新契约（五字段），readiness 判据同步改。**

**Non-Goals:**
- 不改 S端（纯 C端 + C端后端）。
- 不实现世界/开场主角(含金手指)/主线面板（留档后续 change）。
- 不改写作期工具（伏笔/风格/AI痕迹）定位。
- **保存链路不改**——简介 `PUT /settings/story`、题材 `PUT /settings/genre` 沿用；**AI 生成链路必须扩展** `settings/ai_router.py`（新增 intro/genre），否则「AI 写作助手」无后端可调。

## Decisions

**D1. SETTINGS_ITEMS 顺序与流程——改数组 + 补「确认即前进」。**
现数组 `[genre, intro]` 对调为 `[intro, genre]`（简介在前）。**现状"确认后只 toast、从不 setPanel 到下一步"——需补：确认后切到下一未确认项**（`setPanel` + 自动前进），并默认 `initialPanel="intro"`。替代（新写 flow 状态机）被否——现有 `handleFootAction` 的 save 分发按 panel 值 switch、非数组下标，重排不破坏，仅需加自动前进一步。

**D2. 简介面板结构——把 `SettingsView` 内联的 `IntroPanel` 升级为 编辑框 + 六段模板 + AI 助手三块。**
六段模板做成可折叠（`<details>`/受控 state）文本指导，默认收起；数据仍为 synopsis ≤500。AI 助手独立成 `AiWriterAssistant` 组件（与题材复用）。替代（六段拆成字段表单）被否——用户已裁定"模板只作引导、不代写"，写作仍集中在一个编辑器。

**D3. AI 结果区 `.ai-sink`——单一 TintPanel 组件，反馈落输入框下方。**
新增 `AiSink` 组件（fg-soft、操作名标签 + 候选 + 采纳/重试），简介框下方一处、题材各字段下方各一处（按 key 路由）。替代（右栏内嵌答案）被否——用户裁定反馈堆右栏把右栏拉高、要落在输入框下方。右栏只作按钮清单。

**D4. 免费版锁定——复用既有 `useTier`/`useFeature` + §11 门控。**
AI 卡片 `locked` 态由 `useFeature('settings-ai-fields')`（已有会员门控 key，替代不存在的 `ai-assistant`）派生；锁定＝整卡降透明 `.locked` + 徽标转灰 + 行 `not-allowed`，点击走统一升级 toast，不各自弹窗。替代（隐藏入口）被否——规范 §11 首选「可见 + 锁定」。后端 `require_ai_access` 已对会员 + API Key 双验，前端锁定与之对齐（避免「前端解锁、后端 403」）。
- **AI 行点击＝统一门控函数**（`AiWriterAssistant` 内一处判定，**只读 D13 的 `ai_state`、一次分派**——不再 `useFeature` + `ai_state` 两处判）：
  1. `member_required`（免费/过期）→ 升级 toast——**门控只作用于 AI 助手行，不拦模型配置本身（免费版可选模型）**
  2. `missing_model`/`invalid` → 「先给本书选模型」→ `onJumpModel()`（= `SettingsView.setPanel('aiModel')`）
  3. `no_key` → 「先去「模型配置」加 Key」→ 跳模型配置
  4. `ready` → 调 `introAi`/`genreAi`
- **门控顺序统一**：前端 gate **按 D10 的 `ai_state` 分派**（不再用本地四态推导），错误分派顺序统一为 `member_required → no_key → missing_model`（消除 D8 与本节两套写法）。
- **模型步可见性不随 tier**：模型配置是**人工路径能力，免费版也能看、也能配**（§11「免费＝人工路径完整」）；免费版与 PRO/MAX 的差别**只在右侧 AI 助手**（免费版全灰 + 升级引导）。配好的模型在升级 PRO 后直接可用，不必重配。模型步不进 `SETTINGS_ITEMS`/readiness/「确认即前进」。
- **模型窗＝复用既有 `aiModel` 工具项**：`SettingsView` 已渲染 `<ModelSettingForm settingKey="ai-model" />`（不进 `SETTINGS_ITEMS`、恒 done、不参与 readiness/「确认即前进」）。**不新建模型项、不重复接入**；本 change 的增量是「未选模型时冻结 AI 入口 + 提示 + 跳转」。
- **模型窗交互：选择与生效分离（加确认键）**。真实 `ModelSettingForm` 现在是「`<select>` onChange 即 `selectModel` 落库、无确认键」——本 change **改为**：点模型行只标亮选中态（不落库），点「设为本书模型」才落库（未选时按钮禁用、确认后回禁用）。**需同步改真实组件**（从 onChange 即存改为选中态 + 确认保存），否则评审稿与实现不一致。理由：卡片行比下拉更易误触，而该设置决定全书 AI 走哪个模型、影响面大。模型窗不参与「确认即前进」序列（`handleFootAction` 自动前进须跳过非 `SETTINGS_ITEMS` 项）。
- **确认键连带：draft + 脏状态链路**。`ModelSettingForm` 须持 draft（`cid::model`）+ dirty 判定并接 `onDirtyChange`（现 `SettingsView` 只传 `projectId`/`settingKey`——点了行未确认就切面板会**静默丢失**、无「未保存」提示）；确认成功后 `refresh()` 重取或补 `setCurrentConfigName`（`useModelStatus.selectModel` 现不更新 configName → 「当前状态」显示旧配置名）。
- **组头连接状态徽标的数据源**：状态在 `ApiConfig.last_test_status`（`ok/auth_error/timeout/network_error/rate_limited/unknown/untested`），而 `useModelStatus` 现只返回 `modelOptions`（不含状态）——须扩展其返回值或组件内合并 `useApiConfigs().configs`，并做 `last_test_status → 已连接/未测试/失败` 映射。
- **模型选择控件＝分组卡片列表（替代原生 `<select>`）**：按 API 配置分组（组头＝配置名 + 供应商 + 连接状态徽标），组内为该配置下的模型行（可点、单选、选中态 accent + 勾），支持**多供应商 × 多模型**；原生 `<select>` 的 optgroup 既撑不住多供应商×多模型的可读性，也不符合全页设计语言（卡片/列表行/胶囊）。**单选语义用 `role="radiogroup"` + `role="radio"`/`aria-checked`（对齐仓库既有 `StoryArcForm` 的 role/aria 语义；注意它**没有键盘导航先例**、且是「再点取消」的 toggle 语义——模型单选**不可**照抄）**；**键盘导航需新增**：roving `tabindex`（选中行 `0`、其余 `-1`）+ `ArrowUp/Down/Left/Right` + `Home/End`。数据源＝`useModelStatus` 的 `modelOptions: FlatModelOption[]`（含 `api_config_id`/`config_name`/`vendor`/`model`），按 `api_config_id` 分组渲染。**空态**：`modelOptions` 为空（有 Key 但未拉到模型）时给「去「模型配置」补模型」引导，不空白。
- **免费版「已配好但 AI 仍灰」的文案**：模型窗对 configured 的免费用户须提示「模型已配好 · 升级 PRO 后本书 AI 即可用」，不得说「本书 AI 就绪」（与右侧灰卡矛盾）。
- **`ai-model` 登记簿语义**：`features.ts` 现 `"ai-model": { memberOnly: true }`（含 `features.test.ts` 断言）与「模型配置＝人工路径、免费版也能配」冲突——须改 `memberOnly: false` + 单测同步移入 FREE_FEATURES，并注明属登记簿语义变更。
- **模型窗的可见性**：模型步对**所有用户可见可用**（免费版也能配，配好升级后直接用）；模型步的右栏卡不绑 `.locked`（配置不是被锁的会员能力）。只有简介/题材的 `AiWriterAssistant` 卡绑 `useFeature`（免费版全灰）。

**D5. 数据契约——纯新契约（推翻 genre_id），字段说明与六段名/禁忌三元共享常量单源。**
- 简介 `{ synopsis: ≤500 }`（`PUT /settings/story`）。
- 题材**纯新契约** `{ core_promise(enum|custom), promise_note?, forbidden_list[](tagId|custom), cost_ratio(1-10), battlefield[], track? }`（`PUT /settings/genre`——`settings/genre.yaml`）。**无 genre_id**。
- **推翻 genre_id 的连带处置**（关键）：老 `GenreSettingForm` 落盘的 `genre_id + config_overrides(fulfillment_types/chapter_types/pacing_rules/fatigue_words) + selected_arc_id + prompt_injection_enabled + taboos` 这批**写作引擎题材配置**，在纯新契约下没有落点。选择：**迁移为新契约字段**（fulfillment_types→core_promise 语义、taboos→forbidden_list、typicalArc/storyArcTemplates→track）或**显式移除并评估**（`prompt_injection_enabled`/`selected_arc_id` 随 GenrePicker 退役）。**无 C端用户、无迁移**，倾向迁移语义相近的、移除纯写作引擎用不到的；实现时在 `tasks 6.6` 逐项定去留，不得静默丢弃影响写作引擎 AI 口味/节奏/注入的配置。
- **readiness 判据**：`_check_genre` 由「genre_id 非空」改为「新契约核心键非空（`core_promise`/`forbidden_list`/`cost_ratio`/`battlefield`/`track` 至少一非空；**口味胶囊(01)不计入**，避免恒为真）」。
- **六格 ↔ 字段 ↔ 契约映射**（写死，避免实现错位）：02 主要看什么 ↔ `core_promise`(enum|custom)+`promise_note`(仅入契约、不单独成 AI 行)；03 绝对禁止 ↔ `forbidden_list`；04 吃苦指数 ↔ `cost_ratio`；05 主线战场 ↔ `battlefield`；06 剧情轨道 ↔ `track`；01 口味胶囊=预置联动、不走 AI、不计入判据。
- **枚举/标签候选来源**：`presets.py` 无这些新键与 tagId，需**新建一份 5 口味联动 + 候选源枚举**（core_promise 枚举值、forbidden_list tagId 目录、battlefield 候选清单），供 AI 从候选选或走 custom、前端映射 tagId；不复用 presets 现成键（仅萃取其语义作初稿）。
- AI 字段说明、**六段名与禁忌三元** SHALL 注册进**共享常量模块**（前后端与 prompt 共用；`fieldGuide`/`settings-ai-qa` 本仓库不存在，属待建——本 change 不依赖未建系统），prompt 模板与前端渲染共用，避免 AI 返回段名与前端错位。

**D6. 原型先行——评审稿转正。**
设计稿在 `drafts/genre-signup-draft.html`（v8.5）。按硬性流程，需纳入 `docs/design-c/prototypes/` 对应屏并在 `ADJUSTMENTS.md` 登记偏差，再走 `design:check`。

**D7. AI 助手实现路径——扩展 C端后端 `settings/ai_router.py`，不新开独立服务。**
- **AI 前置：本书必须先选模型**。模型配置是**人工路径能力，免费版也能看、也能配**（§11）；免费版与 PRO/MAX 的差别**只在右侧 AI 助手**（免费版全灰）。配好的模型升级 PRO 后直接可用。数据模型已有 `project.ai_config_id` + `project.ai_model`，前端已有 `ModelSettingForm.tsx` / `useModelStatus(projectId)`（`GET/PUT /novels/{id}/ai-model`；**现状**前端自行推导 no_key/no_model/configured/invalid 四态，**D10 后改为消费后端下发的 `ai_state`**）——**复用，不新建**（选择控件形态见 D4：分组卡片列表，非原生 select）。模型步**不进 `SETTINGS_ITEMS`**（不参与 readiness/设定完成度、不占「确认即前进」序列），是 AI 前置引导步（PRO/MAX 用 AI 的第①步；免费版可先配好）。
- **模型前置做成独立 dependency `require_novel_model(project_id, user, db)`**（不内联在 `require_ai_access` 里）：职责分离（它需 path 的 project_id + 读 `Novel`，而 `require_ai_access` 只读 user）、多端点复用（write/router、write/auxiliary、settings/ai_router）、便于单测。端点同时挂 `Depends(require_ai_access)` + `Depends(require_novel_model)`（会员在前、模型在后）。**判据收紧：`not ai_config_id or not ai_model`（两者均须非空）**——只判 `ai_config_id` 会让 `ai_model` 为空时落到 ApiConfig 默认模型，语义不符。
- **三种前置的 status/reason 必须可分流**（否则前端无法分辨去配 Key 还是去选模型）：
  - 会员不足 → `403 detail={reason:"member_required", message}`（现有）
  - 会员但无可用 Key（含 invalid）→ **保持 503**（前端 `lib/api.ts` 已有 503 全局提示链路 `notify503`，不可改成 403）+ 补 `detail={reason:"no_key", message:"先去「模型配置」添加 API Key"}`；前端 503 提示须按 `reason` 分流（`no_key`/`missing_model` 不进 infra 全局提示）。注：`invalid` 是**前端派生态**（config_id 在但列表里找不到该配置），后端无此概念，按 `no_key`/`missing_model` 兜底。
  - 会员 + 有 Key + 本书未选模型 → `503 detail={reason:"missing_model", message:"先在本书选择模型"}`；此 503 语义为「前置未满足、**不可当瞬时故障重试**」，前端直接引导。
- **结构化 detail 全链路归一化（P1）**：`api.ts` 503 分支现只认 `typeof detail === "string"`（对象 detail → `detail=""` → 误弹 infra「服务暂不可用」）；通用分支只透传 `member_required` 的 reason。须：`api.ts` 按 `detail.reason` 分流 + 透传 `e.reason`；`ai.ts` 两处 fetch（`doStreamFetch`/`doJsonPost`）统一取 `detail.message`（否则对象 detail 变 `[object Object]`）。
- **写作页兜底（已定）**：本 change 把章写作/润色/章纲也纳入「未选模型→503」，但**兜底文案只保证设置视图 AI 行**；写作页撞 `missing_model` 的文案与跳转**另立 change**（本 change 不阻塞）。
- **`get_ai_client_for_novel(novel_id)` 落地**：现 C端 AI 端点用全局 `get_ai_client()`，未走本书模型——需实现它（读本书 `ai_config_id`+`ai_model` 构造 `AIClient`；`chat(model="haiku")` 经 `resolve()` 落到本书模型，**无需在 chat 里传字面模型名**）。**全仓库 `get_ai_client()` 调用点逐一替换 + 挂 `require_novel_model`（实测 14 处，含豁免）**：`write/router.py:62,179`、`write/auxiliary.py:157,217,252`、`settings/ai_router.py:50`、`chapters/ai_draft.py:259`、`prompt/router.py:46`、`archive/service.py:46`、**`story/arc_wizard.py:61`（主线 AI 向导）、`story/character_agent.py:250`（角色 agent）、`story/engine.py:201`（剧情推演）**——后三处有 project 上下文，按 D12「全书共用」须纳入。**豁免**：`ai_prefill.py:26`（建书预填，早于选模型）与 **`novels/router.py:154`（`/suggest-meta`，无 project_id、建书期）**。按字面只改 6 处会让多个端点绕过本书模型与 503 前置。**门禁见 D11 边界禁令（含可执行命令与豁免清单）。**
- **双模型源权威链（P1）**：写章链路 **7 处**读 `writing_model`（`write/router.py:64,180`、`write/auxiliary.py:69,153,212,247`、`chapters/ai_draft.py:260`；**默认 `"haiku"`**），而 `resolve()` 只映射 `haiku/sonnet/review`、**字面模型名原样透传**——若 `writing_model` 写成具体模型名会**静默绕过 `project.ai_model`**。权威链定死：**`project.ai_model` 为唯一权威**；`writing_model` 仅允许 `haiku/sonnet` 别名（经 `resolve()` 映射），显式模型名一律忽略（或停用该字段）。
- **`polish_text`/`expand_text`/`archive_chapter` 需补 `project_id` 参数**：三者签名现只有 `root_path/chapter_ref/...`，拿不到 project_id，不能机械替换 `get_ai_client()`——须新增参数并向上游（`write/router.py`、`archive/router.py`）透传；`stream_continue` 已可用 `project`。**另**：`archive/service.py:44` 内联 `check_permission().is_member` 属**业务层自判会员**（违禁令③）——须改由 dependency 前置或显式豁免（若存在非请求内调用路径）。
- **usage 记实际模型 id**：走本书模型后 `record_usage` 仍记 `model="haiku"`（`settings/ai_router.py:71`、`write/auxiliary.py:215/250`）→ 审计/计费失真，须记**实际本书模型 id**。
- **构造失败兜底**：`ai_config_id` 指向的配置已删/解密失败/`api_format` 异常时，优雅返回 503 `reason=missing_model` 或 500 带 detail，不裸 500。
- **结构化输出策略（P1，跨供应商/弱模型）**：模型窗把本地 `qwen3:32b`、`gpt-4o-mini` 与旗舰并列，而体检/题材全靠 JSON 解析——除 endpoint 后置归一化外，prompt 侧须：模板内给 **schema + 枚举 + 一个 few-shot 示例**；能用的 provider 追加 `response_format={"type":"json_object"}`（需同步扩 `AIClient.chat` 的 OpenAI 分支）；不支持的走归一化兜底。
- **行为收窄提示**：把章写作/润色/章纲从「全局 Key 正常用」变为「必须本书选模型否则 503」是硬性收窄；虽无 C端用户，但 e2e/开发数据里未配模型的书会全部 503——相关 e2e 的 seed 须给书配模型。
- **路由注册顺序（关键）**：新增的 `POST /.../settings/ai/intro/{action}` 是 3 段路径，会被既有 `/{stype}/{field}` 通用路由以 `stype=intro, field=introspect` 抢先匹配（`intro ∉ FIELD_GENERATABLE` → 400）。**intro 子路由必须注册在 `/{stype}/{field}` 之前**（仓库 `main.py` 已有同类的「先注册 /settings/status 防被 /{type} 抢先」先例）；或改用不冲突路径（如 `/settings/ai-intro/{action}`）。实现时在 `tasks 6.1` 明示。
- **简介三能力是「动作」**：`POST /api/novels/{id}/settings/ai/intro/{action}`，`action ∈ {introspect, fill, polish}`，各配 `settings_intro_{action}.prompt`。入参统一 `body.content`（当前编辑 synopsis）+ `body.title`（书名，前端必须传，见 D8）。
  - `introspect`（体检/诊断，非生成）：返回 `{"six_segments":[{name,status(ok|missing),excerpt,note?}], "taboo":{"hits":[{rule,excerpts}]}, "title_check":{"fit":"ok|mismatch|generic","note","suggestions"[≤3,≤16字]}, "verdict":"strong|ok|weak"}`；`name`=六段名、`status`∈{ok,missing}、禁忌规则∈{设定集腔,作者自白,剧透}（与别踩统一「作者自白」）；**标题对照**（D21）= 书名与简介是否互相印证，`mismatch`/`generic` 给理由与候选标题，非法/缺失一律不下发；**只分析/只提醒、不补写不改写、不替用户重写整段**。
  - `fill`（补缺失）：入参 `{title, content, missing_segments:[六段名]}`（前端把 introspect 的 missing 段传来），返回 `{"missing":[{name,candidate}], "act":"insert"}`；**只补缺失段、绝不改动作者已写段、不重写整段**。
  - `polish`（润色）：入参 `{title, content}`，返回 `{"original","polished","act":"replace"}`；保原意、只加工不代写；`max_tokens` 上调（前后对照）。
- **题材五行是「字段」**：走既有 `{stype}/{field}` 通道，`FIELD_GENERATABLE` 加 `genre`，`field ∈ {core_promise, forbidden_list, cost_ratio, battlefield, track}`（**promise_note 不设独立 AI 行**）；prompt 用 `settings_genre_{field}.prompt`（**按 field 拼接，仅 genre 特判 field 级；world/style/hooks/characters 仍保持 `settings_{stype}.prompt`，勿误断**——否则会加载不存在的 `settings_genre.prompt`）。按字段**强类型出参**：cost_ratio→1-10 数值、forbidden_list→[{tagId|text}]、battlefield→数组、core_promise→{value:enum|custom, note:读者预期句}、track→文本。
- **题材端点 synopsis 来源统一**：题材五行生成也要能反映当前简介草稿——`synopsis` 取自 `body.content`（前端一并传，与简介一致），而非仅读 story.yaml 旧文。
- **usage 细分**：`record_usage` 的 `operation` 改为 `settings_{stype}_{action|field}`。
- **错误契约**：区分 未配 key(403/带 detail)/AI 返回非法 JSON(502 可重试，不拦确认)/prompt 参数错(400)；补缺失/润色失败允许重试。新端点挂 `require_ai_access`（与既有 ai_router 一致）。

**D8. 前端 AI 调用——`lib/ai.ts` 封装。**
新增 `introAi(action, {title, content}, projectId)` 与 `genreAi(field, {title, synopsis, context}, projectId)` 统一入口（按 stype/action/field 选 URL + 解析强类型响应），在此集中 try/catch、Pro/未配模型/JSON 失败兜底，供 `AiWriterAssistant` + `.ai-sink` 复用；采纳/重试在 `.ai-sink` 内交互，写回调由所在面板状态持有（简介在 IntroPanel、题材在 GenrePanel）。
- **`title` 来源钉死**：前端无现成「按 projectId 取书名」helper——`title` 取自 workspace/novel 状态里的 `novel.name`（或新增 `api.fetchNovel(projectId)` 返回 `name`）；`IntroPanel`/`GenrePanel` 只持 projectId，故由 SettingsView 传入或 lib 内取，保证与 D7 入参一致。
- **前置预检 + 错误兜底双保险**：UI 层先 gate（见 D4 门控），lib 层 catch 后端错误再兜底——**按 `detail.reason` 分派**，不得一色 toast：
  - `member_required` → 升级提示（沿用现有会员拦截）
  - `no_key` → 「先去「模型配置」添加 API Key」→ 跳模型配置
  - `missing_model` → 「先在本书选择模型」→ 跳本书模型设定
  - 非法 JSON/502 → 「暂不可用，请重试」，**不拦确认**
  分派顺序 `member_required → no_key → missing_model`，避免免费用户先撞到「未选模型」而误导。

**D9. 候选来源与 5 口味联动。**
新增一份 5 口味联动数据（每口味→对各核心键的预填值）与候选源：`core_promise` 枚举值、`forbidden_list` tagId 目录、`battlefield` 候选清单（现 `presets.py`/`genres.ts` 无这些新键，仅可萃取语义作初稿）。这些作为 C端前后端共享常量/单源（共享常量模块；`fieldGuide` 本仓库不存在），供题材 AI 候选注入与前端「采纳写回并映射 tagId」。

**D10. AI 就绪状态＝后端单一事实源（用设计消解「识别」问题）。**

**病根**（复审暴露的同一类问题＝同一件事多个事实源）：
- 前端 `useModelStatus` 用本地 `configs` **自己推导**四态（`hasKeys`/`currentConfigId`/`configs.find`），后端 `require_novel_model` 另有判据（`not ai_config_id or not ai_model`）——两处口径会漂移（config_id 有值但 model 空 → 前端放行、后端 503）。
- `invalid`（配置已删）只有前端能判、后端无此概念。
- 错误表示两套（裸字符串 503 vs 结构化 `detail`）。
- 模型源两个（`project.ai_model` vs `writing_model`）——「该用哪个模型」也是多处判断。

**设计：状态与模型由后端一次判定，前端只消费、不推导。**
- `GET /novels/{id}/ai-model` 响应扩展为 `{ api_config_id, model, config_name, ai_state, effective_model, reason?, message? }`：
  - `ai_state ∈ {ready, member_required, no_key, missing_model, invalid}`（**与 `detail.reason` 同枚举**；完整枚举与优先级见 D13——`member_required` > `invalid` > `no_key` > `missing_model` > `ready`）；后端**同一判定函数** `compute_ai_state(novel, config, has_user_key)` 算出，与 `require_novel_model` **共用**（判据只写一次）。
  - `ready` 判据：`ai_config_id` 与 `ai_model` 均非空 **且 本书绑定的配置存在** **且 该配置有可用 Key** **且 `ai_model ∈ json.loads(config.models)`**——最后一项与 D12 的绑定校验**共用同一谓词**（`refresh-models` 后旧模型被移除时不再误报 ready）。
  - **残留态必须覆盖（后端落地审查 R8）**：删 ApiConfig 时 `api_configs/service.py:224-226` 只把 `novels.ai_config_id=None`、**故意保留 `ai_model`**（注释「intentionally retained for history display」）→ 判定函数必须把「`ai_config_id` 空 **且** `ai_model` 非空」判为 **`invalid`**（不是 `missing_model`，也不是 ready），否则会误判。
  - `no_key` 粒度＝**本书绑定配置级**（不是「用户任意配置有 Key」——后者会让「绑了 A 但 A 没 Key、B 有 Key」误判 ready）。
  - `configs` 由调用方查 `ApiConfig` 传入（`require_novel_model` 从 `db` 取）；落点建议 `api_configs/service.py`（紧邻 `get_project_ai_model`）。
  - `effective_model` ＝ 按权威链算出的**实际生效模型**（`project.ai_model` 唯一权威，`writing_model` 字面覆盖忽略），前端只显示、不推导。
- 前端 `useModelStatus` **删除本地四态推导**，直接读 `ai_state`/`effective_model`；AI 行门控按 `ai_state` 分派（`no_key`→去模型配置 / `missing_model`|`invalid`→去选模型 / `ready`→调用）；catch 兜底按后端 `detail.reason` 分派，**`reason` 与 `ai_state` 共用同一枚举**。
- **效果**：前后端判据漂移、`invalid` 前端派生、错误词汇不统一、双模型源——四类「识别」问题一并消解（判据与枚举各只写一次，两端共用）。

**D11. 后端模型调用分层（一张视图 + 边界禁令）。**

本 change 触及 C端后端几乎所有 AI 调用点，须先把分层画清，否则同类「穿透」问题会再犯（复审已见 `writing_model` 绕开权威源、业务层直接 `get_ai_client()`）。

**分层（自下而上，各层落点＝现状模块）**：

| 层 | 落点 | 职责 | 禁止 |
|---|---|---|---|
| ① 配置层 | `api_configs/`（router/service/schemas/connection/crypto/vendor/usage）+ `models/api_config.py` | 存 ApiConfig（Key/BaseURL/api_format/模型列表）、测连接、记用量；存本书选择 `Novel.ai_config_id`/`ai_model` | 不含业务判断、不含会员判断 |
| ② 解析层 | 新增 `effective_model` 解析 | 把「本书用哪个模型」解析成**唯一答案**（`project.ai_model` 权威；`writing_model` 仅 `haiku/sonnet` 别名，字面名忽略） | 业务层不得自己读 `writing_model` 决定模型 |
| ③ 判定层 | 新增 `compute_ai_state(novel, config, has_user_key)`（D10） | 就绪状态单一判定 `ready/no_key/missing_model/invalid` | 前端不得自行推导（D10）；门控不得另写判据 |
| ④ 客户端层 | `ai_client.py`（`AIClient`/`get_ai_client_for_novel`/`chat`/`chat_stream`/`resolve`） | 构造连接（api_format 分流 anthropic/openai）、发请求、流式、按 `api_format` 落地 `json_mode` | 不读**创作内容**（story/settings/chapters）；允许读本书模型绑定（`ai_config_id`/`ai_model`） |
| ⑤ 门控层 | `auth_local/deps.py`（`require_ai_access` + 新增 `require_novel_model`） | 准入：会员 → 可用 Key → 本书模型 | 判据须复用 ③，不得内联 |
| ⑥ 业务层 | `write/` `settings/` `chapters/` `prompt/` `archive/` **`story/`** **`novels/`**（`ai_prefill.py`、`novels/router.py` suggest-meta 豁免） | 挂依赖、取客户端、组上下文、落结果、记 usage | **禁止直接 `get_ai_client()`**；禁止自判会员/模型；禁止直接读 `writing_model` |
| ⑦ prompt 层 | `prompts/*.prompt` + `prompts.py load()` | 模板加载与格式化（**模型无关**） | prompt 内不写模型名 |
| ⑧ 计量层 | `api_configs/usage.py`（`record_usage`） | 记 token 用量 | 须记**实际生效模型 id**（非 `"haiku"`） |

**边界禁令（分「可 grep 门禁」与「review 清单」——不笼统声称全部可 grep）**：
- **可 grep 门禁**：
  1. 业务层禁裸 `get_ai_client()`——命令须排除 tests/注释/豁免：
     `grep -rnE '\bget_ai_client\(' client/backend --include='*.py' | grep -vE 'ai_client\.py|/tests/|ai_prefill\.py|novels/router\.py|__pycache__|\.mimosa' | grep -vE '^\S+:[0-9]+:\s*#'` **须为空**（豁免清单：`ai_client.py` 定义处、`tests/`、`ai_prefill.py`、`novels/router.py` suggest-meta）。
  2. usage 记实际模型 id：`grep -rn 'model="haiku"' client/backend --include='*.py'` 与各 `record_usage(` 调用点逐一核对。
  3. 门控违规近似检查：`grep -rnE 'check_permission\(|is_member' client/backend/{write,settings,chapters,prompt,archive,story,novels}` 须为空（命中即「业务层自判会员」）。
- **review 清单**（无法 grep，靠评审）：
  1. 业务层是否直读 `writing_model` 决定模型（grep 只能列出出现点供人工确认「是否经解析层」）。
  2. 门控是否只在 dependency 且判据复用 ③。
  3. 就绪状态是否只在 ③ 判定（前端可近似 grep `useModelStatus` 内是否还有 `status =` 赋值）。
- 另：`record_usage` SHALL 记实际生效模型 id（⑧）。

**D12. 模型选择的三层粒度与绑定规则（用户裁定）。**

**粒度**（三个不同 scope，勿混）：

| 对象 | 粒度 | 说明 |
|---|---|---|
| 供应商 / API 配置 | **C端用户级** | `ApiConfig` 由用户在「模型配置」配一次，**所有书共用同一批供应商**；一本书不单独配供应商 |
| 模型 | **书级** | `project.ai_config_id` + `project.ai_model`——**一本书选一个模型，全书所有 AI 助手共用**（简介体检/补缺失/润色、题材五行、章写作/续写、章纲起草、提示词润色、归档摘要）；`effective_model` 对全书唯一 |
| 提示词 / 能力 | **页面级** | 每个 AI 助手功能一套模板（`settings_intro_{action}`、`settings_genre_{field}`、章写作/润色/章纲各一），模板**模型无关**（不写模型名）；页面差异体现在 prompt，不体现在模型 |

**绑定规则**：模型与其供应商**绑定**——`project.ai_config_id` 与 `project.ai_model` 必须来自**同一配置**（选了哪个模型，就用该模型所属配置的 Key/BaseURL，不可跨配置混搭）。落法：
- UI：卡片列表按配置分组，选中即确定 `(config_id, model)` **整对**（`cid::model`）——**跨配置混搭在 UI 上不可达**（每行携带所属组 `api_config_id`）；**组内换模型＝同配置换 model，是允许的**（禁的是跨配置混搭）。
- 后端：`set_project_model`（**函数名以现状为准**，`api_configs/service.py:306`；路由 `set_project_model_route`）SHALL 校验 `model ∈ json.loads(config.models)`——须处理 `models` 为 **JSON 文本**（`models/api_config.py:41`，需解析 `None`/空串/非法 JSON）、**空列表拒绝**（config 无模型时任何 model 都拒）、**部分 null 拒绝**（`(config_id, None)` / `(None, model)` 不成对即拒，除非显式 clear）；失败返 **400**（语义错误，Pydantic 缺字段才 422）。现状 `SetAiModelBody` 两字段均可 `None` 且 service 不校验 → 可静默存错配。
- 前端承接：确认键遇 400 须**保留 draft 选中态 + 行内报错**（不清空、不禁用），不得只 toast 后丢选中。
- `effective_model` 解析以该对为准（② 解析层），且 `ready` 判据共用同一 `model ∈ config.models` 谓词（D10）。

**推论**：
- 全书共用一个模型 → 该模型须能胜任**所有**页面助手；弱模型（如本地 `qwen3:32b`）在结构化输出上可能吃力，由「结构化输出策略 + endpoint 归一化兜底 + 502 可重试」应对。
- 换模型＝换全书 AI 的模型（一处改、全书生效），与「一本书内 AI 助手模型一样」一致。
- **页面差异不止 prompt，还有调用参数**（P1 补充）：一本书只有一个模型，却要同时跑两类任务——**JSON 判定类**（`introspect`/`fill`/`settings_genre_{field}`：温度 ≤0.3、结构严格、输出短）与**长文生成类**（章写作/续写/章纲：0.7–1.0、`max_tokens` 4000）。现状 `AIClient.chat` **从不传 `temperature`**（靠 provider 默认 ≈1.0）——对判定类会导致「同文两次结论不同、达标/缺失漂移」；`settings/ai_router.py` 硬编码 `max_tokens=1024`，而 `introspect`（六段 × {name,status,excerpt,note} + taboo + verdict ≈ 700–1400 tokens）有**截断 → 非法 JSON** 的系统性风险。故须：
  1. `AIClient.chat` 透传 `temperature`；逐页面定 `max_tokens`/`temperature`（见 spec 参数表）。
  2. **`json_mode` 分层归属**：业务层只传**语义参数** `json_mode: bool`；由**客户端层**按 `api_format` 决定是否落地为 `response_format={"type":"json_object"}`（Anthropic 分支忽略——直接透传会 400），不支持者靠 prompt + 归一化兜底。
  3. **模型能力门槛/降级提示**：本书模型须支持 system 消息与 ≥8k 上下文；不支持 JSON mode 的模型走归一化兜底并给**非阻断**提示。

**D13. AI 可用性识别的完整收敛（合并会员维度 + 降级链显式化）。**

**残留的两处多源**（D10 只收敛了「书级模型就绪」，这两处没覆盖）：
- **会员维度两个源**：前端 `useFeature('settings-ai-fields')` 读 **entitlement 快照**（`useTier.ts:31`），后端 `require_ai_access` 读 **DB `check_permission()`**——快照过期/失联时不一致（前端放行、后端 403）。
- **建书期模型 4 级 fallback**：`get_ai_client_for_user` 链为「本书 ApiConfig → 用户 active 配置取 `models_list[0]` → 旧 `User.api_model` → `config.json`」，其中 `models_list[0]` 是**隐式默认**；建书期（`ai_prefill`/`suggest_meta` 无 project_id）的模型来源与 D12「模型＝书级」无关，且用户无从识别。

**设计**：
1. **`ai_state` 扩展为覆盖「AI 为什么不可用」的完整枚举**：`{ready, member_required, no_key, missing_model, invalid}`。前端门控**只读这一个字段、一次分派**（不再 `useFeature` + `ai_state` 两处判）——视觉预判与后端判定同源。**注意**：`member_required` 只拦「调用 AI」，**不拦模型配置本身**（配置是人工路径能力，D4）；后端 `require_ai_access`/`require_novel_model` 仍是最终闸门（403/503 兜底，前端 gate 是提前量）。
2. **建书期降级链显式化**：有书一律 `effective_model`（`project.ai_model` 权威）；**无书路径仅限 `ai_prefill`/`suggest_meta`**（建书期），走显式降级链「用户首个 active 配置的 `models[0]`（文档化规则，非隐式）」，并在日志/响应标注「建书期降级模型」；**业务层其余路径禁用 `get_ai_client_for_user`**（只准 `get_ai_client_for_novel`）。
3. **判定优先级**（`compute_ai_state`）：`member_required` > `invalid` > `no_key` > `missing_model` > `ready`——会员不足是最高优先（免费用户先看到升级引导，而非"去选模型"）。

**D14. AI 助手交互状态机（四个能力共用一套交互语义）。**

**病根**：体检/补缺失/润色/题材五行各自定义「成功/失败/采纳/重试」，于是异常路径各写各的——复审的 O-3（补缺失未先体检）、O-4（save 成功但 confirm 400）、O-5（结果区生命周期）、O-13（失败文案矩阵）、O-16（六段全 ok 时补缺失）**都是这一个病根的不同表现**。

**设计：四个能力共用同一状态机，`.ai-sink` 是它唯一的渲染面。**

```
idle ──点能力行──▶ running ──成功──▶ result(候选) ──采纳──▶ adopted(已写回)
                     │                    │
                     └──失败──▶ error(reason)        重试 ──▶ running
```

| 状态 | UI 表现 | 转移 |
|---|---|---|
| `idle` | 结果区隐藏（或保留上次结果） | 点能力行 → `running` |
| `running` | 骨架/转圈 + 该能力行禁用 | 成功 → `result`；失败 → `error` |
| `result` | 候选 + 「采纳」「重试」 | 采纳 → `adopted`；重试 → `running`；**切面板/确认 → 清空回 `idle`** |
| `adopted` | 结果区**保留**（可继续改） | 再点能力行 → `running`（覆盖） |
| `error(reason)` | 按 `reason` 渲染文案 + 「重试」 | 重试 → `running` |

- **前置守卫**：能力有前置时（补缺失需先体检拿到缺失段），未满足则**该行置灰 + 一句「先体检」**，不进入 `running`（O-3）。
- **空结果**：`result` 但候选为空（如六段全 ok 时补缺失）→ 显示「无需补，六段都齐了」，不空白（O-16）。
- **错误分派**：一律按 `detail.reason`（`member_required`/`no_key`/`missing_model`/`invalid`/400/502/网络），文案见 spec 矩阵；**重试不重复计 usage**（O-13）。
- **生命周期**：结果区**采纳后保留、切面板清空、重新请求覆盖、确认后清空**（O-5）。
- **save 与 confirm 分离**：面板 save 成功但 confirm 400（服务端读到的不一致）→ 给「内容未通过校验」并**保留 dirty**，不假装已确认（O-4）。

**D15. 状态恢复出口完备性（每个不可用态都必须有出口）。**

**病根**：复审 O-7/O-8/O-9/O-18 都是「某状态没被识别，或识别了但没有出口」。

**设计原则**：`ai_state` 的**每个非 `ready` 值，必须（1）可被判定、（2）有且仅有一条明确的恢复路径**。

| `ai_state` | 判定（含边界） | 恢复出口 |
|---|---|---|
| `member_required` | 非会员 | 升级 PRO → **已配模型直接可用**（不必重配） |
| `no_key` | 本书绑定配置无可用 Key **（含 Key 非空但 `last_test_status` 为失败态——O-9，文案区分「未配置」/「测试失败，请检查」）** | 去「模型配置」加 Key / 重测 → `refresh()` |
| `missing_model` | 有 Key 未选模型 | 选模型 + 确认 |
| `invalid` | 绑定配置已删 **或 `model ∉ config.models`（存量错配——O-8；D12 校验只挡写入、不挡存量读取，须由判定层兜住）** **或「`ai_config_id` 空 + `ai_model` 非空」的删除残留（R8）** | 重选模型；**若无其他可用配置 → 给「新建配置」入口（O-7 不死路）** |
| `ready` | 上述全部满足 | — |

- **`ready` 收紧**：须同时满足「Key 非空」**且**「最近一次连接测试非失败态」（O-9），否则"Key 填了但无效"会被误判就绪。
- **死路径清理**：`ai-model` 在 `VALID_TYPES` 里可确认（`status.py:14`）但 UI 无确认按钮（`SettingsView.tsx:340`）→ 本 change **移除 `ai-model` 的「可确认」语义**（它不是设定完成度项，D4），消除死路径（O-18）。

**D16. 写回语义表 + 流程收尾。**

**写回语义（按字段类型统一，消除各能力各写各的）**：

| 字段类型 | 采纳语义 | 无法映射时 |
|---|---|---|
| 单值文本（synopsis / core_promise / track / promise_note） | **覆盖**（按钮文案「采纳 · 覆盖」） | — |
| 列表（forbidden_list / battlefield） | **覆盖整个列表**（不追加——O-6） | 落为 `custom`（不丢弃、不报错） |
| 数值（cost_ratio） | 覆盖 | — |
| 选中态（01 口味胶囊） | 不走 AI | **取消选择不回滚**已填各格（只提示——O-15） |

- **不成对拒绝**：`(config_id, None)` / `(None, model)` 拒绝；`(None, None)` 显式 clear 允许（O-12）。
- **流程收尾**（O-11）：「跳过」＝不点确认直接切下一个 tab（无需专门按钮，与「顺序是引导不是锁」一致）；**末项确认后 → 设定完成态**（进度全绿 + 「去写作」主 CTA），不循环、不停留在末项。
- 模型步不进序列、不参与完成度（D4/D13）。

**D17. 后端落地架构（数据层 + 大模型对接层）。**

**一、数据层：C 端数据全在 DB（现状事实，非待办）**
- 设定＝`project_settings` KV 表（`root_path + key` 复合主键、`content` 存 JSON Text）；`filesystem/paths.py::PATH_TO_KEY` **全量路由**：`story.yaml→story`、`settings/genre.yaml→genre`、`world-setting.yaml→world`、`writing-style.yaml→style`、`anti-ai.yaml→anti-ai`、`hooks.yaml→hooks`、`ai-model.yaml→ai-model`、`settings-status.yaml→status`；`threads.yaml→threads`；`settings/character-setting/*→character:*`。`CompositeStorageBackend` 对这些路径分派 `DatabaseFileBackend`；**只有 `route_relative_path() is None` 的路径落本地文件**（章节正文 md、导出包等）。`seed_settings_to_db`（ADR-003）：新项目种子只进 DB 不进盘。
- **本 change 的数据落点**：

| 数据 | 落点 | 本 change 操作 | DDL |
|---|---|---|---|
| 简介 | `project_settings(root_path,"story").content` JSON `{synopsis}` | 契约不变（≤500） | **无** |
| 题材 | **关系表 `novel_genre` + 关联表（见 D19，方案 A）** | **推翻 KV JSON，改 4 张表** | **新增 4 表**（无迁移，存量库留档重建） |
| 设定状态 | `project_settings(root_path,"status")` | confirm 写 `true` | 无 |
| 模型绑定 | **`novels.ai_config_id` / `novels.ai_model`（真列）** | 加绑定校验 + `ai_state` 派生 | **无**（列已存在） |
| 配置 | `api_configs.models`（JSON Text） | 读模型列表做 `model ∈ models` 校验 | 无 |
| 用量 | `token_log` | `operation` 细分 + `model` 记实际 id | 无 |
| 审计 | `project_model_audit_log` | 同值重复 PUT **不新增行** | 无 |
| 题材库 | `genres` 表（全局 preset+custom） | **不碰**——「本书题材设定」≠「全局题材库」，边界见 D12 | 无 |

- **结论：简介/模型绑定部分零 DDL**；**题材改为 4 张新表（D19 方案 A，用户拍板「一次做对」）**——无迁移（无 C 端用户），存量库走「指纹不匹配→留档重建」。旧 `genre_id` 随 `project_settings('genre')` 行**整体废弃**。
- **`genres` 表边界**：本 change **不碰** `genres` 表（无 DDL/seed/CRUD 变更）——只做两件事：① 停止「本书题材」经 `genre_id` 引用它（前端停用 `GenrePicker`、后端 `resolve_genre_context` 改读本书五字段）；② 表退化为只读历史库，`_find_referencing_projects` 改后恒空 → 停用该 guard。**候选源＝`genre_vocab` 表**（D19）：种子 `genres/vocab_presets.py`（稳定 slug）→ `ensure_seed_genre_vocab()` 幂等插入；`GET /api/genres/candidates` 从表读（前端镜像 parity 测试）。
- **R10 警告**：`settings/ai-model.yaml→'ai-model'` 是**确认标记行**，实测**无任何生产代码读写它**（仅 `VALID_TYPES` 与测试引用）——**不要把 `ai_state` 写进这行**。
- **写作注入必须同批重写（最高危）**：`genres/service.py::resolve_genre_context` 现依赖 `genre_id`（`:180-182`）→ 若不同批改写为读五字段，`build_genre_section` 会**恒空且无报错**（静默降级，正文质量悄悄变差）。

**二、大模型对接层（D11 八层的函数级落点）**

| 层 | 新增 / 改动 | 签名建议 |
|---|---|---|
| ② 解析层 | **新增 `api_configs/ai_state.py`**：`resolve_effective_model(project)`（权威＝`project.ai_model`）、`resolve_writing_model(project, alias)`（仅 `haiku/sonnet/review` 别名，字面名忽略） | — |
| ③ 判定层 | 同 `ai_state.py`：`compute_ai_state(novel, config, has_user_key)` | 优先级 `member_required>invalid>no_key>missing_model>ready`；**含 R8 残留分支** |
| ④ 客户端层 | **新增** `get_ai_client_for_novel(novel_id)`；**改** `AIClient.chat(..., temperature=None, json_mode=False)` | OpenAI 分支落 `response_format`、Anthropic 忽略；`get_ai_client()` 收窄/改名，无调用者则删 |
| ⑤ 门控层 | **新增** `require_novel_model(project_id, user, db)`；**改** `require_ai_access` | 补 `detail.reason="no_key"`（保持 503） |
| ⑥ 业务层 | **改** 12 处 `get_ai_client()` → `get_ai_client_for_novel`；**新增** `settings/ai/intro/{action}` 子路由（**注册在 `/{stype}/{field}` 之前**）；**改** `settings/ai_router.generate_field`（加 genre、prompt 按 field）；**重写** `genres/service.py::resolve_genre_context`（读五字段，见上） | `polish_text`/`expand_text`/`archive_chapter` 补 `project` 形参 |
| ⑦ prompt 层 | **新增 8 个模板**：`settings_intro_{introspect,fill,polish}` + `settings_genre_{5 field}` | 模型无关；schema+枚举+few-shot 占位 |
| ⑧ 计量层 | **改** `record_usage` | 记 `model=resolve_effective_model(project)`、**`api_config_id`（现未传）**、`operation=settings_{stype}_{action|field}` |

- **流式选择**：简介/题材**非流式**（结构化 JSON + 归一化）；章写作/续写保持 `chat_stream`。

**三、JSON Text 列的架构约束**（KV 存储的固有边界）
- **无 schema、无索引、无部分更新**：校验必须在应用层（Pydantic + `compute_ai_state`），不能指望 DB 约束；写回一律**整行覆盖**（并发下 last-write-wins → 靠前端 dirty 保护与确认键，D4/D16）。
- 读全量 JSON 再判（`_check_genre`/`ai_state`）——本 change 数据量级（单书设定）无性能问题。

**四、事务与一致性**
- `ai_state`/`effective_model` 是**派生值、不落库**（每次实时算）→ 不存在与存储不一致。
- 绑定校验与 `project_model_audit_log` 写入**同一事务**；同值重复 PUT **不写审计**（幂等，见 spec）。
- 设定写入（KV 整行覆盖）与 `status` 确认是两次写 → 失败时以「status 未确认」兜底（`readiness` 为准）。

- **R9 第二题材源（已定）**：建书时 `novels/service.py:60-62` 把 `genre_profile` 写进 `settings/writing-style.yaml`。**处置＝停用**（不再作为题材来源，不参与写作注入/判定）；建书期若需展示名，用 `story.genre`（已有，本就是展示名）。
- **双 storage 落盘风险**：`CompositeStorageBackend` 对 `route_relative_path() is None` 的路径**静默落盘**。本 change **禁止新增**未路由路径（如 `settings/genre_v2.yaml`）——简介用 `story`、题材用 `genre`、状态用 `status`；建议给未路由分支加告警日志 + 单测断言本 change 全部路径 `route_relative_path(p) is not None`。

**D18. 数据字典（逻辑字段设计；物理层零 DDL）。**

存储位置：**题材＝4 张关系表（D19）**；简介＝`project_settings(root_path,"story").content`；状态＝`(root_path,"status").content`；模型绑定＝`novels` 表列。

**一、题材 `genre` 行（本 change 契约）**

> **本小节（KV 形状的题材字段表）已被 D19 取代**——题材改 4 张关系表，字段约束见 D19 表结构。以下仅保留仍有效的判据与处置规则：

- **确认判据**（`_check_genre`）：`core_promise`/`forbidden_list`/`cost_ratio`/`battlefield`/`track` **至少一非空**；**01 口味胶囊不计入**（不落库）。
- **空值统一规则**：`null` / `""` / 纯空白 / `[]` 一律**等价视为未填**（不得只判 `None`）。
- **旧键处置**（读路径丢弃、写路径整行覆盖自然清除）：`genre_id` **移除**；`prompt_injection_enabled`、`selected_arc_id` **移除**（随 `GenrePicker` 退役）；`config_overrides.*`（`fulfillment_types`/`chapter_types`/`pacing_rules`/`fatigue_words`）＝**写作引擎配置**，**迁至 `writing-style.yaml`**（`fulfillment_types` 语义并入 `core_promise`），不留在题材行。

**二、简介 `story` 行**

| 字段 | 类型 | 约束 | 空值语义 |
|---|---|---|---|
| `synopsis` | `string` | **≤500 字**（**501 尾部截断**） | `null`/`""`/空白 等价未填 |

**三、模型绑定 `novels` 表列（既有，无变更）**：`ai_config_id` `String(36)` FK→`api_configs.id` `ondelete=SET NULL`、`ai_model` `String(100)`，均 nullable；**删除配置后 `ai_config_id=NULL` 而 `ai_model` 保留**（R8）→ 判定见 D10/D15。

**四、用量/审计字段约定**：`token_log.operation = settings_{stype}_{action|field}`、`token_log.model = effective_model`（实际生效 id）；`project_model_audit_log.field = "ai_model"`，**同值重复 PUT 不新增行**。

**五、校验位置**：物理层无约束（JSON Text）→ 全部落在 **Pydantic 请求模型 + 服务层谓词**；候选源（`core_promise` 枚举 / `forbidden` tagId 目录 / `battlefield` 候选）由 `GET /api/genres/candidates` 下发，前端镜像需 parity 测试。
> **注**：本节题材部分（KV JSON）**已被 D19 取代**——题材改关系表；简介/模型绑定部分仍有效。

**D19. 题材完全关系化（方案 A；用户拍板「一次做对」）。**
**为什么推翻 KV JSON**（D17/D18 的题材部分作废）：
1. **候选源必须有稳定标识**——原设计 `tagId = preset:{id}:{index}` 的 **index 会随常量顺序漂移**，用户已存的禁项会指向错误标签（**不可逆的静默数据损坏**）；仓库既有范本 `genres` 表正是用**稳定 slug 主键**（`"urban-daily"`）。
2. **列表字段需外键引用词汇**——`forbidden_list`/`battlefield` 塞 JSON 数组无法建外键、无法去重、无法统计。
3. **约束应由 DB 保证**——`cost_ratio 1–10` 靠应用层判是"约定"，靠 `CHECK` 才是"保证"。
4. **未来查询**（同题材书发现/推荐）需按字段查——KV JSON 无索引。
5. **时机**：现在**无 C 端用户、无迁移**，是改的唯一零成本窗口（正是「一次做对」的判据）。

**表结构（4 张）**：

| 表 | 主键 | 关键列 | 说明 |
|---|---|---|---|
| `genre_vocab` | `id VARCHAR(64)`（**稳定 slug**） | `kind`(`promise`/`forbidden`/`battlefield`)、`label VARCHAR(100)`、`sort INTEGER`、`is_preset BOOLEAN` | 候选源字典（含用户自定义）；种子幂等 |
| `novel_genre` | `novel_id`（FK→`novels.id` CASCADE） | `core_promise VARCHAR(60)`、`promise_note VARCHAR(200)`、`cost_ratio INTEGER`（**CHECK 1–10**）、`track VARCHAR(300)`、`updated_at` | 1:1 本书题材（表名以 D20 命名统一为准） |
| `novel_genre_forbidden` | `(novel_id, sort)` | `vocab_id`（FK→`genre_vocab`）**或** `custom_text VARCHAR(100)`（**CHECK 恰一非空**）；**UNIQUE(novel_id, vocab_id)** | 禁项关联 |
| `novel_genre_battlefield` | `(novel_id, sort)` | 同上 | 战场关联 |

- **tagId 改为稳定 slug**：`forbidden:no-deus-ex-machina`、`promise:comeback`、`battlefield:resource-war`——**不再用 index**。
- **对外契约不变**：`GET/PUT /settings/genre` 仍是五字段 JSON（前端与 AI 端点无感）；后端存储层组装/拆分（**事务**：`novel_genre` upsert + 关联表 delete+insert）。
- **候选源种子**：新增 `genres/vocab_presets.py`（稳定 slug + label + kind + sort），启动时 `ensure_seed_genre_vocab()` 幂等插入（沿用 `ensure_seed_genres` 模式）。

**落点定稿**：新增 `genres/novel_genre_service.py`——`get_novel_genre(db, novel_id) -> dict` / `put_novel_genre(db, novel_id, payload) -> None`（单事务 upsert `novel_genre` + delete+insert 关联表）；`settings/router.py` 的 `get_settings`/`update_settings` 对 `type=="genre"` **分支旁路 KV**（泛型 KV 通道无法单事务写 4 张表）；`readiness._check_genre` 改调该 service。

**删除策略**：关联表 `vocab_id` FK 用 `ON DELETE RESTRICT`（删被引用的 vocab 报错并提示「先解除引用」）；用户自定义 vocab 的 id ＝ `custom:{slugify(label)}`（冲突加 `-2`/`-3` 后缀）；`cost_ratio` 可空须写 `CHECK (cost_ratio IS NULL OR cost_ratio BETWEEN 1 AND 10)`；关联表 `sort` ＝ 从 0 连续、顺序＝前端数组序。

**影响面**：`readiness._check_genre` → 查 `novel_genre` + 关联表；`genres/service.py::resolve_genre_context` → 查三表组装注入（**必须同批改，否则注入恒空**）；`GET /api/genres/candidates` → 查 `genre_vocab`；**`project_settings('genre')` 废弃**（不再读写）。

**DDL 落地机制（C端无 alembic）**：新库由 `Base.metadata.create_all`（`main.py:67`）自动建；**存量库因 schema 指纹变化触发「改名留档 + 全新库」**（`legacy_archive.py`）——无 C 端用户可接受（开发者本地库需重跑种子）。

**D20. 实体命名统一：`projects` → `novels`（Change C D1 翻案，用户拍板「本 change 包含」）。**

**背景**：C端一物三名已收敛两处——类名 `class Novel` ✅、前端路由 `/novels/*` ✅；**DB 表名 `projects` 是唯一残留**。Change C 的 D1 原判「不动」，理由＝「已分发安装包在用户机器落地，改表名＝全量迁移，风险/收益不成比」；**该理由已失效**——用户明确「无 C 端用户、无迁移事项」，迁移成本归零（实测规模见下文「实测规模」）。

**改名范围**：
- 表名 `projects` → `novels`；列名 `project_id` → `novel_id`（`chapters`/`volumes`/`token_log`/`project_model_audit_log` + 新表）
- FK 字符串 `ForeignKey("projects.id")` → `ForeignKey("novels.id")`（**4 处**：chapter/volume/token_log/audit_log）；`ApiConfig.projects` relationship → `.novels`
- 后端 URI `/api/v1/projects/*` → `/api/v1/novels/*`（Change C D2；**无外部消费者，直接改不留别名**）
- 前端残留：`useModelStatus` 的 `/projects/...` → `/novels/...`
- `legacy_archive.py:59` 表名判断、测试同批（Change C D3「测试同批」）
- **不改**：磁盘目录 `PROJECTS_DIR`（与实体命名解耦，`root_path` 已存库）

**实测规模（后端工程师复核，D20 原估偏小）**：表名 6 处 + 列名 4 个 model 列 + **后端 `project_id` 全量 259 处**（形参/局部变量/字典键/路径参数）+ URI 生产路由 **8 条**（`api_configs/router.py:296/307/323/336/349/369/382/398`）+ 测试/e2e 17 处 + 前端 **3 文件 5 处**（`useModelStatus.ts:27/72`、`useUsageStats.ts:31`、`useChangeHistory.ts:26/46`）+ `main.py:91/100/112` 裸 SQL、`legacy_archive.py:61`。**门禁须补** `grep -rn "project_id" client/backend --include='*.py' | grep -vE '/tests/|/.venv/'`（原 grep 查不到 259 处形参）。

**副作用**：改表名必然触发 `legacy_archive` 指纹不匹配 → **开发者本地库整体留档重建**（书/演示数据清空，e2e seed 需重建）。

**落地机制**：无用户 → 存量库指纹变化触发留档重建；新库 `create_all`。

**遗留（记录，本 change 不做）**：`project_settings` 用 `root_path` 而非 `novel_id` 做键、与 `novels` 无 FK——KV 表的历史设计（通用 KV 不绑业务表）；统一它要动 storage 抽象、波及 8 类设定，**另立 change**。

**保留 project 命名清单**（不改，集中登记）：`project_settings`（KV 表名）、`PROJECTS_DIR`（磁盘目录）、`set_project_model`/`get_project_ai_model`（函数名，spec 已声明「以现状为准」）、`project_model_audit_log`（表名保留，其列改 `novel_id`）、`project_id` 作为**路径参数名**（改会触发 FastAPI 422，见 tasks 7.3）。

**API 版本命名空间**：`api_configs` 用 `/api/v1` 前缀、其余模块用 `/api`——D20 后出现 `/api/v1/novels/{id}/ai-model` 与 `/api/novels/{id}` 并存；**沿用各自 prefix、不统一版本号**（无冲突，避免本 change 扩大范围）。

**同步 Change C**：其 D1 从「不动」翻案为「本 change 一并改」；D2/D3 与本 change 一致。

**D21. 体检纳入「标题对照」（用户追加，2026-09-10）。**

**病根**：体检只回答「简介六段写全了吗」，不回答「这六段配得上这个书名吗」——`verdict` 仅由六段齐全度 + 有无禁忌决定，故**标题跑偏也判 strong**（例：《我在夜晚打吸血鬼》+ 宫斗简介 → strong；《第一章》→ strong）。

**设计**：体检增第 ③ 项标题对照，`title_check.fit ∈ {ok, mismatch, generic}`（三值语义见 spec），`mismatch`/`generic` 给理由 + ≤3 条候选标题（≤16 字，贴题材、留钩子、不剧透）。**兜底原则**：模型未给或值非法 → 字段不下发、前端不渲染该行，**不得硬判 `ok`**（避免"看起来体检过了"的假绿）。`verdict` 口径**不变**（仍只看六段 + 禁忌），标题对照为**独立提示行**，不参与 verdict——避免改动既有判定语义。**拍板（用户 2026-09-10）**：候选标题只作参考，**不做一键改书名**——书名是作者的创作决定，系统只提示、不代改。

## Risks / Trade-offs

- **[风险] 简介/题材面板已有 e2e 与 READINESS 依赖** → 重排 SETTINGS_ITEMS + 纯新契约会改变「第一步」与「题材确认」判定；先跑相关 e2e（settings、readiness、onboarding）确认无假定 genre 优先/genre_id 判据的断言，再改动。
- **[风险] 题材纯新契约推翻 genre_id** → `_check_genre`/`GenrePickerModal`/`GenreEditModal`（亦引用 `data/genres.ts`）/`data/genres.ts`/`DEFAULT_GENRE_ID` 均受影响；**无 C端用户、无迁移**，可直接替换，但要全仓库清理依赖（readiness、性别判定、prefill），避免残留 `genre_id` 读空。
- **[风险] AI 响应结构化解析失败** → 体检/题材候选多为 JSON，模型偶发非法 JSON；统一 502 可重试 + `.ai-sink` 给「暂不可用/请重试」且不拦确认，避免白屏。
- **[风险] 简介 AI 以输入框 synopsis 为源** → 编辑中未保存的 synopsis 需随请求带出（`body.content`），不能只读 story.yaml——否则体检的是旧文。
- **[风险] 「已填」徽标从 ok 改 warn 属语义回归** → 同步更新依赖该颜色断言的测试；原型先落地、实现对齐。
- **[风险] 枚举/标签字段候选来源** → core_promise 枚举、forbidden_list tagId、battlefield 数组必须有可回落的候选源，否则模型只能走 custom、预置形同虚设；候选源＝`genre_vocab` 表（D19）+ `genres/vocab_presets.py` 种子；**不复用 `genres/presets.py` 现成键**（其无这些新键/tagId，仅可萃取语义作初稿）。
- **[权衡] 无数据迁移**：无 C端用户；题材改 4 张关系表、`project_settings('genre')` 行废弃，存量库指纹不匹配→留档重建（旧 genre_id 随行废弃）。

## Migration Plan

1. 原型：`drafts/genre-signup-draft.html` → `prototypes/`（新屏或并入工作台设定屏），`ADJUSTMENTS.md` 登记偏差。
2. 后端：`settings/ai_router.py` 扩 `FIELD_GENERATABLE`(genre) + 新增 `settings/intro` 子路由 + `settings_genre_{field}.prompt`/`settings_intro_{action}.prompt` 模板 + 禁忌规则/候选来源 + usage/错误契约；`readiness._check_genre` 判据改新契约；**`compute_ai_state` 判定层 + `effective_model` 解析层 + `get_ai_client_for_novel` + `require_novel_model`；`api_configs/service.py` 的 `set_project_model` 补绑定校验（`model ∈ json.loads(config.models)`、空列表/部分 null 拒、400）；全仓库 12 处 `get_ai_client()` 替换（豁免 `ai_prefill.py`/`novels/router.py` suggest-meta）+ `polish_text`/`expand_text`/`archive_chapter` 补 `project_id` + `writing_model` 停用**。
3. 前端：先重排 SETTINGS_ITEMS + 确认即前进，再落简介面板/题材六格 + `.ai-sink` + `AiWriterAssistant`，接 `lib/ai.ts`（含 `detail.reason` 分派与 `api.ts`/`ai.ts` 结构化错误归一化），**改造 `ModelSettingForm`（select→分组卡片 + 确认键 + draft/脏状态 + 连接状态徽标 + 消费 `ai_state`）**，**`features.ts` 的 `ai-model` 改 `memberOnly:false` + `features.test.ts` 同步**，最后免费版锁定与 `GenrePicker` 清理。
4. 门禁：`design:lint` → `design:check` → `tsc --noEmit` → 相关 e2e（settings/readiness/onboarding）。
5. 回滚：前端 UI + 后端 ai_router 扩展均为增量；题材纯新契约无存量，回滚即还原 SETTINGS_ITEMS 顺序/面板契约与 ai_router。

## Open Questions

- 无实质待决项——设计批准稿 v8.5 已覆盖简介/题材面板、AI 助手、反馈落位、免费版锁定与契约；实现细节（六段模板字面文案、口味预置、题材 01 与现有题材体系取舍）取自评审稿与 PM 稿。
