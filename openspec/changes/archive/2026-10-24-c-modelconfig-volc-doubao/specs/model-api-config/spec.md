# model-api-config Delta

## MODIFIED Requirements

### Requirement: 接口格式为配置的一级字段

每条模型配置 SHALL 持久化一个接口格式字段 `api_format`，取值仅为 `openai` 或 `anthropic`，默认 `openai`。接口格式与供应商正交：同一供应商的配置可分别声明两种格式。

#### Scenario: 新建配置默认 OpenAI 格式

- **WHEN** 用户添加配置且未显式选择接口格式
- **THEN** 该配置保存后 `api_format` 为 `openai`

#### Scenario: 厂商锁定矩阵

- **WHEN** 用户在添加弹窗选择 OpenAI、Anthropic、Ollama、Gemini 或豆包供应商
- **THEN** 接口格式控件呈置灰锁定态，分别固定为 OpenAI 格式、Anthropic 格式、OpenAI 格式、OpenAI 格式、OpenAI 格式，不可切换（豆包锁定 OpenAI 格式：火山方舟无 Anthropic 兼容口）
- **WHEN** 用户选择 OpenCode Go · 通用或 OpenCode Go · Claude 系供应商
- **THEN** 接口格式控件呈置灰锁定态，分别固定为 OpenAI 格式、Anthropic 格式，不可切换
- **WHEN** 用户选择 GLM、Kimi、DeepSeek、Qwen 或 OpenAI 兼容供应商
- **THEN** 接口格式控件可在 OpenAI 格式 / Anthropic 格式间切换

### Requirement: 供应商默认值预填

系统 SHALL 提供供应商默认值登记表（键＝供应商×接口格式，值＝官方 Base URL＋默认模型名称＋备选模型候选），作为创建表单预填的单一数据源。登记纪律＝有据才登记（实测或厂商官方文档），无据字段 SHALL 留空，SHALL NOT 编造；登记的 Base URL SHALL 与生成调用链路同源可用——SDK 生成调用对 openai 格式 base 先经版本段归一（裸域名按 OpenAI 惯例补 `/v1`，与探测同源单判据，见「按接口格式调用大模型」），登记值仍须含版本段以显式表达实际请求地址、不依赖隐式归一（OpenAI 官方为 `https://api.openai.com/v1`，Ollama 为 `http://localhost:11434/v1`），SHALL NOT 登记缺版本段的裸域名；首批全量登记 DeepSeek，其余内置供应商按官方文档核对后登记。

登记表 SHALL 含以下四条新增登记（Gemini/OpenCode Go 三条系 2026-10-20 官方文档核对；豆包条目系 2026-10-24 方舟模型目录元数据＋真 Key 探针实测核对）：Gemini×openai——Base URL `https://generativelanguage.googleapis.com/v1beta/openai/`（官方兼容层，自带版本段），默认模型留空，备选候选按官方模型页登记；OpenCode Go · 通用×openai——Base URL `https://opencode.ai/zen/go/v1`，默认模型留空，备选候选按 OpenCode Go 官方模型清单登记（GLM、Kimi、DeepSeek、MiMo、Hy 等聊天族）；OpenCode Go · Claude 系×anthropic——Base URL `https://opencode.ai/zen/go`（Anthropic 格式链路由 SDK 拼 `/v1/messages`，与 Anthropic 官方登记同口径），默认模型留空，备选候选按官方清单登记（Claude Haiku、MiniMax、Qwen 系）；豆包×openai——Base URL `https://ark.cn-beijing.volces.com/api/v3`（方舟 OpenAI 兼容口，自带版本段 `/api/v3`），默认模型 `doubao-seed-2-1-lite-260915`（**完整版本 id**——方舟数据面裸名不可调，2026-10-24 实测：裸名 `doubao-seed-2-1-lite` 404「模型或推理接入点不存在」、版本 id 200），备选候选按方舟官方模型广场登记豆包文本家族版本 id（Seed 2.1 系 lite/pro/turbo 等）。四者的备选候选 SHALL 与后端探测候选清单同源对齐（前端登记值变更两处同步，既有纪律）。

