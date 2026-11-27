# model-api-config Delta — 模型清单后台保鲜＋编辑态已存密钥刷新

## ADDED Requirements

### Requirement: 模型清单后台保鲜

系统 SHALL 提供 `POST /api-configs/ensure-models-fresh`（body：`config_ids?`、`force?`）作为清单保鲜入口：对当前用户的活跃写作配置（排除已删除与朱雀），按 `models_updated_at` 判断新鲜度——距上次成功超过 TTL（SHALL 默认 10 分钟，可配置）才用已存密钥执行「只拉清单」轻探针（与 `fetch-models` 同一实现，零生成调用；单次出网超时 SHALL 不超过 5 秒）；未过期 SHALL 直接返回已存快照。成功且清单非空 SHALL 按「已选首项保头」归一写库并回显同一份清单与 `models_updated_at`；清单为空或探针失败 SHALL 原样透传，SHALL NOT 覆盖已存清单、SHALL NOT 改动连接测试结果字段（`last_test_*`——轻探针不证对话可用）。失败后 SHALL 进入退避（默认 5 分钟），退避期内 SHALL NOT 自动重试；端点不提供清单（空清单）SHALL 视为「已检查」——同一 TTL 内 SHALL NOT 重复出网，响应保持 `ok=true`（SHALL NOT 标失败），`force=true` 可强制重试；`force=true` SHALL 绕过 TTL 与退避（用户显式动作）。`config_ids` 缺省 SHALL 表示全部活跃配置，空数组 SHALL 表示不刷新任何配置。同一配置的并发 ensure SHALL 单飞；跨配置出网并发 SHALL 有上限（默认 3）。响应 SHALL 为 `{configs: [{id, models, models_updated_at, refreshed, ok, error}]}`。

前端 SHALL 维护模型清单的全局单一数据源（配置与清单一份、选择器共享）：任何一次保鲜成功的清单 SHALL 推送给所有选择器，SHALL NOT 由各页面各持一份快照。前端 SHALL 在应用启动（登录后）、前台定时（SHALL 默认 5 分钟）、窗口回焦/可见、进入含模型选择的页面/面板（模型配置页、本书模型、写作助手、拆书创建/详情）、以及任何模型选择器打开时触发保鲜；客户端 SHALL 有触发节流（SHALL 默认 30 秒），未登录 SHALL NOT 触网。选择器打开 SHALL NOT 阻塞等待保鲜结果：先展示缓存清单，在途时显示更新提示，返回后就地合并（SHALL NOT 重置搜索词、光标或已选值）。

保鲜失败 SHALL NOT 弹全局错误或阻塞选择，SHALL 在选择器/模型面板以一行轻提示告知「清单可能不是最新」；清单更新后当前选中模型不在新清单时 SHALL 保留选择并标注「已不在最新清单」，SHALL NOT 自动改选或改本书绑定（书内就绪度沿用 `ai_model ∈ config.models` 的既有判据）。后台保鲜成功后，正在编辑的配置弹窗与列表卡片 SHALL 同步新清单；保存时的模型列表拼装 SHALL 使用刷新后的清单（SHALL NOT 用打开弹窗时的旧快照覆盖）。

#### Scenario: 冷启动后打开选择器已是新清单

- **WHEN** 用户启动应用并进入工作台/模型配置页，在上一次清单之后供应商上线了新模型（如 `glm-5.4`）
- **THEN** 启动与进页面的后台保鲜已把新清单写进配置；用户打开本书模型/助手底栏/编辑弹窗时，列表里已有新模型，且选择器打开没有等待网络的停顿

#### Scenario: TTL 内不重复出网

- **WHEN** 同一配置在 10 分钟内被多次触发保鲜（启动、定时、选择器打开）
- **THEN** 只有第一次真正请求供应商清单端点，其余直接回已存快照（`refreshed=false, ok=true`）

#### Scenario: 过期刷新保头且不动测试状态

- **WHEN** 配置的 `models_updated_at` 超过 TTL 且供应商返回的清单含当前已选模型
- **THEN** 清单归一后把当前已选模型置于首位落库，响应与落库同一份；`last_test_status`/`last_test_error`/`last_tested_at` 保持不变

#### Scenario: 失败退避与轻提示

- **WHEN** 保鲜请求超时或供应商报错
- **THEN** 已存清单保持不动，该配置进入 5 分钟退避；选择器/模型面板显示一行「清单可能不是最新」，不弹全局错误、不阻塞选择；退避期内不自动重试，手动 `force` 可立即重试

#### Scenario: 空清单不覆盖已存清单

