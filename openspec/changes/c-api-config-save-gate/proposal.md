# c-api-config-save-gate — 保存模型配置先过连通门禁，URL 不对当场拦下

## Why

内测（2026-10-05）实锤：用户把 Base URL 填成 DeepSeek 控制台**网页**（`platform.deepseek.com/api_keys`），配置却顺利保存并显示「连接正常」——两层失守叠加：

1. **判据假阳性**：旧连接判据只看 HTTP 200，SPA 网站对任意路径回 200 HTML 也算「通」（判据收紧已在 `c-ai-availability-fixes` 落）；
2. **暴露时机错位**（本 change 主治）：创建流程是「**先落库、再顺手测**」——`POST /api-configs` 落库前零探测，落库后自动测试失败也不拦（弹窗照关、配置照存，只在 toast 尾巴缀「· 请检查 Key」）。用户没有任何一步被要求面对「这个地址不对」，坏 URL 一路进库到生成期才炸。

「测试连接」判得再准，也只是个用户可以不点的按钮。URL 不对必须在**保存（创建/编辑）这一步**就暴露并拦下。

## What Changes

- **保存门禁（后端单源）**：`POST /api-configs`、`PUT /api-configs/{id}` 在落库前执行连接探测——与「测试连接」同一探测实现、同一判据；探测判败（非 ok 的一切形态，含 unknown，按「非 ok 即拦」不按白名单）SHALL NOT 落库，返回结构化 422（detail：`code=probe_failed`＋`status`＋`message`＝探测原文案，复用前端 `lib/api.ts` 既有 `detail.message` 提取路径），前端弹窗原位展示、保持打开。**BREAKING**：create/update 契约新增探测失败 422 分支；无真实存量用户（2026-09-18 拍板），不做兼容回落；v0.27 内测库按原地升级口径接受新行为。
- **判过即持久化**：探测结果写入测试结果字段（`last_test_status`/`last_test_error`/`last_tested_at`/`models`，与连接测试同源）；保存响应携带嵌套 `probe`（ok/status/models/note，不与配置对象顶层 `status`/`models` 撞名），前端据此置卡片状态（刷新不回退）；**删除创建后多余的二次 `testConfig`**。
- **门禁触发**：创建恒触发；编辑仅在连接相关字段（`base_url`/`api_format`/`api_key`，Key 以非空为变更）**值与已存值不同**时触发——纯改名/改 models 不触网（前端编辑恒发全量负载，触发判定在后端按「值变化」做）；编辑 Key 留空用已存密钥探测。
- **适用面收窄**：门禁限 `POST/PUT /api-configs` 保存入口；备份包导入、库迁移回填、朱雀 upsert 等非保存入口建行路径豁免（旧数据恢复/固定端点，不因离线不可用）。
- **与既有需求让位**：「编辑态可改接口格式」的「改格式保存后清空模型缓存/测试态」语义改为「门禁以新格式探测通过即为重测完成，更新为本次探测结果」（MODIFIED 收编，避免同动作两套 SHALL 打架）。
- 明确不做：Base URL 自动改写/预填（由 `c-api-config-vendor-defaults` 承接，2026-10-05 拍板反转旧「URL 不预填」）；「测试连接」按钮行为与判据不动（收紧在 `c-ai-availability-fixes`）；老配置历史坏数据不批量重验；探测文案脱状态码改写（沿用现状，另案处理）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`: 新增「保存前连通门禁」要求（判败不落库、判过持久化、嵌套 probe 契约、触发＝值变化、保存入口豁免面）；「编辑态可改接口格式」收编改格式×门禁让位语义。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：模型配置页「添加 API Key」/「编辑配置」弹层（原型 `docs/design-c/prototypes/model-config.html`）。
- **对象状态**：复用既有错误语义——门禁判败呈现在弹窗连接测试结果位（`tresult bad` 同款 err 语气）＋保存中按钮 busy 态（「保存中…」spinner，沿 ZhuquePanel 范式）；不新增提示语气、不新增胶囊/条带形态。
- **共享段**：不触碰（不改 base.css 令牌与基础组件类、不改 pill/notice/sk/panel/f-err 家族）。
- **原型先行**：需要——`model-config.html` 补「保存判败原位展示、弹窗不关」＋「保存中 busy」＋「改字段旧错误清除」形态，偏差登记 `ADJUSTMENTS.md`。
- **设计工件产出**：实现侧自查（含 design:lint/design:check 门禁）。

## Impact

- `client/backend/api_configs/router.py`、`service.py`：create/update 落库前探测、结构化 422（detail `{code,status,message}`）、判过持久化测试结果字段、响应附嵌套 `probe`。
- `client/backend/api_configs/connection.py`：复用 `test_connection`（判据依赖 `c-ai-availability-fixes` 组 5「你好」探针，硬前置）。
- `client/frontend/src/pages/ApiKeyConfigPage.tsx`、`src/components/api-config/ApiConfigForm.tsx`：判败留在弹窗原位报错（probe_failed→tresult、409/网络/503→ferr 分流）＋改连接字段清过期错误＋保存按钮 busy 态；删创建后二次 `testConfig`；卡片状态取保存响应。
- 测试：后端新增保存门禁用例（判败不落库/判过持久化/值变化触发/Key 留空/unknown 形态/豁免面）、`conftest` 统一探测桩（打桩点 `api_configs.service._test_connection`，防别名导入陷阱）＋存量 CRUD 用例免触网改造、前端 `apiConfigForm`/`apiKeyConfigPage` 用例、`lib/api.ts` `detail.message` 提取钉、config-page e2e 新增＋存量 ②③「网络错误照常入库」用例改造（造数走桩上游/后端种子）。
- 原型：`docs/design-c/prototypes/model-config.html`＋`ADJUSTMENTS.md` 登记。
- 依赖：`c-ai-availability-fixes` 组 5（「你好」禁思考最小生成判据）为本 change 硬前置；`c-api-config-vendor-defaults`（预填模型名）同批可消「探针 id 猜测」误拦面，互不阻塞。
