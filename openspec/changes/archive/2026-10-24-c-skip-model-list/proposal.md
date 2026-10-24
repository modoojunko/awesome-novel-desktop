## Why

CloudBase AI 网关等端点对模型清单接口 `GET {base}/models` 本身回 4xx（同环境不同管理 Key 实测有 400 也有 403，403 还附「Unsupported model in group cloudbase」这类与清单无关的误导文案），而对话接口完全正常。现行连接测试只对「404／200 网页体」降级探对话，其余一律判「认证失败／异常响应」——这类网关的配置因此永远测试红，`last_test_status` 失败态又被健康闸（`config_key_usable`）采信，把**实际可用的生成**也一并挡死（2026-10-16 实锤：用户配 CloudBase 浑元，chat/completions 实测 200，卡片恒红、生成被拦）。

## What Changes

- **高级选项「跳过模型清单接口」**：每条配置新增持久化布尔 `skip_model_list`（默认关）。表单「模型名称」字段下提供勾选框；勾选后连接测试**不发起清单请求**，直接用手填模型名发最小生成探针，无模型名则拦下提示；「获取模型」按钮禁用、Key 失焦自动拉取不再触发。anthropic 格式同样适用；ollama 不显示（自有 tags 端点）。
- **清单失败自动降级兜底**：连接测试中 models 端点凡未能带回可用清单（400/401/403/405/其它 4xx/5xx）且有可用探针模型 id 时，一律降级发对话探针、判定以探针为准（与既有 404／200 网页体降级同判据）。真坏 Key 不失真——探针同址同鉴权照样回「认证失败」；无 id 守卫保持：401/403 无 id 维持认证失败文案，其余无清单形态无 id 按提示填写模型名判负。
- **轻探针文案纠正**：`fetch_models` 对 models 端点的 400/403/405 不再标「认证失败／异常响应」，按「该端点未提供模型清单」口径返回 ok＋空清单＋候选＋说明（403 文案兼容「权限不足」语义）。
- **持久化与兼容**：本地库升级幂等新增 `skip_model_list` 列（默认关）；配置包导出/导入按加键兼容契约携带该键（旧包缺键默认关）。
- **健康闸与生成链路零改动**：`config_key_usable` 谓词、按次模型选择、本书绑定不动——探针语义修正后 `last_test_status` 自然转好，闸自然开。不做厂商特判（按协议行为修，不按厂商开洞）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`：
  - **ADDED** Requirement「可跳过模型清单接口」——`skip_model_list` 的持久化、表单控件、测试直探对话、自动获取禁用、迁移与配置包兼容。
  - **MODIFIED** Requirement「按接口格式探测连接」——models 端点凡未带回可用清单（400/401/403/405/其它 4xx/5xx）同享降级探对话，判定以探针为准；跳过声明时直接探对话。
  - **MODIFIED** Requirement「模型清单自动拉取」——轻探针对 400/403/405 按「端点未提供模型清单」口径返回，不再标「认证失败／异常响应」。

## Impact

- 后端：`client/backend/api_configs/connection.py`（test_connection 降级分支、fetch_models 状态语义）、`api_configs/schemas.py`（Create/Update/TestRaw body 与 Response 加 `skip_model_list`）、`api_configs/service.py`（落库/测试透传）、本地库迁移链（幂等加列）、配置包导出/导入（加键兼容）。
- 前端：`client/frontend/src/components/api-config/ApiConfigForm.tsx`（勾选框＋联动禁用）、`types/api-config.ts`、`pages/ApiKeyConfigPage.tsx`（透传字段）。
- 测试：`tests/test_api_configs*.py` 新增降级矩阵与 skip 用例、迁移幂等用例；前端 vitest 表单联动用例。
- 不动：`ai_client.py` 生成链路、`ai_state.config_key_usable`、ollama 特例路径。

## Design Impact

- 受影响端：**仅 C端**（S端 无模型配置域，不触碰）。
- 受影响屏/弹层：模型配置页「添加 API Key／编辑配置」弹窗（新增勾选框＋说明行，模型名称字段下方）；配置卡无结构变化（仅测试结果随探测语义自然转绿）。
- 对象状态：勾选框为既有表单控件词汇（checkbox＋`cf-hint` 说明行），不新增组件形态、不引入新提示语气（info/ok/warn/err 既有词表内）；「获取模型」禁用态沿用现有 disabled＋title 口径。
- 两端共享段：不触碰（base.css 令牌与基础组件类零改动，`design-cross.mjs` 不需跑）。
- 原型先行：**需要**——`docs/design-c/prototypes/model-config.html` 同批加勾选框并在 `ADJUSTMENTS.md` 登记偏差；`npm run design:check` 复跑。
- 设计工件：实现侧自查（控件为既有词汇复用，无新视觉决策）。
- 文案口径（design-language §13）：面向用户的说法是「模型清单」，不出现「/models 端点」「降级」等内部术语；「获取模型」禁用说明带补救出口（手填模型 id 后测试）。
