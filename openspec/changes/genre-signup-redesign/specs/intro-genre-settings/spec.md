## Purpose

定义创建期前两步「① 简介 → ② 题材」的设定面板：简介六段模板引导与 AI 写作助手、题材六格与五行 AI、AI 反馈落输入框下方、免费版锁定与简介/题材字段数据契约。

## ADDED Requirements

### Requirement: 创建期前两步重排（简介 → 题材）
- 设定视图的 SETTINGS_ITEMS 前两步 SHALL 固定为 **① 简介 → ② 题材**（题材在前、简介在后的现顺序对调）。
- 第 ① 步简介确认后 SHALL 自动进入第 ② 步题材（确认即前进，可跳过后补）；每步可跳过、可回改；全页无必填、确认永远可点。**末项确认后**（O-11）SHALL 进入「设定完成」态并给「去写作」出口，不循环、不停留在末项。
- 后续（世界 / 开场主角(含金手指) / 主线）与写作期工具（伏笔 / 配角 / 风格 / AI痕迹）SHALL 不占用前两步。

#### Scenario: 简介在前、题材在后
- Given 创建期的设定视图
- When 顺序为 ① 简介 → ② 题材
- Then 先显示简介面板、确认后自动进入题材面板

#### Scenario: 前两步可跳过可回改
- Given 简介已确认、题材未填
- When 用户点回简介 tab
- Then 简介内容保留、可继续编辑，且不锁住题材

### Requirement: 简介面板（编辑框 + 六段模板 + AI 写作助手）
- 简介输入框 SHALL 接受 ≤500 字，实时显示 `x/500` 计数与状态徽标。
- 状态徽标 SHALL 走状态语言：未填＝ghost（中性）、已填＝**进行中/草稿**（warn 软底，不能说成已确认）、已确认才用 ok 绿。
- 「怎么写」SHALL 以**六段模板**呈现为可折叠文本指导（默认收起、点开展开）：主角身份 / 本来的生活 / 突发状况 / 必须面对的矛盾 / 不做的后果 / 做了的可能结局；最后一段固定「可能」结局（指方向、不剧透）。
- 六段模板每段 SHALL 带一句成书视角解释与例句（例句同书贯穿），底部应收六段公式与「别踩」三条（设定集腔 / 作者自白 / 写死结局）。

#### Scenario: 六段模板默认收起、点开展开
- Given 简介面板
- When 作家未点击「怎么写」
- Then 只见折叠行 + 六段名链，点开才见完整六段+公式+别踩

#### Scenario: 已填徽标为进行中（非已确认）
- Given 简介输入框有文字但未点确认
- When 查看状态徽标
- Then 显示进行中（warn）语义，而非已确认（ok）

### Requirement: 简介「AI 写作助手」（三能力，Pro）
- 简介右栏 SHALL 为一个「AI 写作助手」卡片：PRO 徽标并入头部（「AI 写作助手」+ 已解锁/套餐归属/只加工不代写）＋三个**并列**能力行（体检 / 补缺失 / 润色，非先后流程）＋底部来源/去向声明。
- 每行 SHALL 为：能力名称（上）+ 描述（下，从属）+ 右侧箭头，整行可点。
- 体检 SHALL 按四件事检查：① 六段模板逐项查达标/缺失；② 扫禁忌（**设定集腔 / 作者自白 / 剧透**）；③ **标题对照**（书名 ↔ 简介是否互相印证）；④ 结论。**只提醒、不拦确认**；行名与六段模板完全一致。注：禁忌第三元「剧透」与「别踩」第三元「写死结局」**用途不同（扫描规则 vs 写作引导），写死结局 ≠ 剧透，勿合并为同一枚举**。体检为诊断语义，**只分析/只提醒、不补写不改写**。
- 体检接口 SHALL 返回结构化 JSON：`{"six_segments":[{name,status(ok|missing),excerpt,note?}], "taboo":{"hits":[{rule,excerpts}]}, "title_check":{"fit":"ok|mismatch|generic","note":"…","suggestions":["…"]}, "verdict":"strong|ok|weak"}`，其中 `name` 须为六段名之一、`status` 限 `ok|missing`、`fit` 限三值。
- **标题对照语义**（`title_check`）：`ok`＝标题暗示的类型/看点与简介一致；`mismatch`＝不符（如标题像甜宠、简介是压抑复仇）；`generic`＝标题无信息（任何同类型小说都能用，如《第一章》）。`mismatch`/`generic` 时 SHALL 给 `note` 说明理由 + **≤3 条候选标题**（每条 ≤16 字，贴题材、留钩子、不剧透结局）。候选标题 SHALL 仅作参考提示，**SHALL NOT 提供「一键设为书名」入口**——书名改不改、怎么改由作家自己决定（用户拍板 2026-09-10）。**兜底**：模型未返回该字段或 `fit` 非法 → 该字段**不下发**，前端不渲染该行（**不得硬判 `ok`**，避免假绿）。
- **结构化输出策略**（跨供应商/弱模型）：体检/题材的 JSON 输出除 endpoint 后置归一化兜底外，prompt 侧 SHALL 给 **schema + 枚举 + 一个 few-shot 示例**；能用的 provider 追加 `response_format={"type":"json_object"}`（需同步扩 `AIClient.chat` 的 OpenAI 分支）。
- 补缺失 SHALL 只针对缺失段给候选；请求体 SHALL 带 `missing_segments`（前端把 introspect 的 missing 段传来），返回 `{"missing":[{name,candidate}], "act":"insert"}`；**只补缺失段、不重写作者已写段**。采纳才插入简介，可逐条采纳。**前置**：未先体检时「补缺失」行 SHALL 提示「先体检，才知道缺哪段」（或禁用），不得空跑（O-3）；六段全 ok 时 SHALL 提示「六段都齐了，无需补」（O-16）。
- 润色 SHALL 前后对照（入参 `{title, content}`，返回 `{"original","polished","act":"replace"}`），采纳才替换；保原意、只加工不代写。**对照展示形态**＝原句/润后**上下两行**（O-17）。
- **AI 助手交互状态机**（设计见 D14）：四个能力（体检/补缺失/润色/题材五行）SHALL 共用同一状态机 `idle → running → result → adopted`（异常走 `error(reason)`）；`.ai-sink` 为其唯一渲染面。**前置守卫**：补缺失未先体检时该行置灰 + 「先体检」，不空跑（O-3）；**空结果**（六段全 ok 时补缺失）显示「无需补」而非空白（O-16）；**生命周期**＝采纳后保留、切面板清空、重新请求覆盖、确认后清空（O-5）；**save 成功但 confirm 400** → 「内容未通过校验」+ 保留 dirty（O-4）。
- **失败文案矩阵**（O-13）：400 →「请求有误，请检查输入」；403 `member_required` → 升级；403 `no_key` → 去模型配置；503 `missing_model` → 去选模型；502/非法 JSON →「暂不可用，请重试」且**不拦确认**；网络异常/超时 →「网络异常，请重试」。**重试不重复计 usage**。
- 点任一能力，反馈 SHALL 落到**简介框下方**的结果区（.ai-sink，fg-soft），带操作名标签 + 采纳/重试；右栏只作按钮、不内嵌答案。AI 请求以**当前输入框的 synopsis 为源**（`content`），不读存储旧文；入参含 `title`（书名）。

