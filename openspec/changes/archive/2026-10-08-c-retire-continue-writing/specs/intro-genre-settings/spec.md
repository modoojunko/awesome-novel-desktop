## MODIFIED Requirements

### Requirement: 模型选择的三层粒度与绑定
- **粒度**：供应商/API 配置 SHALL 为 **C端用户级**（一次配置、所有书共用同一批供应商）；模型 SHALL 为 **书级**（一本书一个，全书所有 AI 助手共用同一 `effective_model`——简介三能力、题材五行、章写作、章纲起草、提示词润色、归档摘要）；提示词/能力 SHALL 为 **页面级**（每助手一套模板，模板**模型无关**、不写模型名）。
- **绑定**：模型与其供应商 SHALL 绑定——`project.ai_config_id` 与 `project.ai_model` 须来自**同一配置**；后端 `set_project_model`（函数名以现状为准）SHALL 校验 `model ∈ json.loads(config.models)`（处理 JSON 文本/`None`/空串/非法 JSON），**空列表拒绝**、**部分 null 拒绝**（不成对即拒，除非显式 clear）；失败返 **400**（Pydantic 缺字段才 422）。**跨配置混搭在 UI 上不可达**（每行携带所属配置）；**组内换模型＝同配置换 model，允许**。前端确认键遇 400 SHALL **保留 draft 选中态 + 行内报错**（不清空、不禁用）。
- **存量错配与失效边界**（流程审查 O-7/O-8）：`ai_model` 存在但**不在**该配置 `models` 列表（存量/手工改库）时，`ai_state` SHALL NOT 为 `ready`（**已定：并入 `invalid`**，不派生第 6 个枚举值），前端按「重选模型」引导——D12 校验只挡写入、不挡存量读取，须在判定层兜住。**配置被删且用户无其他可用配置**时 SHALL NOT 死路：模型窗须给「去「模型配置」新建配置」入口（而非仅隐藏选择区）。
- **清除本书模型**（O-12）：`(None, None)` 的显式 clear SHALL 被支持（API 层保留现有 `change_type="clear"` 语义）；**UI 不提供「清除」入口**（仅 API 保留），且**不得**让 `(config_id, None)`/`(None, model)` 这种**不成对**状态落库。
- 换模型 SHALL 对全书 AI 助手同时生效（一处改、全书生效）。
- **页面级调用参数（本清单即参数表，design D12 引用它）** SHALL 与 prompt 一并页面化：JSON 判定类（`introspect`/`fill`/`settings_genre_{field}`）`temperature ≤ 0.3`、`max_tokens` 足量（≥2048，防 introspect 六段+禁忌+verdict 被截断）；长文生成类（章写作/章纲）`0.7–1.0`、`max_tokens 4000`。`AIClient.chat` SHALL 支持透传 `temperature`。
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
