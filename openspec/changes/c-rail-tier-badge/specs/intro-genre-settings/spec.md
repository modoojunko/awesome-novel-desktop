## MODIFIED Requirements

### Requirement: 免费版（无套餐）AI 可见 + 锁定

- 无套餐用户 SHALL 仍可看到「AI 写作助手」卡片，但其为**可见 + 锁定**：整体降透明、档位角标转灰（角标文案随套餐）、各能力行降透明且不可点（cursor:not-allowed），每行名称/描述仍可见。
- 点击锁定行 SHALL 给档位感知的统一升级提示（文案出自单源 helper、按该行 feature key 的最低档出口径——免费用户提示「开通解锁」类；SHALL NOT 硬编码「升级 PRO」字面量：标准档已解锁的件对免费用户不得误导为「升级 PRO」，MAX 件须出 MAX 口径），SHALL NOT 各自弹窗；统一拦截弹窗的标题 SHALL 与档位无关（「升级套餐解锁」），档位口径只出现在提示正文。
- 免费版写作能力 SHALL 完整（人工路径零差异）。

#### Scenario: 免费版 AI 卡片锁定

- Given 无套餐用户进入简介/题材设定
- When 查看 AI 写作助手卡片
- Then 三个/五行能力可见但整体降透明、点击给档位感知升级提示、不生成结果

### Requirement: 本书模型设定（AI 前置）
- **模型配置＝人工路径能力，不锁会员**：免费版 SHALL 也能看到「本书模型」步、也能配置（选 API 配置 + 模型）——免费版与会员档（标准起）的差别**只在右侧 AI 助手**（免费版全灰、升级引导）。
- 用该书的任何 AI 能力（简介/题材助手、章写作等）前，SHALL 先在本书选定 API 配置 + 模型（复用 `ModelSettingForm`/`useModelStatus`，落 `project.ai_config_id` + `project.ai_model`）；**就绪判据见「AI 就绪状态的单一事实源」（四条件）**。配好的模型在开通/升级套餐后 SHALL 直接可用（不必重配）。
- 模型选择控件 SHALL 为**按 API 配置分组的卡片列表**（组头＝配置名 + 供应商 + 连接状态徽标；组内模型行可点、单选、选中态 accent + 勾），支持**多供应商 × 多模型**；SHALL NOT 用原生 `<select>`/optgroup（撑不住多供应商×多模型、且不符全页设计语言）。**单选语义**：容器 `role="radiogroup"` + 行 `role="radio"`/`aria-checked`（对齐仓库既有 `StoryArcForm` 的 role/aria 语义；注意它无键盘导航先例、且是「再点取消」toggle 语义——模型单选不可照抄）；**键盘导航须新增**（roving tabindex + 方向键 + Home/End）。**选择与生效分离**：点模型行只标亮选中态（不落库），点「设为本书模型」才 `selectModel` 落库——防误触（该书全书 AI 走这个模型）；未选模型时确认键禁用；确认后按钮回禁用、再改再启用。**空态**（有 Key 但未拉到模型）SHALL 给「去「模型配置」补模型」引导，不空白。
- **免费版「已配好但 AI 仍灰」**：模型窗对已配置的免费用户 SHALL 提示「模型已配好 · 开通套餐后本书 AI 即可用」，不得说「本书 AI 就绪」。
- **API Key 的增删改同样不锁会员**（现状 `api_configs` 路由零门控）；SHALL NOT 给模型配置/Key 管理加会员门控（后续误加会关掉免费版的人工路径能力）。
- 模型步 SHALL NOT 进入 `SETTINGS_ITEMS`（不参与 readiness/设定完成度判定、不占「确认即前进」序列），它是 AI 前置引导步（会员用 AI 的第①步；免费版可先配好）。
- 未选本书模型的（会员），该书 AI 能力 SHALL 不可用：后端以独立 dependency `require_novel_model(novel_id, user, db)` 校验（与 `require_ai_access` 并列挂载，会员在前），未就绪返回 **503 `detail={reason:"missing_model", message:"先在本书选择模型"}`**（前置未满足、**不可当瞬时故障重试**）。
- **三种前置 SHALL 可分流**（前端按 `detail.reason` 分派文案与跳转，不得一色 toast；分派顺序 member_required → no_key → missing_model）：
  | 场景 | 状态码 | detail.reason | 文案 | 跳转 |
  |---|---|---|---|---|
  | 非会员（免费/过期） | 403 | `member_required` | 开通套餐 / 试用 | 升级入口 |
  | 会员但无可用 Key（含 invalid※） | **503**（保持现有码，前端 503 提示链路不可改 403） | `no_key` | 先去「模型配置」添加 API Key | 模型配置 |
  | 会员 + 有 Key + 本书未选模型 | 503 | `missing_model` | 先在本书选择模型 | 本书模型设定 |

  ※ `invalid` **由判定层下发**（配置已删 / `model ∉ config.models` / R8 删除残留），非前端派生。**结构化 detail 全链路**：`api.ts` 503 分支须按 `detail.reason` 分流（`no_key`/`missing_model` 不进 infra 全局提示）并透传 `e.reason`；`ai.ts` 两处 fetch 统一取 `detail.message`（否则对象 detail 变 `[object Object]`）。