#### Scenario: 标题与简介不符时给出提示与候选
- Given 书名为《我在夜晚打吸血鬼》（暗示都市奇幻），简介写成压抑宫斗
- When 执行体检
- Then 返回 `title_check.fit="mismatch"` + `note` 说明不符之处 + ≤3 条候选标题
- And 简介面板在六段行下方显示「标题对照：与简介不符」+ 理由 + 候选标题

#### Scenario: 标题无信息也提示（不得判为一致）
- Given 书名为《第一章》或《测试》，任何同类型作品都能用
- When 执行体检
- Then 返回 `title_check.fit="generic"` + 候选标题（非 `ok`）

#### Scenario: 弱模型未返回标题对照时不造假绿
- Given 模型输出缺少 `title_check` 或 `fit` 取值非法
- When 归一化体检响应
- Then 该字段不下发、前端不渲染标题对照行（**不得**补一个 `ok`）

#### Scenario: 体检六行与模板一致
- Given 简介已输入
- When 作家点「体检」
- Then 结果区列出六段逐项 达标/缺失，行名与六段模板一致，且给出禁忌扫描结论

#### Scenario: 反馈落输入框下方而非右栏
- Given 点任一能力
- Then 结果出现在简介框下方结果区，右栏不堆长答案

### Requirement: 题材面板（六格 + 五行 AI）
- 题材面板 SHALL 为六格：**① 题材目录（第一问「什么题材？」：大类必选 + 子类可选，见下条）** ② 主要看什么 ③ 绝对禁止（库标签预勾 + 取消＝放行 + 回车自定义）④ 吃苦指数滑块（1-10，浮例句）⑤ 主线战场（预选 2，第 3 个出软提示不禁止）⑥ 剧情轨道。
- **01 格 SHALL 是题材本身（用户 2026-09-10 拍板「题材应该是第一个问题：什么题材」）**：候选源＝**题材目录**（20 大类 × 各自子类，单一事实源 `genres/theme_catalog.py` ↔ `lib/themeCatalog.ts`，逐字对拍）——仙侠/修真、科幻、架空古王朝、刑侦/现实犯罪…（不再用「口味胶囊」当第一问）。交互：点大类即选中（再点取消），选中后出该大类的子类行（单选，可不选）；**换大类 SHALL 清掉不属于新大类的子类**（后端也会 400 拒收跨类子类）。大类是 01 格的**必选**项（子类可选）。
- **目录每一项 SHALL 带「解读」与「案例」（用户 2026-09-10 追加）**：只给名字（如「武魂流」「本格刑侦」）作者不知道指什么。`desc`＝这一项**写的是什么**（一句话、作者视角，非营销词）；`example`＝**可对照的作品/取材**（把抽象标签锚到具体印象，叙事/影视/漫画皆可，正史类以「取材」形式给史料）。展示：**选中即见**——只选大类说大类解读，选了子类换成子类解读 + 案例（`.cap-note`，未选不占位）；每颗胶囊另带 `title` 悬停提示。**两项缺一不可**（对拍测试逐项断言非空）。
- **口味胶囊 SHALL 移到 02 格**作「常见口味」快捷填充（原名「题材口味胶囊」名不符实：它填的是 02-05，不是题材）：一次预填 02/03/04/05，各格可改；**SHALL NOT** 覆盖 01 已选的题材。
- 每格 SHALL 有编号 + 名称 + 「怎么填」提示 + 成书视角去处说明（m-use）。
- 题材右栏 SHALL 为同款「AI 写作助手」卡片：五行字段（对应 **02-06** 六格/契约字段；01 题材目录为直接选择、不走 AI、**计入**确认判据），各行名称上/描述下（含本格问题 + 输入来源）/右箭头，各答各题。**六格→路由 field→契约字段映射**：02 主要看什么↔core_promise(+promise_note，仅入契约不设 AI 行)；03 绝对禁止↔forbidden_list；04 吃苦指数↔cost_ratio；05 主线战场↔battlefield；06 剧情轨道↔track。
- 点某行，反馈 SHALL 落到**左侧对应字段输入框正下方**的结果区（.ai-sink），采纳才写回对应控件；AI 建议按字段返回**强类型出参**（cost_ratio 为 1-10 数值、forbidden_list 为 `[{tagId|text}]`、battlefield 为数组、core_promise 为 `{value:enum|custom, note:读者预期句}`、主要看什么/剧情轨道为文本）。
- 题材的枚举/标签类字段（core_promise、forbidden_list、battlefield）SHALL 有**候选来源**：由 9. 共享候选源给出候选清单（core_promise 枚举值、forbidden_list tagId 目录、battlefield 候选），模型从中选或走 custom，前端「采纳才写回并映射 tagId」。
- **写回语义**（设计见 D16）：单值文本/数值**覆盖**（按钮「采纳 · 覆盖」）；列表（forbidden_list/battlefield）**覆盖整个列表**（不追加——O-6）；AI 返回无法映射 tagId 的文本落为 `custom`（不丢弃）；**01 取消选择不回滚**已填各格（O-15）。
- 题材定义 SHALL 收口为：题材 = 读者预期 + 作者轨道 + 核心冲突的类型锁（提示帮助中的措辞）。
- **纯新契约连带**（写作引擎配置去留）：推翻 genre_id 后，老 GenreSettingForm 落盘的 `genre_id + config_overrides(fulfillment_types/chapter_types/pacing_rules/fatigue_words) + selected_arc_id + prompt_injection_enabled + taboos` 这批写作引擎题材配置必须有明确去留——语义相近的迁移为新契约字段（fulfillment_types→core_promise、taboos→forbidden_list、typicalArc/storyArcTemplates→track），纯写作引擎/随 GenrePicker 退役的显式移除并评估，**不得静默丢弃**影响写作引擎 AI 口味/节奏/注入的配置。