创建模型配置时，用户选中登记表内的供应商（或切换接口格式）后，表单 SHALL 自动填入该「供应商×接口格式」登记的 Base URL 与默认模型名称，用户只需填写 API Key 即可保存；「模型」SHALL 为创建与编辑表单的一级字段（2026-10-09 拍板，修复「编辑页没有模型可选、实际测试连接又要用模型」——连接测试必须用模型做真实生成探针，已存配置恒用模型列表首项，探针模型失败后用户须能在编辑页改选），形态为**模型选择器**（自动拉取清单，见「模型清单自动拉取」）：登记的默认模型名称为清单到位前的初值（清单到位后默认选中清单首项，登记值不优先）；清单为空或拉取失败时 SHALL 退为手填输入（登记默认模型名称为初值）。保存后选中值（或手填值）SHALL 为该配置模型列表首项。预填字段 SHALL 可编辑。字段为空、或仍等于预填值（用户未手改）时，SHALL 随供应商/格式切换更新为新登记值；用户手改过的字段 SHALL NOT 被覆盖。「OpenAI 兼容」等无登记值的供应商 SHALL NOT 预填（沿用 placeholder 示例域名引导；清单自动拉回后的默认选中不算预填）。编辑已有配置 SHALL NOT 施加预填（沿用已存值）：模型选择器初值 SHALL 为该配置已存模型列表首项（＝该配置已选模型/探针优先模型），清单种子＝已存模型列表（弹层立即可改选或手填清单外 id），已存初值视同手改（SHALL NOT 被拉取/测试的「清单首项」默认选中覆盖）；编辑保存时改选值 SHALL 置模型列表首项（保留其余已存项按原序，超上限截断对齐手动路径），留空 SHALL 省略模型列表字段（沿用已存值，与「留空则保留当前密钥」同语义）。

#### Scenario: 选 DeepSeek 只填 Key 即可保存

- **WHEN** 用户在添加弹窗选择 DeepSeek 供应商
- **THEN** Base URL 与模型初值自动填为登记默认值，用户填入 API Key 后自动拉取清单并默认选中清单首项（登记值不优先），保存成功，配置的 Base URL 为登记值、模型列表首项为选中值

#### Scenario: 选 Gemini 只填 Key 即可保存

- **WHEN** 用户在添加弹窗（官方页）选择 Gemini 供应商
- **THEN** Base URL 自动填为官方兼容层登记值、接口格式锁定为 OpenAI 格式，模型初值留空；用户填入 Gemini API Key 后自动拉取清单（兼容层提供模型列表）并默认选中清单首项，保存成功；清单拉取失败时退为手填（placeholder 提示可填 gemini-2.5-pro 等 id），保存不阻塞

#### Scenario: 选豆包只填 Key 即可保存

- **WHEN** 用户在添加弹窗（官方页）选择豆包供应商
- **THEN** Base URL 自动填为 `https://ark.cn-beijing.volces.com/api/v3`、接口格式锁定为 OpenAI 格式，模型初值为登记默认 `doubao-seed-2-1-lite-260915`；用户填入方舟 API Key 后自动拉取清单（方舟提供模型列表时）并默认选中清单首项，或按备选候选手填，保存成功；生成请求命中 `POST https://ark.cn-beijing.volces.com/api/v3/chat/completions`，SHALL NOT 因裸名 id 而命中不存在的模型

#### Scenario: 选 OpenCode Go · Claude 系预填 Anthropic 地址并锁格式

- **WHEN** 用户在中转页选择 OpenCode Go · Claude 系供应商
- **THEN** Base URL 自动填为 `https://opencode.ai/zen/go`（不带 `/v1`），接口格式锁定为 Anthropic 格式且控件置灰；填入 OpenCode API Key 后自动拉取清单（`GET {归一 base}/models`）或按备选候选手填，保存后生成请求命中 `POST https://opencode.ai/zen/go/v1/messages`

#### Scenario: 预填字段可编辑且手改不被覆盖

- **WHEN** 用户把预填的 Base URL 改成自己的地址后切换供应商再切回
- **THEN** 用户改过的 Base URL 保持不变（不被预填值覆盖）；未手改的字段随所选供应商更新为对应登记值

#### Scenario: 无登记值的供应商不预填

- **WHEN** 用户选择「OpenAI 兼容」供应商
- **THEN** Base URL 与模型初值留空（placeholder 引导），不自动填入任何猜测值（清单自动拉回后的默认选中不算猜测值）

