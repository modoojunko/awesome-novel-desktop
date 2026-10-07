# model-api-config Delta — 模型清单自动拉取

## ADDED Requirements

### Requirement: 模型清单自动拉取

系统 SHALL 提供「只拉清单」轻探针：按与连接测试完全相同的端点构造（`openai` 格式 GET `{base}/models`（base 无版本段补 `/v1`）+ Bearer 头；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头；ollama GET `/api/tags`），仅请求模型清单端点，SHALL NOT 发起对话探针（不产生生成调用）。新端点 `POST /api-configs/fetch-models` 接收 raw 配置（vendor/base_url/api_key/api_format，未保存态），返回 `{ok, status, models, candidates?, note?, error?}`。200 响应体非 API JSON（网页等）SHALL 判失败并提示核对 Base URL；anthropic 格式 404 SHALL 返回空清单＋该 vendor 候选 id＋「端点不提供模型列表」说明（与连接测试降级同口径，但不发生成请求）；非 ollama 且 Key 为空 SHALL 判鉴权失败。

创建表单中，API Key 失焦且非空时 SHALL 自动调用轻探针拉取清单（Ollama 免 Key：供应商或 Base URL 确定后即拉）；vendor、Base URL、接口格式变更且 Key 已填时 SHALL 重拉；在途请求 SHALL 去重（不并发重复拉取）。清单到位后模型选择器 SHALL 默认选中「登记表默认模型（若在清单内）→ 否则清单首项」；用户手动改选后 SHALL NOT 被后续自动刷新覆盖。选择器 SHALL 带搜索。拉取失败 SHALL NOT 阻塞表单（提示可重试）；清单为空或拉取失败时 SHALL 保留手动填写出口（手填值保存后仍为该配置模型列表首项）。「测试连接」返回的模型清单 SHALL 同步刷新选择器选项（默认选中规则同上）。

服务端连接测试自动落库路径 SHALL 与手写路径执行一致的清单归一化（去空白/去重保序），清单条数超过上限 SHALL 截断保留前 N 条而非原样超限落库。

#### Scenario: Key 失焦自动拉清单并默认选中首项
- **WHEN** 用户在添加弹窗选择无登记默认模型的供应商（如 Kimi）、填入 API Key 后焦点离开 Key 输入框
- **THEN** 表单自动向该供应商清单端点发起轻探针拉取，成功后模型选择器弹层可选全部拉回的模型 id，默认选中清单首项

#### Scenario: 登记默认模型在清单内优先选中
- **WHEN** 用户选择 DeepSeek 并填入 Key，自动拉取返回含 `deepseek-v4-pro` 的清单
- **THEN** 默认选中登记表默认模型 `deepseek-v4-pro`（而非清单首项），保存后模型列表首项为它

#### Scenario: Ollama 免 Key 即拉
- **WHEN** 用户选择 Ollama 供应商（无需 API Key）
- **THEN** Base URL 确定后即自动拉取 `/api/tags` 本地模型清单，无需等待 Key 输入

#### Scenario: 无清单端点退手填兜底
- **WHEN** anthropic 格式端点对 `/v1/models` 返回 404（不提供模型列表）
- **THEN** 轻探针返回空清单＋候选 id＋说明，选择器内保留手填输入行与候选 chips，用户手填模型 id 后可正常保存（首项落库）

#### Scenario: 拉取失败不阻塞保存
- **WHEN** 轻探针网络失败或鉴权失败
- **THEN** 模型字段呈现失败提示与「重新拉取」出口，表单其余字段可继续填写并保存（不因拉取失败锁死）

#### Scenario: 测试连接结果刷新清单
- **WHEN** 用户点「测试连接」且测试成功返回模型清单
- **THEN** 选择器选项以测试返回的清单刷新；用户此前手动改选的值在清单内时保持不变

#### Scenario: 超长清单落库截断
- **WHEN** 连接测试拉回的模型清单超过上限（如百炼返回逾百条）
- **THEN** 自动落库前归一化（去空白/去重）并截断保留前 N 条，后续手动 PUT 模型列表 SHALL NOT 因存量超限被拒

## MODIFIED Requirements

### Requirement: 供应商默认值预填

系统 SHALL 提供供应商默认值登记表（键＝供应商×接口格式，值＝官方 Base URL＋默认模型名称＋备选模型候选），作为创建表单预填的单一数据源。登记纪律＝有据才登记（实测或厂商官方文档），无据字段 SHALL 留空，SHALL NOT 编造；首批全量登记 DeepSeek，其余内置供应商按官方文档核对后登记。

创建模型配置时，用户选中登记表内的供应商（或切换接口格式）后，表单 SHALL 自动填入该「供应商×接口格式」登记的 Base URL 与默认模型名称，用户只需填写 API Key 即可保存；「模型」SHALL 为创建表单的一级字段，形态为**模型选择器**（自动拉取清单，见「模型清单自动拉取」）：登记的默认模型名称为清单到位前的初值与清单到位后的默认选中优先项；清单为空或拉取失败时 SHALL 退为手填输入（登记默认模型名称为初值）。保存后选中值（或手填值）SHALL 为该配置模型列表首项。预填字段 SHALL 可编辑。字段为空、或仍等于预填值（用户未手改）时，SHALL 随供应商/格式切换更新为新登记值；用户手改过的字段 SHALL NOT 被覆盖。「OpenAI 兼容」等无登记值的供应商 SHALL NOT 预填（沿用 placeholder 示例域名引导；清单自动拉回后的默认选中不算预填）。编辑已有配置 SHALL NOT 施加预填（沿用已存值）。

#### Scenario: 选 DeepSeek 只填 Key 即可保存
- **WHEN** 用户在添加弹窗选择 DeepSeek 供应商
- **THEN** Base URL 与模型初值自动填为登记默认值，用户填入 API Key 后自动拉取清单并默认选中登记默认模型，保存成功，配置的 Base URL 与模型列表首项即为登记值

#### Scenario: 预填字段可编辑且手改不被覆盖
- **WHEN** 用户把预填的 Base URL 改成自己的地址后切换供应商再切回
- **THEN** 用户改过的 Base URL 保持不变（不被预填值覆盖）；未手改的字段随所选供应商更新为对应登记值

#### Scenario: 无登记值的供应商不预填
- **WHEN** 用户选择「OpenAI 兼容」供应商
- **THEN** Base URL 与模型初值留空（placeholder 引导），不自动填入任何猜测值（清单自动拉回后的默认选中不算猜测值）

#### Scenario: 登记表无据字段留空
- **WHEN** 某供应商的默认模型 id 尚无实测或官方文档依据
- **THEN** 该供应商的模型初值留空（由自动拉取清单默认选中或用户自填），SHALL NOT 编造模型 id