#### Scenario: 三种口味快捷填充（02 格）
- Given 题材面板，已选 01 题材「仙侠/修真」
- When 点 02 格的「逆袭打脸」
- Then 主要看什么/绝对禁止/吃苦指数/主线战场 预填推荐值，均可改可清
- And 01 已选的题材不被覆盖

#### Scenario: 题材目录两级选择
- Given 打开题材面板
- When 点大类「仙侠/修真」
- Then 出现其子类行（古典仙侠/凡人流/仙魔大战/种田修仙），可单选
- And 换点「科幻」时，若原先选了「凡人流」，该子类被清掉（不属于科幻）

#### Scenario: 每项都有解读与案例
- Given 打开题材面板（未选题材）
- When 点大类「仙侠/修真」
- Then 下方给出该大类的解读（「以修行阶次与道法体系为骨架…」）
- When 再点子类「凡人流」
- Then 解读换成子类的（「主角资质平平，靠算计…」）并附案例「《凡人修仙传》」
- And 每颗胶囊悬停也都给出对应解读与案例

#### Scenario: 未知题材被拒
- Given 客户端提交一个不在目录内的大类名
- When 保存题材
- Then 后端 400 拒绝（「未知的题材」），不落库

#### Scenario: 题材 AI 反馈落对应字段下方
- Given 题材面板
- When 点「主要看什么」的 AI 行
- Then 建议出现在左侧「主要看什么」输入框正下方结果区，采纳写回该文本框

### Requirement: 免费版（无套餐）AI 可见 + 锁定
- 无套餐用户 SHALL 仍可看到「AI 写作助手」卡片，但其为**可见 + 锁定**：整体降透明、PRO 徽标转灰、各能力行降透明且不可点（cursor:not-allowed），每行名称/描述仍可见。
- 点击锁定行 SHALL 给统一升级提示（「这是会员功能，升级 PRO 后解锁——免费版写作能力完整」），SHALL NOT 各自弹窗。
- 免费版写作能力 SHALL 完整（人工路径零差异）。

#### Scenario: 免费版 AI 卡片锁定
- Given 无套餐用户进入简介/题材设定
- When 查看 AI 写作助手卡片
- Then 三个/五行能力可见但整体降透明、点击给升级提示、不生成结果

