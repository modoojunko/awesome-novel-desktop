## 1. 后端（client/backend/api_configs）

- [x] 1.1 `schemas.py`：`TestConfigBody{model?}`（已存配置测试的可选请求体）。
- [x] 1.2 `router.py`：`POST /api-configs/{config_id}/test` 接受可选 body，透传 `preferred_model`。
- [x] 1.3 `service.py`：`test_api_config` 增 `preferred_model` 参数——覆盖（strip 非空）＞已存 `models[0]`。
  - 回执：✅ 实现随 PR #789。

## 2. 前端（client/frontend/src）

- [x] 2.1 `hooks/useApiConfigs.ts`：`testConfig(id, model?)` 可选覆盖透传。
- [x] 2.2 `components/api-config/ApiConfigForm.tsx`：编辑态渲染模型选择器（种子＝已存清单、初值＝`models[0]`、种子视同手选、`listFresh` 文案分源）；放开拉取门（获取模型按钮/失焦自动拉取）；编辑态格式切换不施加预填；空清单种子手填引导文案。
- [x] 2.3 `pages/ApiKeyConfigPage.tsx`：编辑保存改选值置 models 首项随 PUT（留空省略字段）；未重敲 Key 测试连接把表单模型传 `testConfig` 作覆盖。
  - 回执：✅ 合入 main = fb505377（2026-10-09，PR #789，CI 双绿）。

## 3. 测试

- [x] 3.1 后端：`test_test_config_model_override`（body.model 覆盖＋空串回落已存首项）；全量 1854 passed。
- [x] 3.2 前端：`apiConfigForm` 编辑态用例×5（模型选择位种子与改选/重填 Key 自动拉取且种子不被覆盖/获取模型按钮门/测试带改选模型/重置再种子）；`apiKeyConfigPage` 页面层用例×3（改选置首随 PUT/未改原样随 PUT＋测试带覆盖/清空省略 models）＋清空后测试两路径用例。
- [x] 3.3 门禁：前端 1373 passed＋v8 分支覆盖率 100% 达标（门禁抓出 Key 失焦 if 反向臂、页面 `|| undefined`／`|| null` 右臂三处新分支，已用清空模型用例补回）；tsc 干净；ruff 干净。