- C端 AI 端点（简介/题材/章写作等）SHALL 走 `get_ai_client_for_novel(novel_id)`（读本书模型；`chat` 经 `resolve()` 落到本书模型），不复用全局 `get_ai_client()`（其不感知本书模型）；**全仓库调用点逐一替换（实测 14 处：替换 12 + 豁免 2）**，含章纲起草/归档摘要（原「提示词润色」调用点随 c-retire-prompt-polish 退役）；**建书预填 `ai_prefill` 豁免**（早于选模型，降级为无 AI 或用户默认模型）。**双模型源权威链**：`project.ai_model` 为唯一权威，`writing_model` 仅允许 `haiku/sonnet` 别名（经 `resolve()` 映射），显式模型名一律忽略。**`polish_text`/`expand_text`/`archive_chapter` 须补 `novel_id` 参数**（现签名拿不到）。构造失败（配置已删/解密失败）须优雅返回，不裸 500。**写作页兜底另立 change**（本 change 只保证设置视图 AI 行的文案与跳转）。
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

### Requirement: 简介「AI 写作助手」（三能力，Pro）
- 简介右栏 SHALL 为一个「AI 写作助手」卡片：头部＝**档位角标**（随套餐：免费版／标准会员／PRO 会员／MAX 会员，文案单源）＋标题「AI 写作助手」＋可选功能性副行（无 Key／缺模型等下一步动作；SHALL NOT 出「已解锁/套餐归属/只加工不代写」这类套餐文案）＋三个**并列**能力行（体检 / 补缺失 / 润色，非先后流程）＋底部来源/去向声明。
- 每行 SHALL 为：能力名称（上）+ 描述（下，从属）+ 右侧箭头，整行可点。
- 体检 SHALL 按四件事检查：① 六段模板逐项查达标/缺失；② 扫禁忌（**设定集腔 / 作者自白 / 剧透**）；③ **标题对照**（书名 ↔ 简介是否互相印证）；④ 结论。**只提醒、不拦确认**；行名与六段模板完全一致。注：禁忌第三元「剧透」与「别踩」第三元「写死结局」**用途不同（扫描规则 vs 写作引导），写死结局 ≠ 剧透，勿合并为同一枚举**。体检为诊断语义，**只分析/只提醒、不补写不改写**。
- 体检接口 SHALL 返回结构化 JSON：`{"six_segments":[{name,status(ok|missing),excerpt,note?}], "taboo":{"hits":[{rule,excerpts}]}, "title_check":{"fit":"ok|mismatch|generic","note":"…","suggestions":["…"]}, "verdict":"strong|ok|weak"}`，其中 `name` 须为六段名之一、`status` 限 `ok|missing`、`fit` 限三值。
- **标题对照语义**（`title_check`）：`ok`＝标题暗示的类型/看点与简介一致；`mismatch`＝不符（如标题像甜宠、简介是压抑复仇）；`generic`＝标题无信息（任何同类型小说都能用，如《第一章》）。`mismatch`/`generic` 时 SHALL 给 `note` 说明理由 + **≤3 条候选标题**（每条 ≤16 字，贴题材、留钩子、不剧透结局）。候选标题 SHALL 仅作参考提示，**SHALL NOT 提供「一键设为书名」入口**——书名改不改、怎么改由作家自己决定（用户拍板 2026-09-10）。**兜底**：模型未返回该字段或 `fit` 非法 → 该字段**不下发**，前端不渲染该行（**不得硬判 `ok`**，避免假绿）。
- **结构化输出策略**（跨供应商/弱模型）：体检/题材的 JSON 输出除 endpoint 后置归一化兜底外，prompt 侧 SHALL 给 **schema + 枚举 + 一个 few-shot 示例**；能用的 provider 追加 `response_format={"type":"json_object"}`（需同步扩 `AIClient.chat` 的 OpenAI 分支）。
- 补缺失 SHALL 只针对缺失段给候选；请求体 SHALL 带 `missing_segments`（前端把 introspect 的 missing 段传来），返回 `{"missing":[{name,candidate}], "act":"insert"}`；**只补缺失段、不重写作者已写段**。候选在弹窗文本卡内逐条呈现，确认才写入简介。**前置**：未先体检时「补缺失」行 SHALL 提示「先体检，才知道缺哪段」（或禁用），不得空跑（O-3）；六段全 ok 时 SHALL 提示「六段都齐了，无需补」（O-16）。
- 润色 SHALL 前后对照（入参 `{title, content}`，返回 `{"original","polished","act":"replace"}`），确认才替换；保原意、只加工不代写。**对照展示形态**＝弹窗文本卡内原句/润后**上下两行**（O-17）。
- **AI 助手交互状态机**：三个能力（体检/补缺失/润色）SHALL 共用同一状态机 `idle → running → result → adopted`（异常走 `error(reason)`）；**「AI 出卡确认弹窗」为其唯一渲染面**。**前置守卫**：补缺失未先体检时该行置灰 + 「先体检」，不空跑（O-3）；**空结果**（六段全 ok 时补缺失）弹窗内显示「无需补」而非空白（O-16）；**生命周期**＝结果只在弹窗内呈现，确认写回后弹窗关闭、直接关闭即弃（不写回、不留面板残留）；「换一个」＝弹窗内重新生成，**生成历史切换退役**（O-5 生命周期随之改口径）；**save 成功但 confirm 400** → 「内容未通过校验」+ 保留 dirty（O-4）。
- **失败文案矩阵**（O-13）：400 →「请求有误，请检查输入」；403 `member_required` → 升级；403 `no_key` → 去模型配置；503 `missing_model` → 去选模型；502/非法 JSON →「暂不可用，请重试」且**不拦确认**；网络异常/超时 →「网络异常，请重试」。**重试不重复计 usage**。
- 点任一能力，生成/体检结果 SHALL 在**弹窗出卡**中呈现（生成类＝文本卡带确认；体检＝只读报告卡，无采纳）；右栏只作按钮、不内嵌答案、面板内不再渲染格下结果区。AI 请求以**当前输入框的 synopsis 为源**（`content`），不读存储旧文；入参含 `title`（书名）。