### Requirement: 本书模型设定（AI 前置）
- **模型配置＝人工路径能力，不锁会员**：免费版 SHALL 也能看到「本书模型」步、也能配置（选 API 配置 + 模型）——免费版与 PRO/MAX 的差别**只在右侧 AI 助手**（免费版全灰、升级引导）。
- 用该书的任何 AI 能力（简介/题材助手、章写作等）前，SHALL 先在本书选定 API 配置 + 模型（复用 `ModelSettingForm`/`useModelStatus`，落 `project.ai_config_id` + `project.ai_model`）；**就绪判据见「AI 就绪状态的单一事实源」（四条件）**。配好的模型在升级 PRO 后 SHALL 直接可用（不必重配）。
- 模型选择控件 SHALL 为**按 API 配置分组的卡片列表**（组头＝配置名 + 供应商 + 连接状态徽标；组内模型行可点、单选、选中态 accent + 勾），支持**多供应商 × 多模型**；SHALL NOT 用原生 `<select>`/optgroup（撑不住多供应商×多模型、且不符全页设计语言）。**单选语义**：容器 `role="radiogroup"` + 行 `role="radio"`/`aria-checked`（对齐仓库既有 `StoryArcForm` 的 role/aria 语义；注意它无键盘导航先例、且是「再点取消」toggle 语义——模型单选不可照抄）；**键盘导航须新增**（roving tabindex + 方向键 + Home/End）。**选择与生效分离**：点模型行只标亮选中态（不落库），点「设为本书模型」才 `selectModel` 落库——防误触（该书全书 AI 走这个模型）；未选模型时确认键禁用；确认后按钮回禁用、再改再启用。**空态**（有 Key 但未拉到模型）SHALL 给「去「模型配置」补模型」引导，不空白。
- **免费版「已配好但 AI 仍灰」**：模型窗对已配置的免费用户 SHALL 提示「模型已配好 · 升级 PRO 后本书 AI 即可用」，不得说「本书 AI 就绪」。
- **API Key 的增删改同样不锁会员**（现状 `api_configs` 路由零门控）；SHALL NOT 给模型配置/Key 管理加会员门控（后续误加会关掉免费版的人工路径能力）。
- 模型步 SHALL NOT 进入 `SETTINGS_ITEMS`（不参与 readiness/设定完成度判定、不占「确认即前进」序列），它是 AI 前置引导步（会员用 AI 的第①步；免费版可先配好）。
- 未选本书模型的（会员），该书 AI 能力 SHALL 不可用：后端以独立 dependency `require_novel_model(novel_id, user, db)` 校验（与 `require_ai_access` 并列挂载，会员在前），未就绪返回 **503 `detail={reason:"missing_model", message:"先在本书选择模型"}`**（前置未满足、**不可当瞬时故障重试**）。
- **三种前置 SHALL 可分流**（前端按 `detail.reason` 分派文案与跳转，不得一色 toast；分派顺序 member_required → no_key → missing_model）：
  | 场景 | 状态码 | detail.reason | 文案 | 跳转 |
  |---|---|---|---|---|
  | 非会员（免费/过期） | 403 | `member_required` | 升级 PRO / 试用 | 升级入口 |
  | 会员但无可用 Key（含 invalid※） | **503**（保持现有码，前端 503 提示链路不可改 403） | `no_key` | 先去「模型配置」添加 API Key | 模型配置 |
  | 会员 + 有 Key + 本书未选模型 | 503 | `missing_model` | 先在本书选择模型 | 本书模型设定 |

  ※ `invalid` **由判定层下发**（配置已删 / `model ∉ config.models` / R8 删除残留），非前端派生。**结构化 detail 全链路**：`api.ts` 503 分支须按 `detail.reason` 分流（`no_key`/`missing_model` 不进 infra 全局提示）并透传 `e.reason`；`ai.ts` 两处 fetch 统一取 `detail.message`（否则对象 detail 变 `[object Object]`）。
- C端 AI 端点（简介/题材/章写作等）SHALL 走 `get_ai_client_for_novel(novel_id)`（读本书模型；`chat` 经 `resolve()` 落到本书模型），不复用全局 `get_ai_client()`（其不感知本书模型）；**全仓库调用点逐一替换（实测 14 处：替换 12 + 豁免 2）**，含章纲起草/提示词润色/归档摘要；**建书预填 `ai_prefill` 豁免**（早于选模型，降级为无 AI 或用户默认模型）。**双模型源权威链**：`project.ai_model` 为唯一权威，`writing_model` 仅允许 `haiku/sonnet` 别名（经 `resolve()` 映射），显式模型名一律忽略。**`polish_text`/`expand_text`/`archive_chapter` 须补 `novel_id` 参数**（现签名拿不到）。构造失败（配置已删/解密失败）须优雅返回，不裸 500。**写作页兜底另立 change**（本 change 只保证设置视图 AI 行的文案与跳转）。
- 前端 AI 行点击 SHALL 走统一门控函数（优先级：非会员→升级 / 本书模型未就绪→跳模型设定 / 无可用 Key→跳模型配置 / 就绪→调用）；**门控只作用于 AI 助手行，不拦模型配置本身**（免费版可选模型）。就绪判据＝**后端 `ai_state === "ready"`**（前端不推导）。