- **WHEN** 保鲜时端点不提供模型清单（空清单）
- **THEN** 响应 `ok=true, refreshed=false` 并回已存清单，SHALL NOT 把配置清单清空

#### Scenario: 空清单不重复出网

- **WHEN** 端点不提供清单（空清单）后，TTL 内再次触发保鲜（启动/定时/选择器打开/进页面）
- **THEN** 不再请求供应商清单端点（视同已检查），响应保持 `ok=true, refreshed=false`；用户点「获取模型」等 force 动作仍可立即重试

#### Scenario: 显式空 config_ids 不刷新

- **WHEN** 调用 ensure 时显式传 `config_ids: []`
- **THEN** 不刷新任何配置、不出网，响应 `configs: []`（与缺省 `config_ids`＝全部配置区分）

#### Scenario: 失效选中保留并标记

- **WHEN** 保鲜后的新清单不再包含用户当前选中的模型
- **THEN** 选中值保持不变，选择器/模型面板标「已不在最新清单」；书内就绪度按既有判据显示失效并引导重选，不静默改选或改绑定

#### Scenario: 未登录不触网

- **WHEN** 用户在登录页/落地页（无会话）
- **THEN** 保鲜与调度 SHALL NOT 发起 ensure 请求

#### Scenario: 后台更新不吞保存

- **WHEN** 编辑配置弹窗打开期间后台保鲜更新了该配置的清单，用户随后直接保存（未改模型）
- **THEN** 弹窗内清单已同步新模型，保存提交的模型列表为刷新后的清单，SHALL NOT 按打开弹窗时的旧快照覆盖

## MODIFIED Requirements

### Requirement: 模型清单自动拉取

系统 SHALL 提供「只拉清单」轻探针：按与连接测试完全相同的端点构造（`openai` 格式 GET `{base}/models`（base 无版本段补 `/v1`）+ Bearer 头；`anthropic` 格式 GET `{base}/v1/models` + `x-api-key` 与 `anthropic-version` 头；ollama GET `/api/tags`，一律打用户填写的 base），仅请求模型清单端点，SHALL NOT 发起对话探针（不产生生成调用）。新端点 `POST /api-configs/fetch-models` 接收 raw 配置（vendor/base_url/api_key/api_format，未保存态），返回 `{ok, status, models, candidates?, note?, error?}`。200 响应体非 API JSON（网页等）SHALL 判失败并提示核对 Base URL；**anthropic 格式** 404 SHALL 返回空清单＋该 vendor 候选 id＋「端点不提供模型列表」说明（与连接测试降级同判据，但不发生成请求）；models 端点返回 400/403/405（2026-10-16 CloudBase 案：网关对清单路由本身回 403 并附误导文案）SHALL 按「该端点未提供模型清单」口径返回成功＋空清单＋该 vendor 候选 id＋说明——403 的说明 SHALL 兼容「Key 无此权限」语义，SHALL NOT 标「认证失败」（该状态无法区分路由权限与清单缺失），SHALL NOT 发起对话探针（保持零生成调用语义）；401 SHALL 维持「认证失败」判死（Key 层语义明确）；openai/ollama 格式 404 SHALL 按异常响应判失败并提示核对（SHALL NOT 误诊为「无清单端点」）；非 ollama 且 Key 为空 SHALL 判鉴权失败。

