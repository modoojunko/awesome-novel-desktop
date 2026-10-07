# c-api-config-auto-models — 模型清单自动拉取：配完 Key 弹清单，手填退役为兜底

## Why

创建模型配置仍要用户**手填模型 id**（10-05 的供应商默认值预填只解了 DeepSeek 一家）。但八家供应商的模型清单端点已实勘全部可用（OpenAI/DeepSeek/Kimi/GLM/百炼 `/models`、Anthropic `/v1/models`、Ollama `/api/tags`，另文有据），后端连接测试也**早已把清单拉回来了**——只是表单把它扔掉。用户拍板（2026-10-07）：**配完 Key 后自动获取提供商的模型清单，默认选第一个；用户只需要填 API Key＋验证测试连接**。形态用带搜索的弹层（百炼清单有几十个模型 id）。

顺带修一个实锤隐患：连接测试自动落库路径**绕过 `_normalize_models`**（手动路径去空白/去重/上限 100，自动路径原样写库）——百炼清单若超 100 条，之后任何手动 PUT 模型列表都会 422。

## What Changes

- **新增「只拉清单」轻探针**（`fetch_models`）：复用连接测试的 URL/请求头构造，只 GET 模型清单端点，**不跑对话探针**（零生成调用、零计费）。新端点 `POST /api-configs/fetch-models`（raw、未保存态，鉴权同 test-connection）。
- **创建表单模型字段改为选择器**：API Key 失焦且非空时自动拉清单（Ollama 免 Key＝供应商/Base URL 确定即拉）；vendor/Base URL/接口格式变更且 Key 已填时重拉。弹层带搜索（组合框：输入即搜索），**默认选中＝清单首项**（2026-10-07 二次拍板「默认选第一个就好，不评估价值」——登记默认模型不优先，预填值只作清单到位前的初值）；用户手动改选后不被覆盖。
- **兜底不删**：拉取失败/端点无清单（anthropic 兼容端点 404 常见）→ 弹层内保留手填输入行＋vendor 候选 chips，不阻塞保存。「测试连接」返回的清单同步刷新选择器（双保险）。
- **保存语义不变**：创建仍 `models: [选中项]`；创建后自动测试落全量清单（现状行为，书内选择面板数据源不动）。
- **落库归一化补齐**：测试自动落库路径走与手写路径一致的归一化（去空白/去重），超上限**截断**而非静默存超限（消除后续手动 PUT 422 的雷）。
- **候选表刷新**：`VENDOR_MODEL_CANDIDATES.deepseek` 按官方文档（api-docs.deepseek.com/api/list-models：`deepseek-flash`、`deepseek-v4-pro`）更新陈旧 id（`deepseek-v4-flash` 已不存在）。
- 明确不做：编辑态不加模型字段（卡片「测试连接」已能刷新清单）；`refresh-models` stub 不动；书内 ModelSettingForm 长清单搜索（后续优化）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`: 新增「模型清单自动拉取」需求（轻探针、自动触发、默认选中、兜底手填、落库归一化）；「供应商默认值预填」中模型字段形态从手填一级输入框改为自动拉取选择器（登记默认模型＝初值＋默认选中优先项）。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响的屏/弹层**：模型配置页（`/#/config`）·「添加 API Key」弹窗——「模型名称」输入框替换为模型选择器（选中态按钮＋搜索弹层＋手填兜底行）；配置卡列表无改动。
- **对象状态**：无新增对象状态（拉取中/已拉到 N 个/失败可重试均为表单瞬时态，不入状态语言总表）。
- **共享段**：不触碰两端共享段；`.sel-panel` 系样式为 C端 book.css 既有类，直接复用。
- **原型先行**：需要——`docs/design-c/prototypes/model-config.html` 同批补选择器形态（design-parity 0.002 门禁），由实现侧自查产出。
- **语气词表**：沿用 info/ok/warn/err（拉取失败提示＝warn 带「重新拉取」出口；成功态＝ok），无第四种胶囊形态。