#### Scenario: 免费版可看可配模型、AI 助手全灰
- Given 免费版用户进入设定
- When 查看「本书模型」步与右侧 AI 助手
- Then 模型步可见、可选模型（配好保留），而右侧 AI 助手整卡灰、点击给升级提示

#### Scenario: 会员未选模型则 AI 不可用
- Given PRO/MAX 本书未设模型（ai_config_id/ai_model 为空）
- When 作者点简介「AI 体检」
- Then 不生成结果，提示「先在本书选择模型」并跳本书模型设定

#### Scenario: 已选本书模型 AI 可用
- Given PRO/MAX 本书已选 API 配置 + 模型
- When 作者点简介「AI 体检」
- Then 用本书模型生成体检结果

#### Scenario: 无可用 Key 与未选模型分流
- Given 会员但未配任何 API Key
- When 作者点简介「AI 体检」
- Then 提示「先去「模型配置」添加 API Key」（reason=no_key），而非「先在本书选择模型」

### Requirement: AI 就绪状态的单一事实源
- 「本书 AI 是否就绪」SHALL 由**后端一次判定、前端只消费**，SHALL NOT 由前端用本地配置列表自行推导（消除前后端判据漂移）。
- `GET /novels/{id}/ai-model` SHALL 扩展返回 `{ api_config_id, model, config_name, ai_state, effective_model, reason?, message? }`：
  - `ai_state ∈ {ready, member_required, no_key, missing_model, invalid}`（**与 `detail.reason` 同枚举**）——**覆盖「AI 为什么不可用」的全部原因**，前端门控只读这一个字段、一次分派（不再 `useFeature` + `ai_state` 两处判）；判定优先级 `member_required > invalid > no_key > missing_model > ready`。`member_required` 只拦「调用 AI」，**不拦模型配置本身**。
  - `ready` 判据 SHALL 为：`ai_config_id` 与 `ai_model` 均非空 **且 本书绑定的配置存在** **且 该配置有可用 Key** **且 `ai_model ∈ json.loads(config.models)`**（与绑定校验共用同一谓词——`refresh-models` 后旧模型被移除不得再报 ready）。
  - `no_key` 粒度 SHALL 为**本书绑定配置级**（非「用户任意配置有 Key」）。
  - `effective_model` SHALL 为按权威链算出的实际生效模型（`project.ai_model` 唯一权威），前端只显示、不推导。
- 前端 `useModelStatus` SHALL 删除本地四态推导，直接消费 `ai_state`/`effective_model`；AI 行门控按 `ai_state` 分派；错误兜底的 `detail.reason` SHALL 与 `ai_state` **共用同一枚举**（`no_key`/`missing_model`/`invalid`）。

#### Scenario: 前后端判据不再漂移
- Given 某书 `ai_config_id` 有值但 `ai_model` 为空
- When 查看该书 AI 就绪状态
- Then 后端下发 `ai_state="missing_model"`，前端据此拦在「先选模型」，不会放行调用（不再出现「前端放行、后端 503」）

#### Scenario: 配置已删的 invalid 由后端判定
- Given 某书绑定的 API 配置已被删除
- When 查看该书 AI 就绪状态
- Then 后端下发 `ai_state="invalid"`（不再是仅前端派生态）

#### Scenario: 模型被刷新移除后不再报就绪
- Given 本书绑定模型 x，其后配置的模型列表刷新且不再含 x
- When 查看该书 AI 就绪状态
- Then `ai_state` 不再为 `ready`（`model ∈ config.models` 谓词生效）

### Requirement: 后端模型调用分层
- C端后端模型调用 SHALL 分层且边界可验证：**配置层**（`api_configs/`，存配置/测连接/记用量）→ **解析层**（`effective_model`，`project.ai_model` 唯一权威）→ **判定层**（`compute_ai_state`，单一事实源）→ **客户端层**（`ai_client.py`，构造连接、调用、按 `api_format` 落地 `json_mode`）→ **门控层**（`require_ai_access` + `require_novel_model`，判据复用判定层）→ **业务层**（`write/`/`settings/`/`chapters/`/`prompt/`/`archive/`/`story/`/`novels/`）→ **prompt 层**（模型无关模板）→ **计量层**（记实际模型 id）。
- 边界 SHALL 分「可 grep 门禁」与「review 清单」：
  - **可 grep**：① 业务层禁裸 `get_ai_client()`——`grep -rnE '\bget_ai_client\(' client/backend --include='*.py' | grep -vE 'ai_client\.py|/tests/|ai_prefill\.py|novels/router\.py|__pycache__|\.mimosa' | grep -vE '^\S+:[0-9]+:\s*#'` 须为空（豁免：`ai_client.py` 定义、`tests/`、`ai_prefill.py`、`novels/router.py` suggest-meta）；② `record_usage` 记实际模型 id（`grep -rn 'model="haiku"'` + 各调用点核对）；③ 门控违规近似 `grep -rnE 'check_permission\(|is_member' client/backend/{write,settings,chapters,prompt,archive,story,novels}` 须为空。
  - **review 清单**（不可 grep）：① 业务层是否直读 `writing_model` 决定模型；② 门控是否只在 dependency 且判据复用判定层；③ 就绪状态是否只在判定层。