创建表单的字段顺序 SHALL 为「Base URL → API Key → 模型」（2026-10-07 拍板：Key 失焦拉到的清单直接喂给紧随其下的模型选择器；编辑表单同序）。创建表单中，API Key 失焦且非空时 SHALL 自动调用轻探针拉取清单（Ollama 免 Key：供应商或 Base URL 确定后即拉）；vendor、Base URL、接口格式变更且 Key 已填时 SHALL 重拉。编辑表单同口径（2026-10-09）：API Key 重填后失焦且非空（或 Ollama 免 Key）SHALL 自动拉取；显式「获取模型」按钮 SHALL NOT 仅因 Key 未重填而禁用（2026-11-27 翻案——旧口径「Key 未重填即禁用并提示重填」让上线后的新模型看不到，已存清单是过期快照）：表单连接参数（Base URL、接口格式）与已存值字面一致时 SHALL 走已存密钥轻探针（见下段），连接参数有未保存变更或已重填 Key 时 SHALL 走 raw 轻探针（raw 需明文 Key，无 Key 时按钮禁用并提示重填）；已存密钥轻探针失败后的「重新拉取」SHALL 与首次同一路径（SHALL NOT 退回 raw）；编辑态接口格式切换作废清单时 SHALL NOT 施加供应商预填（沿用已存值）。配置声明跳过模型清单接口（见「可跳过模型清单接口」）时，表单 SHALL NOT 触发自动拉取，显式「获取模型」入口 SHALL 禁用。在途请求管理：同参数重复触发（在途或已成功）SHALL 不再发起新请求；参数已变的在途响应 SHALL 作废（不落地）；供应商/格式切换作废清单时 SHALL 连同在途请求一并作废。清单到位后模型选择器 SHALL 默认选中**清单首项**（2026-10-07 二次拍板「默认选第一个就好，不评估价值」——登记表默认模型不优先，预填值只作清单到位前的初值；编辑态已存初值视同手改，SHALL NOT 被覆盖）；用户手动改选或手填后 SHALL NOT 被后续自动刷新覆盖（含在途响应迟到时）。选择器 SHALL 带搜索，且 SHALL 始终保留手动填写出口（清单非空时手填用于清单外 id；清单为空/拉取失败时为主入口）。拉取失败 SHALL NOT 阻塞表单（提示可重试）。「测试连接」返回的模型清单 SHALL 同步刷新选择器选项（连接失败信封携带的清单同样刷新——失败但清单真实时用户可改选正确模型；默认选中仅在成功时执行）。

已存密钥轻探针 SHALL 为 `POST /api-configs/{config_id}/refresh-models`：服务端以落库密钥（解密）与已存连接参数（vendor/base_url/api_format）执行与 `fetch-models` 同款「只拉清单」请求——仅请求模型清单端点，SHALL NOT 发起对话探针（零生成调用）。成功且清单非空 SHALL 按「已选首项保头」归一写库（与连接测试自动落库同一口径，含去空白/去重/上限截断），响应 SHALL 回显同一份落库清单；清单为空（端点不提供）或探针失败 SHALL 原样透传响应，SHALL NOT 覆盖已存清单，SHALL NOT 改动连接测试结果字段（`last_test_status`/`last_test_error`/`last_tested_at`——轻探针不证对话可用）。未知配置 SHALL 404、已禁用配置 SHALL 400。前端 SHALL NOT 在打开编辑弹窗时自动调用**该端点**（`refresh-models`，它总是真出网）；弹窗打开时的自动保鲜走「模型清单后台保鲜」的 ensure 端点（服务端 TTL 决定是否真出网）。刷新成功 SHALL 同步更新编辑目标与列表卡片的已存清单，保存时的模型列表拼装 SHALL 使用刷新后的清单（SHALL NOT 按弹窗打开时的旧快照覆盖）。

连接测试的对话探针失败时，失败信封 SHALL 携带已提取的模型清单（models 端点 GET 已成功的真实数据）——手填错 id 后重测，清单照常落库，书内选择面板立刻有正确候选可选（自恢复闭环，无需删配置重建）。服务端连接测试自动落库路径 SHALL 与手写路径执行一致的清单归一化（去空白/去重保序），清单条数超过上限 SHALL 截断保留前 N 条而非原样超限落库——**上限 SHALL 为 300**（2026-10-24 火山案拍板：方舟 `/models` 返回 137 条且最老在前排序，上限 100 时在役新模型被系统性截成「拿不到」，上限抬至 300 兼顾防无界落库与清单全量可见）；落库 SHALL **保头**——配置当前默认模型（models 首项＝用户登记/手选值）在清单内时置于结果首位（不限是否触发截断：保住「首项＝已选模型」语义，下次探针优先用它；截断时尤甚——SHALL NOT 被供应商顺序挤出截断窗）；测试响应体与落库 SHALL 为同一份归一化清单。

#### Scenario: Key 失焦自动拉清单并默认选中首项
- **WHEN** 用户在添加弹窗选择供应商、填入 API Key 后焦点离开 Key 输入框
- **THEN** 表单自动向该供应商清单端点发起轻探针拉取，成功后模型选择器弹层可选全部拉回的模型 id，默认选中清单首项（登记表默认模型在清单内也不优先）

#### Scenario: 登记默认不优先（2026-10-07 二次拍板「不评估价值」）
- **WHEN** 用户选择 DeepSeek 并填入 Key，自动拉取返回含登记默认模型 `deepseek-v4-pro` 的清单（首项为 `deepseek-flash`）
- **THEN** 默认选中清单首项 `deepseek-flash`（预填初值 `deepseek-v4-pro` 仅作清单到位前的显示值），保存后模型列表首项为选中值

