# design — c-api-config-save-gate（2026-11-23 按 main 现状重做）

## Context

动机见 proposal（Why 两层失守）。本稿基于 2026-11-23 对 main（`9fcc04fb`）的重新扫描，替换 2026-10-05 旧稿。核心现状（行号已对当前代码逐一核实）：

- **保存链（前端）**：`ApiKeyConfigPage.handleFormSubmit`（`src/pages/ApiKeyConfigPage.tsx:73-103`）——创建＝`addConfig`（POST 直落库）→ `testConfig(newConfig.id)`（non-blocking，失败只改 toast 尾巴）→ 关弹窗；编辑＝`updateConfig`（PUT，Key 空省略字段）。
- **表单已具备门禁 UX 所需的两个位**：`ApiConfigForm.handleSubmit`（`src/components/api-config/ApiConfigForm.tsx:329-350`）已有 `saving` busy 态与内联 `error` 位（提交异常 `setError`、弹窗保持打开）——**本 change 不需要新增 UI，也不需要改原型**（旧稿的「原型先行」要求由现状满足）。
- **错误透传已通**：`src/lib/api.ts:238` 对 4xx 非字符串 `detail` 取 `detail.message` 作为 `Error.message`（对象 detail 已有 `member_required`/`feature_required` 先例；`detail.code` 走 `ApiError.code`）——422 结构化 detail 直达表单 error 位，零解析层改动。
- **后端点位**：`api_configs/router.py` `create_config`(117)/`update_config`(226) 直落库零探测；`service.create_api_config`(105) 建行、`update_api_config`(255) 应用更新，**其中 `api_format` 变更会清空 models/测试态（300-310）**；探测单源 `connection.test_connection`(175)，返回 `{ok,status,models,error}`，status 集合＝`ok/auth_error/rate_limited/timeout/network_error/endpoint_mismatch/unknown`；`CONNECTION_TEST_TIMEOUT` 默认 10s。
- **探测签名已含思考参数**（c-thinking-config 之后新增，旧稿没有）：`test_connection(..., preferred_model, thinking_enabled, thinking_effort)`——门禁探测必须带表单当前思考值，才与「测试连接」同一判据。
- **结果持久化唯一写点**：`service.test_api_config`(187-252)——写 `last_test_status/last_test_error/last_tested_at/models`，含 c-api-config-auto-models 的归一化/截断与「首项保头」（评审 P1-2）。门禁必须复用同一套写库口径。
- **服务别名导入**：`service.py:18` `from .connection import test_connection as _test_connection`——测试打桩点**必须是** `api_configs.service._test_connection`（patch `api_configs.connection.test_connection` 不生效；既有 `test_test_config_*` 用例已是此口径）。
- **豁免直建路径（不经 create/update，天然豁免，已逐一核实）**：`backup/importer.py:1214`（备份恢复直建）、`zhuque/service.py:148`（朱雀配置直建）、`service.migrate_user_configs`(867)（旧字段迁移 lifespan）；`restore_api_config`(359) 只翻状态；`refresh-models` 不改保存入口。

## Goals / Non-Goals

**Goals:**

- 坏 URL/坏 Key 在保存动作当场被拦、原位暴露；落库数据保证「探测通过」（限 `POST/PUT /api-configs` 保存入口）。
- 探测判据与「测试连接」严格同一份（含思考参数与模型优先序）。
- 判过持久化与卡片状态链路自洽（刷新不回退）；一次保存只打一次上游探测；纯改名/改模型清单不触网。

**Non-Goals:**

- 不改探测判据本身（在 `c-ai-availability-fixes`，已归档）。
- 不做 URL 自动改写/预填（`c-api-config-vendor-defaults` 已落）。
- 不对存量配置批量重验；不给导入/迁移/朱雀/restore 路径加门禁。
- 不给「探测失败仍要保存」的逃生口。
- 不改写探测文案的状态码裸露问题（沿用现状，另案）。

## Decisions