- 调用点 SHALL 全仓库替换（实测 14 处）：`write/router.py:62,179`、`write/auxiliary.py:157,217,252`、`settings/ai_router.py:50`、`chapters/ai_draft.py:259`、`prompt/router.py:46`、`archive/service.py:46`、`story/arc_wizard.py:61`、`story/character_agent.py:250`、`story/engine.py:201`；豁免 `ai_prefill.py:26`、`novels/router.py:154`（建书期，无 project 上下文）。
- **建书期降级链显式化**：有书 SHALL 一律用 `effective_model`；**无书路径仅限 `ai_prefill`/`suggest_meta`**（建书期），走**显式**降级链「用户首个 active 配置的 `models[0]`」（文档化规则、非 `models_list[0]` 隐式），并标注「建书期降级模型」；**业务层其余路径 SHALL NOT 使用 `get_ai_client_for_user`**（只准 `get_ai_client_for_novel`）。**「建书期」判定规则**（O-19）：以**调用点是否持有 novel_id/novel 对象**为准（无 project 上下文者＝建书期），不依赖 phase 字段；`suggest_meta` 与 `ai_prefill` 同列豁免。

#### Scenario: 业务层不得绕过客户端层
- Given 任一 C端 AI 端点
- When 静态检查其客户端获取方式
- Then 只出现 `get_ai_client_for_novel(novel_id)`，无裸 `get_ai_client()`（`ai_prefill.py` 除外）

#### Scenario: 模型权威链不可穿透
- Given `writing-style.yaml` 的 `writing_model` 写了具体模型名
- When 该书的 AI 调用取模型
- Then 仍以 `project.ai_model`（经解析层 `effective_model`）为准，字面覆盖被忽略

### Requirement: 模型选择的三层粒度与绑定
- **粒度**：供应商/API 配置 SHALL 为 **C端用户级**（一次配置、所有书共用同一批供应商）；模型 SHALL 为 **书级**（一本书一个，全书所有 AI 助手共用同一 `effective_model`——简介三能力、题材五行、章写作/续写、章纲起草、提示词润色、归档摘要）；提示词/能力 SHALL 为 **页面级**（每助手一套模板，模板**模型无关**、不写模型名）。
- **绑定**：模型与其供应商 SHALL 绑定——`project.ai_config_id` 与 `project.ai_model` 须来自**同一配置**；后端 `set_project_model`（函数名以现状为准）SHALL 校验 `model ∈ json.loads(config.models)`（处理 JSON 文本/`None`/空串/非法 JSON），**空列表拒绝**、**部分 null 拒绝**（不成对即拒，除非显式 clear）；失败返 **400**（Pydantic 缺字段才 422）。**跨配置混搭在 UI 上不可达**（每行携带所属配置）；**组内换模型＝同配置换 model，允许**。前端确认键遇 400 SHALL **保留 draft 选中态 + 行内报错**（不清空、不禁用）。
- **存量错配与失效边界**（流程审查 O-7/O-8）：`ai_model` 存在但**不在**该配置 `models` 列表（存量/手工改库）时，`ai_state` SHALL NOT 为 `ready`（**已定：并入 `invalid`**，不派生第 6 个枚举值），前端按「重选模型」引导——D12 校验只挡写入、不挡存量读取，须在判定层兜住。**配置被删且用户无其他可用配置**时 SHALL NOT 死路：模型窗须给「去「模型配置」新建配置」入口（而非仅隐藏选择区）。
- **清除本书模型**（O-12）：`(None, None)` 的显式 clear SHALL 被支持（API 层保留现有 `change_type="clear"` 语义）；**UI 不提供「清除」入口**（仅 API 保留），且**不得**让 `(config_id, None)`/`(None, model)` 这种**不成对**状态落库。
- 换模型 SHALL 对全书 AI 助手同时生效（一处改、全书生效）。
- **页面级调用参数（本清单即参数表，design D12 引用它）** SHALL 与 prompt 一并页面化：JSON 判定类（`introspect`/`fill`/`settings_genre_{field}`）`temperature ≤ 0.3`、`max_tokens` 足量（≥2048，防 introspect 六段+禁忌+verdict 被截断）；长文生成类（章写作/续写/章纲）`0.7–1.0`、`max_tokens 4000`。`AIClient.chat` SHALL 支持透传 `temperature`。
- **`json_mode` 分层归属**：业务层 SHALL 只传语义参数 `json_mode: bool`；SHALL NOT 直接传 provider 专有参数（`response_format`）——由客户端层按 `api_format` 决定是否落地（Anthropic 分支忽略，否则 400），不支持者靠 prompt + 归一化兜底。
- **模型能力门槛**：本书模型 SHALL 支持 system 消息与 ≥8k 上下文；不支持 JSON mode 的模型由归一化兜底并给**非阻断**提示。

#### Scenario: 模型与供应商绑定、不可混搭
- Given 用户选了配置 A 的模型 x
- When 保存本书模型
- Then 存为 `(A, x)`；若传 `(A, y)` 而 y 不属于 A 的模型列表，则拒绝（400/422）

