# Tasks — c-api-config-auto-models

## 1. 后端

- [x] 1.1 `connection.py`：新增 `fetch_models()` 轻探针（复用 `_build_probe`；GET-only；anthropic 404 → 空清单＋candidates＋note；Key 空非 ollama → auth_error；200 非 API JSON → endpoint_mismatch）
- [x] 1.2 `schemas.py`：新增 `FetchModelsBody`（vendor_id/base_url/api_key/api_format）
- [x] 1.3 `router.py`：新增 `POST /api-configs/fetch-models`（登录鉴权，透传 `fetch_models` 结果）
- [x] 1.4 `service.py`：`_normalize_models` 加 `truncate` 参数（超 100 截断）；`test_api_config` 自动落库走归一化
- [x] 1.5 `connection.py`：`VENDOR_MODEL_CANDIDATES.deepseek` → `["deepseek-flash", "deepseek-v4-pro"]`（官方文档 2026-10-07 实勘）
- [x] 1.6 pytest：fetch_models 成功/404 降级/网页判废/Key 空/ollama tags；端点契约；落库归一化截断；候选表断言更新

## 2. 前端

- [x] 2.1 `types/api-config.ts`：`FetchModelsResult` 类型（含 candidates/note）
- [x] 2.2 `useApiConfigs.ts`：`fetchRawModels(body)` 调新端点
- [x] 2.3 `ApiConfigForm.tsx`：模型字段改选择器（选中态按钮＋`.sel-panel` 搜索弹层＋手填行＋候选 chips；键盘导航）
- [x] 2.4 自动拉取接线：Key 失焦非空触发；Ollama 免 Key 触发；vendor/URL/格式变更重拉；在途去重（序号丢弃过期响应）；失败 warn＋「重新拉取」
- [x] 2.5 默认选中规则：登记默认 ∈ 清单 → 登记值；否则首项；手选不覆盖；`handleTest` 结果同步刷新清单
- [x] 2.6 vitest：apiConfigForm（触发/默认选中/弹层搜索选择/手填兜底/测试刷新/失败重试）、apiKeyConfigPage（fetch-models 接线＋POST body）、apiVendorDefaults 对齐
- [x] 2.7 字段顺序＝Base URL → API Key → 模型（2026-10-07 用户拍板：模型垫底，Key 失焦拉到的清单喂给紧随其下的选择器）；原型同批对调

## 3. 原型与规格

- [x] 3.1 `docs/design-c/prototypes/model-config.html`：添加弹窗补模型选择器形态（选中态＋弹层＋手填行），design:check 过线
- [x] 3.2 openspec validate --strict 过线

## 4. 端到端与收尾

- [x] 4.1 e2e `config-page.spec.ts` ④ 改造：DeepSeek 流程补 Key 失焦自动拉取（stub 清单）＋选择器默认选中＋POST body 断言保持
- [x] 4.2 隔离栈跑 config-page 全 spec＋design parity；全量 vitest／pytest 绿
- [ ] 4.3 PR（含变更说明与本 change 归档待办）
