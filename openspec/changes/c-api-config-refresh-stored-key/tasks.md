# tasks — c-api-config-refresh-stored-key

## 1. 后端（`client/backend/api_configs`）

- [x] 1.1 `service.refresh_models_with_stored_key(db, user_id, config_id)`：查行（无行返回 None）→ 解密已存 Key → `fetch_models`（与 raw 端点同一实现，零生成）
- [x] 1.2 落库口径：成功且清单非空 → 已选首项保头 → `_normalize_models(truncate=True)` → 写 `models`/`models_updated_at` 并 commit，响应回显同一份；清单为空/失败不写库
- [x] 1.3 不动 `last_test_status`/`last_test_error`/`last_tested_at`（轻探针不证对话可用）
- [x] 1.4 `router`：`POST /api-configs/{config_id}/refresh-models` 接实现，保留 404（无行）与 400（已禁用）语义

## 2. 后端测试（`tests/test_api_key_config.py`）

- [x] 2.1 已存密钥解密透传＋已存连接参数＋保头落库，响应与落库同一份（`models_updated_at` 非空）
- [x] 2.2 探针失败：原样透传，已存清单不变
- [x] 2.3 端点不提供清单（空清单）：回传候选/说明，已存清单不变
- [x] 2.4 未知配置 404

## 3. 前端（`client/frontend`）

- [x] 3.1 `ApiConfigForm`：新增 `onRefreshStoredModels`；按钮门——编辑态 Key 留空且表单 Base URL/接口格式与已存值一致时可用，title 改「用已存 API Key 重新拉取清单」
- [x] 3.2 `ApiConfigForm`：清单重拉分流（已存密钥路 vs raw 路）；`.mp-err`「重新拉取」与首次同路；两路共用序号作废/`fetching`/结果落地
- [x] 3.3 `ApiKeyConfigPage`：接线 `refreshModels(id)`，成功同步 `editConfig.models`（保存拼装用刷新后清单）
- [x] 3.4 `useApiConfigs.refreshModels`：返回类型 `FetchModelsResult`，成功回填列表卡片 chips

## 4. 前端测试

- [x] 4.1 `apiConfigForm.test.tsx`：已存密钥路可拉到 `glm-5.4` 并可改选、已存首项不被覆盖；失败提示可重试且重试仍走已存路；重填 Key 回 raw 路；改 Base URL 未保存时已存路禁用
- [x] 4.2 `apiKeyConfigPage.test.tsx`：Key 留空点「获取模型」命中 `refresh-models`（不碰 `fetch-models`）；刷新后直接保存，PUT models 为刷新后的清单

## 5. 回归

- [x] 5.1 后端：`tests/test_api_key_config.py` 115 passed；`test_ai_layers.py`/`test_llm_probe_logging.py`/`test_modelconfig_gemini_go.py` 94 passed/21 skipped；ruff 全绿
- [x] 5.2 前端：vitest 全量 187 文件 / 2352 passed（1 skipped）；`tsc --noEmit` 零错
- [ ] 5.3 真机走查（待装包）：GLM 配置编辑弹窗点「获取模型」→ 清单出现 `glm-5.4` → 改选保存 → 卡片 chips 含新模型；断网/坏端点下失败提示可重试
