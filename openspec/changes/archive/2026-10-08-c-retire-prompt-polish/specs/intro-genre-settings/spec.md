## MODIFIED Requirements

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

### Requirement: 模型选择的三层粒度与绑定
- **粒度**：供应商/API 配置 SHALL 为 **C端用户级**（一次配置、所有书共用同一批供应商）；模型 SHALL 为 **书级**（一本书一个，全书所有 AI 助手共用同一 `effective_model`——简介三能力、题材五行、章写作/续写、章纲起草、归档摘要（原「提示词润色」随 c-retire-prompt-polish 退役））；提示词/能力 SHALL 为 **页面级**（每助手一套模板，模板**模型无关**、不写模型名）。
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