1. **门禁落点＝service 层 `create_api_config` / `update_api_config`（单源，探测在任何 ORM 变更之前）**，router 保持薄：service 抛 `ProbeFailed(status, message)`，router 统一转 `422`，`detail = {"code": "probe_failed", "status": <探测 status>, "message": <探测原文案>}`（`message` 键对齐 `lib/api.ts:238` 既有提取路径；`code` 走 `ApiError.code`）。备选「前端先测后存」可绕过、双往返、响应无从带结果——否。
2. **判败即拦全集，按「非 ok 即拦」**（`endpoint_mismatch`/`auth_error`/`timeout`/`network_error`/`rate_limited`/`unknown` 均拦），不按白名单枚举。弱网/离线/Ollama 未启动时无法保存是接受的代价（内测反馈再议逃生口）。
3. **触发集**：创建恒触发；编辑按**值变化**触发——`base_url`、`api_format`、`api_key`（router 已保证空串不进入 updates＝非空才算变更，`router.py:240`）、**`thinking_enabled`、`thinking_effort`（本稿新增：探测判据含思考参数，改思考值会让上游请求形态变化，必须重测；旧稿 2026-10-05 时尚无思考参数）**；`name`/`models`/`vendor_override` 单独变更不触发（`vendor_override` 单独改不改变探测输入——`update_api_config` 只重识别 vendor 于 `base_url` 变更时；`base_url` 变更的组合已被触发，探测用生效值重识别 vendor）。前端编辑恒发全量负载不需要改，触发判定在后端按「值变化」做。
4. **探测输入＝保存后的生效值**：`base_url`＝新值；`api_format`＝新值（create 未传时按既有默认推导，`service.py:127-136`）；`api_key`＝新值或（编辑留空时）解密后的已存密钥（不报「API Key 为空」）；`vendor_id`＝按生效 `base_url`＋生效 `vendor_override` 重跑 `resolve_vendor`；`preferred_model`＝新 `models` 首项（改了模型选择）否则已存首项；`thinking_*`＝updates 有值用新值，否则已存值。
5. **判过持久化复用测试连接同一写库口径**：从 `test_api_config` 抽出 `_persist_probe_result(config, outcome)`（写 `last_test_status/last_test_error/last_tested_at`；`outcome.models` 非空时按 `_normalize_models(truncate=True)` 归一/截断并保首项在头），`test_api_config` 与门禁共用——行为零漂移由既有 `test_test_config_*` 用例钉住。
6. **响应新增嵌套 `probe`**：`{ok, status, models, error}`（`test_connection` 原样 outcome；不单独造 `note` 键——现状 outcome 无 note 概念）。Additive：配置对象顶层既有 `status`/`models` 不动，`probe` 嵌套防撞名；前端类型加 `probe?`，卡片状态仍以落库字段为准（响应里已含 `last_test_*`）。
7. **改接口格式让位**：删除 `update_api_config` 的 300-310 清空分支——改格式经保存入口时，门禁以新格式探测：判过 → 模型清单/测试态写为本次探测结果（探测未返回清单时保留原清单，沿 `test_api_config` 语义）；判败 → 更新不落库、原配置（含原格式/清单/测试态）原样。
8. **前端改动最小化**：创建分支删除二次 `testConfig`（L94-99），toast 固定「已添加「X」· 连接正常」（判败由表单 error 位呈现，不改 toast）；成功落库后表单关闭、卡片状态取响应行（`useApiConfigs.addConfig` 已把响应行写入列表）＋既有 `refreshStatus` 回读。改动连接相关输入即清过期 error（表单已有 `setError(null)` 点位，核对覆盖 Key/URL/格式/思考）。
9. **测试打桩策略**：`test_api_key_config.py` 存量 CRUD 用例统一默认桩（autouse fixture：`monkeypatch.setattr("api_configs.service._test_connection", fake_ok)`，默认 `{ok: True, status: "ok", models: None}`——不改变既有「models 默认空」断言），门禁用例逐个覆盖 fake（判败机臂、调用计数、入参快照）。

## 现状差异裁决（相对 2026-10-05 旧稿）

- **新增**：思考参数纳入触发集与探测入参（Decision 3/4）；持久化抽 helper（Decision 5）；`probe` 形状按现状 `error`（Decision 6）。
- **删除**：原型先行要求（表单 busy/error 位已在，无需改原型）；旧稿「前端 tresult/ferr 分流」细化——现状表单只有一个内联 error 位，422 文案直达即可。
- **修正**：旧稿「后端同时收紧空串=未提供」——现状由 `router.py:240` 已收紧，design 只依赖该语义；打桩点已确认别名导入（Decision 9）。

## Risks / Trade-offs

- **[保存动作变长（最坏多跳×10s 超时，30s 量级）]** → 表单 `saving` busy＋Modal locked 已覆盖；失败即时可改可重试；不设总预算（接受）。
- **[弱网/离线/Ollama 未启动不能保存]** → 接受（Decision 2）；错误文案即探测文案；内测若反馈集中再议逃生口。
- **[存量后端测试集体触网翻红]** → autouse 默认桩（Decision 9）；打桩点别名已钉死。
- **[端点无模型清单且未填模型名 → `unknown` 被拦]** → `c-api-config-vendor-defaults` 预填模型名＋`preferred_model` 取表单模型，大幅收窄；错误文案点名「请填写模型名称」，可行动。
- **[存量 e2e「网络错误照常入库」语义相反]** → 属改造面（tasks 4.3），门禁后必须改；e2e 成功臂可用本地假上游桩（`page.route` 拦不到后端 httpx 出网，参照 ai-assist `STUB_BASE` 先例）——若桩成本高，e2e 降级挂账、以单测＋真机走查兜底。

## Migration Plan

无数据迁移、无 schema 变更。API 契约变化（create/update 新增探测失败 422 分支、响应新增嵌套 `probe`、判过写既有测试结果字段）按 **BREAKING** 记录：现网客户端升级后同一入口即新行为（弱网/离线保存被拦属预期变化）；回滚＝还原提交，无状态残留（写入的是既有测试结果字段）。

## Open Questions

（无）