#### Scenario: 登记表无据字段留空

- **WHEN** 某供应商的默认模型 id 尚无实测或官方文档依据
- **THEN** 该供应商的模型初值留空（由自动拉取清单默认选中或用户自填），SHALL NOT 编造模型 id

#### Scenario: 登记值与生成调用同源（缺版本段的裸域名不登记）

- **WHEN** 用户选择 OpenAI（或 Ollama）供应商、按预填值只填 API Key 保存，并触发连接测试或生成
- **THEN** 请求命中官方真实路径（OpenAI `POST {base}/chat/completions` 即 `/v1/chat/completions`），SHALL NOT 因预填值缺版本段而 404

#### Scenario: 编辑弹窗改选模型并保存置首

- **WHEN** 用户编辑一条已存模型列表的配置，从选择器改选另一模型后保存
- **THEN** 保存成功且模型列表首项＝改选值（后续卡片测试连接优先用它），其余已存项按原序保留；重新打开编辑弹窗时模型字段初值＝该改选值

#### Scenario: 编辑态模型留空沿用已存值

- **WHEN** 用户清空编辑弹窗的模型名称字段后保存
- **THEN** 更新请求省略模型列表字段（沿用已存值，与「留空则保留当前密钥」同语义），已存模型列表不变

### Requirement: 供应商分组页签

添加配置弹窗的供应商选择区 SHALL 以两页页签分组：**官方厂商**与**中转 · 订阅制**（页签形态复用接口格式分段控件的同款样式）。官方厂商页 SHALL 承载现有内置厂商（OpenAI、Anthropic、DeepSeek、GLM、Kimi、Qwen、Ollama）与 Gemini、豆包（火山方舟）；中转 · 订阅制页 SHALL 承载存量「OpenAI 兼容」与 OpenCode Go 两张方块（OpenCode Go · 通用、OpenCode Go · Claude 系）。新建弹窗默认落在官方厂商页。页签切换仅改变当前可见的供应商方块集合，SHALL NOT 清除已选中的供应商，SHALL NOT 改动用户已填写的表单内容。新增方块的供应商按钮 SHALL 携带「新」静态角标；SHALL NOT 在本期呈现「待排期」类不可用方块（OpenCode Go 的 Gemini 与 GPT/Grok 系入口待后续 change）。

#### Scenario: 新建弹窗默认官方页

- **WHEN** 用户打开添加配置弹窗
- **THEN** 供应商区显示「官方厂商｜中转 · 订阅制」页签且官方厂商页生效，页内为现有 8 家厂商方块外加 Gemini 与豆包（均带「新」角标），无分组标题行

#### Scenario: 切换中转页见订阅方块

- **WHEN** 用户点「中转 · 订阅制」页签
- **THEN** 页内显示「OpenAI 兼容」「OpenCode Go · 通用」（带「新」角标）「OpenCode Go · Claude 系」（带「新」角标）三张方块；OpenCode Go 的 Gemini／GPT 系入口 SHALL NOT 出现

#### Scenario: 切页不清已选

- **WHEN** 用户已在官方页选中 Gemini 并产生预填后切换到中转页再切回
- **THEN** Gemini 仍为选中态，表单预填与用户已填内容保持不变

#### Scenario: Gemini 官方块全流程可用

- **WHEN** 用户在官方页选中 Gemini（Base URL 预填官方兼容层地址）、填入 Gemini API Key、拉取或手填模型 id 后点「测试连接」并保存
- **THEN** 连接测试与后续生成均走 openai 协议路径命中兼容层地址，行为与「Gemini 兼容层全流程可用」既有口径一致（清单拉取失败不阻塞保存，退手填）

#### Scenario: 豆包官方方块全流程可用

- **WHEN** 用户在官方页选中豆包（Base URL 预填方舟登记地址、模型预填版本 id）、填入方舟 API Key、拉取或手填模型 id 后点「测试连接」并保存
- **THEN** 连接测试与后续生成均走 openai 协议路径命中方舟 `/api/v3/chat/completions`，思考参数按既有 openai 路径形态原样下发（方舟实测接受，见 change design 探针记录；模型未在控制台开通时按既有「探针真实死因透传」口径呈现报错），清单拉取失败不阻塞保存（退手填）
