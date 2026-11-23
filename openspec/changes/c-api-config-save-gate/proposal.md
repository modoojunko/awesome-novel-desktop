# c-api-config-save-gate — 保存模型配置先过连通门禁，URL 不对当场拦下

## Why

内测（2026-10-05）实锤：用户把 Base URL 填成 DeepSeek 控制台**网页**（`platform.deepseek.com/api_keys`），配置却顺利保存并显示「连接正常」——两层失守叠加：

1. **判据假阳性**：旧连接判据只看 HTTP 200，SPA 网站对任意路径回 200 HTML 也算「通」（判据收紧已在 `c-ai-availability-fixes` 落，已归档）；
2. **暴露时机错位**（本 change 主治）：创建流程是「**先落库、再顺手测**」——`POST /api-configs` 落库前零探测，落库后自动测试失败也不拦（弹窗照关、配置照存，只在 toast 尾巴缀「· 请检查 Key」）。用户没有任何一步被要求面对「这个地址不对」，坏 URL 一路进库到生成期才炸。

「测试连接」判得再准，也只是个用户可以不点的按钮。URL 不对必须在**保存（创建/编辑）这一步**就暴露并拦下。

## What Changes

- **保存门禁（后端单源）**：`POST /api-configs`、`PUT /api-configs/{id}` 在落库前执行连接探测——与「测试连接」同一探测实现、同一判据（含思考参数 `thinking_*`，c-thinking-config 之后签名为准）；探测判败（非 ok 的一切形态，含 unknown，按「非 ok 即拦」不按白名单）SHALL NOT 落库，返回结构化 422（detail：`code=probe_failed`＋`status`＋`message`＝探测原文案，复用前端 `lib/api.ts` 既有 `detail.message` 提取路径 —— 当前代码 `lib/api.ts:238`），前端弹窗原位展示、保持打开（表单既有内联 error 位，零新增 UI）。**BREAKING**：create/update 契约新增探测失败 422 分支；不做兼容回落，现网客户端升级后同一入口即新行为（弱网/离线保存被拦属预期变化）。
- **判过即持久化**：探测结果写入测试结果字段（`last_test_status`/`last_test_error`/`last_tested_at`/`models`，与 `test_api_config` 同源写库）；保存响应携带嵌套 `probe`（`ok/status/models/error`，不与配置对象顶层 `status`/`models` 撞名），卡片状态取落库字段（刷新不回退）；**删除创建后多余的二次 `testConfig`**（`ApiKeyConfigPage.handleFormSubmit` 现行 L94-99）。
- **门禁触发**：创建恒触发；编辑仅在连接相关字段（`base_url`/`api_format`/`api_key`，Key 以非空为变更；**`thinking_enabled`/`thinking_effort` 亦纳入**——探测判据含思考参数）**值与已存值不同**时触发——纯改名/改 models 不触网（前端编辑恒发全量负载，触发判定在后端按「值变化」做）；编辑 Key 留空用已存密钥探测。
- **适用面收窄**：门禁限 `POST/PUT /api-configs` 保存入口；备份包导入（`backup/importer.py:1214`）、库迁移回填（`service.migrate_user_configs`）、朱雀 upsert（`zhuque/service.py:148`）等非保存入口建行路径豁免（旧数据恢复/固定端点，不因离线不可用）；`restore`/`refresh-models` 不动。
- **与既有需求让位**：「编辑态可改接口格式」的「改格式保存后清空模型缓存/测试态」语义改为「门禁以新格式探测通过即为重测完成，更新为本次探测结果」（MODIFIED 收编，避免同动作两套 SHALL 打架）。
- 明确不做：Base URL 自动改写/预填（`c-api-config-vendor-defaults` 已落）；「测试连接」按钮行为与判据不动；老配置历史坏数据不批量重验；探测文案脱状态码改写（沿用现状，另案处理）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`: 新增「保存前连通门禁」要求（判败不落库、判过持久化、嵌套 probe 契约、触发＝值变化（含思考参数）、保存入口豁免面）；「编辑态可改接口格式」收编改格式×门禁让位语义。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：模型配置页「添加 API Key」/「编辑配置」弹层（`ApiConfigForm`）。
- **对象状态**：**复用既有错误语义，零新增 UI**——判败经 `Error.message` 直达表单既有内联 error 位（`ApiConfigForm.handleSubmit` catch→`setError`，弹窗不关）；保存按钮 `saving` busy 态已存在（「保存中…」）。不改提示语气、不加胶囊/条带。
- **共享段**：不触碰（不改 base.css 令牌与基础组件类、不改 pill/notice/sk/panel/f-err 家族）。
- **原型先行**：**不需要**——所需三形态（判败原位展示、弹窗不关、保存中 busy）均由表单既有 error/busy 位覆盖；实现侧仅核对「改动连接字段即清过期 error」点位。
- **设计工件产出**：实现侧自查（含 design:lint 门禁；本 change 无可见样式变化）。

## Impact

- `client/backend/api_configs/service.py`：新增 `ProbeFailed` 异常与门禁探测（create/update，mutation 之前）；抽 `_persist_probe_result`（自 `test_api_config` 抽出，共用写库口径）；删 `update_api_config` 的 300-310「改格式清空」分支。
- `client/backend/api_configs/router.py`：捕获 `ProbeFailed` → 422 `detail {code,status,message}`；create/update 成功响应附嵌套 `probe`。
- `client/backend/api_configs/connection.py`：零改动（复用 `test_connection`，含 `preferred_model`/`thinking_*` 入参）。
- `client/frontend/src/pages/ApiKeyConfigPage.tsx`：删创建后二次 `testConfig`；成功 toast 固定「已添加「X」· 连接正常」；判败由表单 error 位呈现（零新增错误 UI）。
- `client/frontend/src/types/api-config.ts`：`ApiConfig` 加可选 `probe?`。
- 测试：后端 `tests/test_api_key_config.py` 存量 CRUD 用例加默认探测桩（打桩点钉死 `api_configs.service._test_connection`——别名导入陷阱）＋新增门禁用例（判败不落库/判过持久化/值变化触发/思考触发/Key 留空/非 ok 状态参数化/豁免面）；前端 `apiKeyConfigPage.test.tsx` 更新（保存只发一次 POST、不再二次 test）＋`lib/api.ts` 422 对象 detail 提取钉。
- 依赖：`c-ai-availability-fixes`（判据）已归档为硬前置完成态；`c-api-config-vendor-defaults`（预填模型名）已落，收窄「探针 id 猜测」误拦面。