#### Scenario: 标题与简介不符时给出提示与候选
- Given 书名为《我在夜晚打吸血鬼》（暗示都市奇幻），简介写成压抑宫斗
- When 执行体检
- Then 返回 `title_check.fit="mismatch"` + `note` 说明不符之处 + ≤3 条候选标题
- And 体检报告卡在六段行下方显示「标题对照：与简介不符」+ 理由 + 候选标题

#### Scenario: 标题无信息也提示（不得判为一致）
- Given 书名为《第一章》或《测试》，任何同类型作品都能用
- When 执行体检
- Then 返回 `title_check.fit="generic"` + 候选标题（非 `ok`）

#### Scenario: 弱模型未返回标题对照时不造假绿
- Given 模型输出缺少 `title_check` 或 `fit` 取值非法
- When 归一化体检响应
- Then 该字段不下发、报告卡不渲染标题对照行（**不得**补一个 `ok`）

#### Scenario: 体检六行与模板一致
- Given 简介已输入
- When 作家点「体检」
- Then 弹窗报告卡列出六段逐项 达标/缺失，行名与六段模板一致，且给出禁忌扫描结论

#### Scenario: 反馈落输入框下方而非右栏
- Given 点任一能力
- Then 结果出现在弹窗出卡内，右栏不堆长答案；简介框下方不再出现内嵌结果区（原「落输入框下方」形态随 .ai-sink 退役，确认语义不变——确认才写回）

#### Scenario: 关闭即弃
- Given 补缺失候选已在弹窗内呈现
- When 作者未点确认直接关闭弹窗
- Then 简介原文一个字不动，面板无残留结果