#### Scenario: Ollama 免 Key 即拉
- **WHEN** 用户选择 Ollama 供应商（无需 API Key）
- **THEN** Base URL 确定后即自动拉取 `/api/tags` 本地模型清单，无需等待 Key 输入

#### Scenario: 无清单端点退手填兜底
- **WHEN** anthropic 格式端点对 `/v1/models` 返回 404（不提供模型列表）
- **THEN** 轻探针返回空清单＋候选 id＋说明，选择器内保留手填输入行与候选 chips，用户手填模型 id 后可正常保存（首项落库）

#### Scenario: openai 格式清单 403/400/405 按无清单口径返回（CloudBase 案）

- **WHEN** 轻探针对 openai 格式 models 端点拿到 403（JSON 错误信封，如 CloudBase 网关）、400 或 405
- **THEN** 返回成功＋空清单＋该 vendor 候选 id＋「该端点未提供模型清单」说明（403 说明兼容 Key 无此权限语义，SHALL NOT 标「认证失败」），选择器保留手填输入行；SHALL NOT 发起任何对话探针

#### Scenario: 拉取失败不阻塞保存
- **WHEN** 轻探针网络失败或鉴权失败
- **THEN** 模型字段呈现失败提示与「重新拉取」出口，表单其余字段可继续填写并保存（不因拉取失败锁死）

#### Scenario: 测试连接结果刷新清单
- **WHEN** 用户点「测试连接」且测试成功返回模型清单
- **THEN** 选择器选项以测试返回的清单刷新；用户此前手动改选的值在清单内时保持不变

#### Scenario: 编辑态重填 Key 自动拉取与获取模型
- **WHEN** 用户编辑配置时重填 API Key 后失焦（或 Ollama 免 Key），或点「获取模型」
- **THEN** 按当前参数发起 raw 轻探针，清单到位刷新选择器，已存初值（已选模型）不被「清单首项」默认选中覆盖

#### Scenario: 编辑态 Key 留空刷新清单（新模型上线）
- **WHEN** 用户编辑一条已有清单的配置，未重填 Key、未改 Base URL 与接口格式，点「获取模型」
- **THEN** 走已存密钥轻探针（`POST /api-configs/{id}/refresh-models`），服务端以已存密钥与已存连接参数执行清单请求；成功后选择器可选刷新后清单的全部 id（如新上线的 `glm-5.4`），已存已选模型仍为初值不被覆盖；保存时模型列表按刷新后的清单落库

#### Scenario: 已存密钥轻探针失败或端点不提供清单
- **WHEN** 已存密钥轻探针网络失败/鉴权失败，或端点不提供清单（空清单）
- **THEN** 原失败/说明提示与「重新拉取」出口照常呈现（重试仍走已存密钥路）；已存清单 SHALL NOT 被覆盖，连接测试状态字段保持不变，表单其余字段可继续填写并保存

#### Scenario: 连接参数有未保存变更时回 raw 路
- **WHEN** 用户编辑配置时改了 Base URL 或接口格式（尚未保存）且 Key 留空，点「获取模型」
- **THEN** 已存密钥轻探针不可用（按钮禁用并提示重填 Key），SHALL NOT 用旧端点清单充数；用户重填 Key 后按当前参数走 raw 轻探针，保存门禁按新参数探测

#### Scenario: 超长清单落库截断且保头
- **WHEN** 连接测试拉回的模型清单超过上限 300（如供应商返回逾 300 条），且配置当前默认模型排在供应商清单尾部；或清单在 100–300 条区间（如火山方舟 137 条、最老在前——在役新模型全在尾部）
- **THEN** 自动落库前归一化（去空白/去重）：100–300 条区间 SHALL 全量落库（在役新模型可见、可选）；超 300 条 SHALL 截断保留前 300 条，配置默认模型置于截断结果首位不被截掉，测试响应体与落库为同一份清单；后续手动 PUT 模型列表 SHALL NOT 因存量超限被拒

#### Scenario: 未超限重测同样保头
- **WHEN** 配置当前默认模型（用户手选值）排在供应商清单第二位及以后，重测拉回的清单未超上限
- **THEN** 落库清单把该默认模型置于首位（首项＝已选模型语义，下次探针优先用它），其余按供应商原序跟随

#### Scenario: 探针失败仍带回清单（自恢复闭环）
- **WHEN** 用户手填了清单外的模型 id 保存，连接测试的 models GET 成功但对话探针因该 id 被拒
- **THEN** 测试判失败并点名所试 id，但失败信封携带已提取的真实清单并照常落库，书内选择面板可直接改选正确模型，无需删除配置重建
