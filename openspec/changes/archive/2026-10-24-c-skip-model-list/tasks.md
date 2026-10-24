## 1. 原型先行（C端 用户可见改动硬性流程）

- [x] 1.1 `docs/design-c/prototypes/model-config.html`：「添加/编辑 API Key」弹窗模型名称字段下加勾选控件＋说明行（复用既有表单控件词汇，勾选态演示「获取模型」禁用）
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md`：登记勾选框偏差条目（新增控件的理由与口径）
- [x] 1.3 `npm run design:check` 复跑（model-config 原型在 parity 矩阵内），全绿后进实现

## 2. 后端：schema／迁移／配置包

- [x] 2.1 `api_configs/schemas.py`：`CreateApiConfigBody`/`UpdateApiConfigBody`/`TestRawBody`/`ApiConfigResponse`/`StatusEntry` 增 `skip_model_list`（body 可选默认关；TestRaw 可选覆盖未保存态）
- [x] 2.2 `models/api_config.py` 加 `skip_model_list` 列（Boolean，`server_default="0"`）——新库 create_all 自然具备；旧库带回走 `migration/engine.build_plan` 列交集 server_default 兜底（引擎零改动，本仓无代内 DDL），补旧源库缺列的迁移用例
- [x] 2.3 配置包导出/导入：每条 api_config 携带 `skip_model_list` 键（加键兼容不升 format_version），导入缺键默认 0
- [x] 2.4 `api_configs/service.py`：create/update 落库透传；已存配置测试（`POST /{id}/test`）按已存值分流；raw 测试（`test-raw`）按 body 值分流

## 3. 后端：连接测试降级（connection.py）

- [x] 3.1 `test_connection`：`skip_model_list=1` 时跳过 models GET，直接走 `_fallback_probe` 路径（探针 id 链＝显式覆盖 > 已选/手填 > 候选；无 id 判「请填写模型名称」）；成功信封＝ok＋空清单＋「已跳过模型清单接口」说明
- [x] 3.2 models GET 的 400/401/403/405/429/5xx 分支统一降级：有 id → `_fallback_probe`（探通＝ok＋空清单＋无清单说明；失败按探针形态透传）；无 id 时 401/403 维持「认证失败」、其余按「提示填写模型名」判负
- [x] 3.3 `fetch_models`：400/403/405 返回 ok＋空清单＋candidates＋说明（403 文案兼容权限语义，不标「认证失败」）；401 维持判死；404 维持「异常响应」
- [x] 3.4 留痕核查：skip 时不产生 models_list 行；降级链 models_list＋generation_probe 两行齐全（llm.log 每出网请求恰一行不破坏）

## 4. 后端测试

- [x] 4.1 降级矩阵用例：400/403/5xx＋有 id→探针通＝绿＋空清单＋说明；403＋坏 Key→探针 auth_error 透传；400/405/5xx＋无 id→提示填名；401/403＋无 id→认证失败；404/200 网页体既有用例不回归
- [x] 4.2 skip 用例：skip=1 不发清单请求（桩断言 GET /models 零调用）直探转绿；无 id 拦下；已存测试按已存值、raw 测试按 body 值
- [x] 4.3 fetch_models 用例：403/400/405 新信封（ok＋空清单＋note）；401 判死回归
- [x] 4.4 迁移用例：旧库升级幂等加列、重复启动零变化；配置包导出带键、新包还原、旧包缺键默认关
- [x] 4.5 后端全量 pytest 过（覆盖率门禁：新分支臂臂可达）

## 5. 前端

- [x] 5.1 `types/api-config.ts`：`ApiConfig` 增 `skip_model_list`；表单数据流透传
- [x] 5.2 `ApiConfigForm.tsx`：模型名称字段下勾选框＋说明行；ollama 隐藏；勾选后三处自动拉取入口（Key 失焦／vendor・URL・格式变更／「获取模型」按钮）统一以 `canAutoFetch` 派生条件关闸，按钮禁用＋title 说明
- [x] 5.3 `ApiKeyConfigPage.tsx`：create/update/test-raw 请求体透传 `skip_model_list`
- [x] 5.4 vitest：勾选联动（自动拉取不触发、按钮禁用）、编辑回读已存值、保存透传；`tsc` 过

## 6. 收尾门禁

- [x] 6.1 e2e：模型配置相关 spec 回归（连接测试红/绿路径、手填保存）；如涉存量断言同批改钉
- [ ] 6.2 真机抽检：CloudBase 浑元配置（`ai-novel-test` 环境）勾选后测试转绿、健康闸开、生成实际出文
- [x] 6.3 `openspec validate --specs` 过；归档时按 sync 流程回写主 spec（MODIFIED 两 Requirement 整块对拍）
