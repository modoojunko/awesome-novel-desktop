# tasks — c-api-config-save-gate（2026-11-23 按 main 现状重排）

> 前置已满足：`c-ai-availability-fixes`（探测判据）已归档；`c-api-config-vendor-defaults`（预填模型名）已落。

## 1. 后端门禁核心（`client/backend/api_configs/service.py` / `router.py`）

- [x] 1.1 抽 `_persist_probe_result(config, outcome)`：写 `last_test_*` ＋ models 归一/截断/首项保头；`test_api_config` 改为调用（既有 `test_test_config_*` 全绿，行为零漂移）
- [x] 1.2 `ProbeFailed(status, message)`；`create_api_config` 在 `db.add` 前探测（生效值：`resolve_vendor` 后 vendor、默认推导后 format、明文 key、`models[0]` 作 `preferred_model`、body 的 `thinking_*`），非 ok 抛 `ProbeFailed`；判过建行＋`_persist_probe_result`
- [x] 1.3 `update_api_config`：生效值（`base_url` 变更重跑 `resolve_vendor`、Key 留空取已存解密 key、`thinking_*` 缺省取已存）→ 按触发集判定 → 探测在**任何 setattr 之前**；判败不落库，判过应用更新＋持久化
- [x] 1.4 删「改格式清空 models/测试态」分支（让位语义替代）；改格式判过＝清单/测试态更新为本次探测结果，判败原配置原样
- [x] 1.5 router：捕获 `ProbeFailed` → `422 detail={code:"probe_failed", status, message}`；成功响应附嵌套 `probe`（`{ok,status,models,error}`）；`ValueError/IntegrityError` 既有映射不动
- [x] 1.6 边界：仅改名/仅改 models 零探测（桩调用计数 0）；`api_key` 空串仍按「未提供」（`router.py` 语义不动）

## 2. 后端测试（`client/backend/tests/test_api_key_config.py` ＋ `test_api_format.py` 存量改造）

- [x] 2.1 默认桩：模块级 autouse fixture patch `api_configs.service._test_connection`（返回 `{ok: True, status: "ok", models: None}`）；存量 CRUD 离线全绿
- [x] 2.2 创建门禁：坏 URL → 422 `detail.code=probe_failed` 且库无行、探测收到明文 Key 与生效参数；判过 → 落库 `last_test_status="ok"`＋响应 `probe`；探测带 models → 落库且首项在头
- [x] 2.3 编辑门禁：改 `base_url` 触发（入参新 URL）；仅改名零调用；改 `api_format` 触发且判过清单/测试态更新、判败原配置不变；改 `thinking_*` 触发且入参带新值
- [x] 2.4 Key 留空：编辑只改 URL → 桩入参为**已存密钥解密值**；判败不落库
- [x] 2.5 「非 ok 即拦」参数化：六状态均 422 且不落库
- [x] 2.6 豁免面：`migrate_user_configs` 迁移与 `restore` 不触探测桩（备份导入/朱雀直建为直建路径，不经 service）

## 3. 前端接线（`client/frontend`）

- [x] 3.1 `ApiKeyConfigPage` 创建分支删二次 `testConfig`；成功 toast 固定「已添加「X」 · 连接正常」；判败经表单 catch→`setError` 呈现（弹窗不关）；卡片状态取响应行＋既有 `refreshStatus`
- [x] 3.2 `types/api-config.ts`：`ApiConfig` 加可选 `probe?`
- [x] 3.3 改动连接相关输入即清过期 error：`ApiConfigForm` 补 `setError(null)`（Key/URL 输入、接口格式、供应商切换、思考开关/强度）

## 4. 前端测试

- [x] 4.1 `apiKeyConfigPage.test.tsx`：创建保存只发一次 `POST /api-configs`、不再发 `/test`；成功 toast；422 场景弹窗不关＋错误文案可见＋改字段清错误
- [x] 4.2 `api-error-message.test.ts`：422 对象 `detail={code,status,message}` → `Error.message`/`ApiError.code`/HTTP status 提取钉
- [ ] 4.3 e2e（降级挂账）：`config-page` 存量「网络错误照常入库」语义与门禁相反，需桩上游改造——本批以单测＋真机走查兜底，e2e 改造另排

## 5. 回归与收尾（实际输出记录）

- [x] 5.1 后端全量 pytest：**3555 passed, 332 skipped, 0 failed**（8m46s）；存量两处触网用例已改造（`test_api_key_format` 的 format 清空断言按 MODIFIED 语义重写）
- [x] 5.2 前端：vitest 全量 **2345 passed**（187 文件）＋`tsc --noEmit` 零错＋`design:lint` 通过（无可见样式变化）
- [x] 5.3 判据抽样：`endpoint_mismatch` 坏 URL 与探测判过两臂由单测覆盖（真端点「你好」探针需 Key，留真机臂）
- [ ] 5.4 真机走查（装包另批）：坏 URL 保存被拦（弹窗不关、文案可读）；真端点保存即「连接正常」且刷新不回退；编辑仅改名零触网（`llm.log` 无新 probe 行）
- [x] 5.5 `openspec validate c-api-config-save-gate --strict` 通过；归档随实现 PR（sync `model-api-config` delta）