#### Scenario: 全书 AI 共用同一模型
- Given 本书选了模型 x
- When 分别调简介体检 / 题材五行 / 章写作
- Then 三者都走 x（`effective_model` 全书唯一）

- **幂等性**：同值重复写 SHALL 幂等——`PUT /novels/{id}/ai-model` 重复提交同 `(config_id, model)` → 均 200、状态不变、**审计不重复写**；`PUT /settings/story`/`PUT /settings/genre` 重复提交同 payload → 幂等；`PUT /settings/status/{type}` 重复 confirm → 幂等；**AI 重试/换候选不重复计 usage**。
- **边界与等价类**：`synopsis` 界 **500**（0/1/499/500/501，**501 尾部截断**——与 D16「500 字截断」一致）；`cost_ratio` 界 **[1,10]**（0/11 拒）；模型列表 0/1/多（0 → 任意 model 拒）；空串/纯空白/`None` SHALL 视为「未填」（三者等价，不得只判 `None`）。

- **存储（D19 关系化，取代 D17 的 KV 方案）**：题材 SHALL 落 `novel_genre` + 关联表（4 张表，见下「题材 SHALL 存关系表」条）；`project_settings('genre')` 行 SHALL 废弃（不再读写）；**无迁移**（无 C 端用户，存量库指纹不匹配→留档重建）。**写作注入 SHALL 同批重写**：`resolve_genre_context` 须改读五字段，否则 `build_genre_section` 恒空且**无报错**（静默降级，正文质量悄悄变差）；**且 SHALL 带上 01 题材目录**（`题材：大题（子类）` 一行，同读 `story.yaml`）——01 是「定了就不跑偏」的类型锁，只注入 02-06 会让模型不知道书是什么题材。**`genres` 表 SHALL NOT 被本 change 修改**（仅停用 `genre_id` 引用）。候选源 SHALL 由 `GET /api/genres/candidates` 下发（前后端镜像需 parity）。**`settings/ai-model.yaml` 为确认标记行，SHALL NOT 写入 `ai_state`**。**R9**：`writing-style.yaml` 的 `genre_profile` SHALL 停用或明确仅作展示名，不得与五字段并存为两个题材源。**禁止新增未路由的 storage 路径**（会静默落盘、破坏「数据全在 DB」）。
- **R8 删除残留**：删 ApiConfig 后 `ai_config_id` 被置空而 `ai_model` 保留 → `ai_state` SHALL 判 `invalid`（非 `missing_model`/ready）。

### Requirement: 简介/题材字段数据契约
- 简介 SHALL 存储 `{ synopsis: string, ≤500 }`（`PUT /settings/story`）。
- **题材目录（01 格）SHALL 落 `story.yaml`**（用户 2026-09-10 拍板）：大类名存**既有 `genre` 键**（书卡胶囊/书内标签的展示链一直读它）、子类名存新键 `sub_genre`；`GET/PUT /novels/{id}/settings/genre` 的对外契约 SHALL 含 `theme`/`sub_genre` 两字段，**存储位置对前端透明**（面板一次取全、一次保存）。**理由**：题材目录是与简介同族的单值书级元数据（同文件、已有 `genre` 键），不是多值关系；**另立关系表意味着改 schema → 触发 C端 启动期指纹留档（用户库被改名重建，实打实的数据丢失）**，而简介真源本来就在 `story.yaml`。**键存在才写**：PUT 未带 `theme`/`sub_genre` 键时 SHALL NOT 改动既有值（老调用方只 PUT 五字段不得清空题材）。
- **题材目录（封闭目录）SHALL 以中文名为存储值**：不另造 slug-id（名字即稳定键，免 id↔名两处漂移）；写入 SHALL 按目录校验，未知大类/跨类子类 → 400（「未知的题材」/「没有这个子类」）。
- 题材 SHALL 存**关系表**（方案 A，D19）：`novel_genre`（`novel_id` 主键、`core_promise VARCHAR(60)`、`promise_note VARCHAR(200)`、`cost_ratio INTEGER CHECK 1–10`、`track VARCHAR(300)`）+ `novel_genre_forbidden` / `novel_genre_battlefield`（关联表，`vocab_id` FK→`genre_vocab` 或 `custom_text`，CHECK 恰一；`UNIQUE(novel_id, vocab_id)`）。**候选源 SHALL 为 `genre_vocab` 表**（稳定 slug 主键、`kind`/`label`/`sort`/`is_preset`），**tagId SHALL 为稳定 slug**（如 `forbidden:no-deus-ex-machina`），**SHALL NOT 用 `preset:{id}:{index}` 这类随顺序漂移的编号**。**空值统一**：`null`/`""`/纯空白/无关联行 等价视为未填。`project_settings('genre')` 行 SHALL 废弃。
- **实体命名统一（D20）**：DB 表 `projects` SHALL 改名 `novels`、列 `project_id` SHALL 改名 `novel_id`（含 `chapters`/`volumes`/`token_log`/`project_model_audit_log` + 新表 FK）；后端 URI `/api/v1/projects/*` SHALL 改 `/api/v1/novels/*`（无外部消费者，不留别名）；前端 `/projects/...` 残留同批改。**理由**：一物三名已收敛两处（类名 `Novel`、路由 `/novels`），表名是唯一残留；Change C D1 原判「不动」的前提（有已分发数据）已因「无 C 端用户」失效。
- 题材确认判据 SHALL 由「genre_id 非空」改为「**已选题材目录大类 或 新契约核心键非空**」（`core_promise`/`forbidden_list`/`cost_ratio`/`battlefield`/`track` 至少一非空；`readiness._check_genre` 同步改）——01 格问的就是「什么题材」，只选了题材也算题材已定，否则作者会被自己答的第一问卡住。
- **六格↔字段↔契约映射** SHALL 固定：01 题材目录↔`theme`+`sub_genre`(story.yaml)；02 主要看什么↔core_promise(+promise_note，仅入契约不设 AI 行)；03 绝对禁止↔forbidden_list；04 吃苦指数↔cost_ratio；05 主线战场↔battlefield；06 剧情轨道↔track。
- **候选源** SHALL 提供 core_promise 枚举值、forbidden_list 的 tagId 目录、battlefield 候选清单（新建共享候选源，不复用 presets 现成键），供题材 AI 从中选或走 custom、前端「采纳写回并映射 tagId」。
- AI 辅助的字段说明、**六段名与禁忌三元** SHALL 注册进**共享常量模块**（prompt 模板与前端渲染共用）；注：`fieldGuide`/`settings-ai-qa` **本仓库不存在**，属待建——本 change 以共享常量模块落地，不依赖未建系统。
- 简介/题材 AI 能力 SHALL 由 **C端后端** `settings/ai_router.py` 承载：扩展（`FIELD_GENERATABLE` 加 `genre`、新增 `settings/ai/intro/{action}` 子路由且**注册在 `/ai/{stype}/{field}` 之前**、`settings_intro_{action}`/`settings_genre_{field}` prompt 模板）、挂 `require_ai_access`、`record_usage` 按 `settings_{stype}_{action|field}` 细分——非 S端、不引入独立服务。

#### Scenario: 题材 payload 键控
- Given 作者选了题材大类「仙侠/修真」+ 子类「凡人流」、禁项、吃苦 8、战场 2 个
- When 保存
- Then `story.yaml` 落 `genre: 仙侠/修真` + `sub_genre: 凡人流`，关系表落 core_promise/forbidden_list/cost_ratio:8/battlefield 两个值，空字段省略；无 genre_id

#### Scenario: 题材确认基于新契约
- Given 题材已填 core_promise（未填 genre_id）
- When 查看设定状态
- Then 题材判定为已确认（判据为已选题材目录或新契约核心键非空，而非 genre_id）

### Requirement: 题材的对外展示（书卡胶囊与书内标签）

- 书本上的题材展示位（书架卡片胶囊、书内标签）**SHALL 取值来自题材**（用户 2026-09-10 拍板「书的类型胶囊，取值从题材获取」），**SHALL NOT** 依赖已废弃的历史来源：建书弹窗的「类型」下拉与题材面板的 `genre_id` 都已不再写入，旧展示链（`story.yaml.genre` 的旧语义 / `project_settings('genre')` KV）对本 change 之后的书恒为空。
- 展示名 SHALL 取**题材目录**（01 格）：`主题大类 · 子类`（子类为空则只显示大类），由后端在 `GET /novels`（`genre` 字段）与 `GET /novels/{id}`（`genre_label` 字段，另下发 `theme`/`sub_genre`）**单源下发**；两端 SHALL NOT 各自拼装。
- 题材目录缺失时 SHALL 依次回退：老书核心承诺 → 老书 `story.yaml.genre`(旧值) → KV 题材名。
- **占位**：题材未设定（题材目录为空、且无历史来源可回退）时 SHALL 显示「**待定题材**」（共享常量 `GENRE_PENDING_LABEL`，前端两侧同源），**SHALL NOT** 空缺该展示位——空位会让作者以为界面漏了东西。
- 展示名可能长于展示位 → 展示位 SHALL 单行截断，SHALL NOT 撑破卡片顶栏。

#### Scenario: 选完题材后胶囊显示大类·子类
- Given 作者在题材面板选了「仙侠/修真」+「凡人流」
- When 回到书架
- Then 该书卡片的题材胶囊显示「仙侠/修真 · 凡人流」

#### Scenario: 只选大类也能显示
- Given 作者只选了题材大类「悬疑」、未选子类
- When 查看书架卡片或打开这本书
- Then 题材展示位显示「悬疑」

#### Scenario: 题材未设定时占位
- Given 一本刚创建、题材未选的书
- When 查看书架卡片或打开这本书
- Then 题材展示位显示「待定题材」（不是空缺、也不是「其他」）

#### Scenario: 老书题材展示不回归为空
- Given 一本建书时写入过旧 `story.yaml.genre`（如「科幻」）的老书，且题材目录与关系表均无数据
- When 查看书架卡片或打开这本书
- Then 题材展示位仍显示「科幻」

## MODIFIED Requirements

（无 — 本 capability 为新增，无既有需求被修改。）
