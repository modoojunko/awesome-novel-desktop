# tasks — c-model-list-auto-refresh

## 1. 后端：单配置已存密钥刷新（`client/backend/api_configs`）

- [x] 1.1 `service.refresh_models_with_stored_key(db, user_id, config_id, timeout?)`：查行（无行返回 None）→ 解密已存 Key → `fetch_models`（与 raw 端点同一实现，零生成）
- [x] 1.2 落库口径：成功且清单非空 → 已选首项保头 → `_normalize_models(truncate=True)` → 写 `models`/`models_updated_at` 并 commit，响应回显同一份清单与时间戳；清单为空/失败不写库
- [x] 1.3 不动 `last_test_status`/`last_test_error`/`last_tested_at`（轻探针不证对话可用）
- [x] 1.4 `router`：`POST /api-configs/{config_id}/refresh-models` 接实现，保留 404（无行）与 400（已禁用）语义

## 2. 后端：清单后台保鲜 ensure（`client/backend/api_configs`）

- [x] 2.1 `MODEL_LIST_*` 常量（TTL 600s / 退避 300s / 超时 5s / 并发 3，均可 env 覆盖）＋进程内单飞锁/失败退避表
- [x] 2.2 `service.ensure_models_fresh(user_id, config_ids?, force?)`：按 `models_updated_at` TTL 判断；过期用已存密钥轻探针；成功保头写库；失败退避且不清快照；非 active/无 Key 跳过；逐配置独立 session＋并发上限
- [x] 2.3 `schemas.EnsureModelsBody`；`router` 新增 `POST /api-configs/ensure-models-fresh`（静态路径先于参数路径）
- [x] 2.4 成功/失败均不动 `last_test_*`；响应 `{configs:[{id, models, models_updated_at, refreshed, ok, error}]}`

## 3. 后端测试（`tests/test_api_key_config.py`）

- [x] 3.1 refresh：已存密钥解密透传＋已存连接参数＋保头落库，响应与落库同一份（`models_updated_at` 非空）
- [x] 3.2 refresh：探针失败/空清单/畸形清单不覆盖已存清单；未知配置 404
- [x] 3.3 ensure：刚创建（TTL 内）零出网；过期刷新且不动 `last_test_status`；force 绕过 TTL
- [x] 3.4 ensure：失败退避（期内不再出网）＋force 重试；空清单不清快照；`config_ids` 过滤

## 4. 前端：全局 ModelCatalog（`client/frontend/src/lib/modelCatalog.ts`）

- [x] 4.1 模块级 store（`useSyncExternalStore`）：configs/loading/error/refreshing/lastErrors/ensureError/version
- [x] 4.2 `loadModelCatalog`（多实例单飞；启动竞态：先到的 ensure 结果暂存，load 后并入）
- [x] 4.3 `ensureModelsFresh`（30s 节流、在途复用、force 绕过、未登录不触网；成功合并清单并递增 version）
- [x] 4.4 `useModelCatalog` / `useModelCatalogVersion` / `useEnsureModelsFresh(enabled)` / `useModelCatalogScheduler`（启动＋5min 定时＋focus/可见）
- [x] 4.5 测试隔离：`modelCatalogReset` 注册桥＋test-setup 逐用例重置（不直接 import store，避免 mock lib/api 的用例绑死真实 request）

## 5. 前端：接线与提示

- [x] 5.1 `useApiConfigs` 改为 store 适配层：CRUD 写穿、status/test 局部回填（undefined 不覆盖已有值）
- [x] 5.2 `App` 挂调度器；`ApiKeyConfigPage`、`ApiConfigForm`（编辑打开）、`ModelSettingForm`、`Aui2Dock`、`CreateTaskPage`、`TaskDetailPage` 进页面/面板即 ensure
- [x] 5.3 共享 `ModelPicker` 打开时 ensure；弹层轻提示（正在更新/可能不是最新/当前选择已不在最新清单）
- [x] 5.4 编辑弹窗：编辑态「获取模型」Key 留空走已存密钥路（失败重试同路；改连接参数/重填 Key 回 raw）；后台清单更新后弹窗清单就地刷新＋失效选中标记
- [x] 5.5 本书模型面板：ensure＋「正在更新/可能不是最新」＋失效选中标记；拆书创建/详情：按 store version 重取选项＋轻提示＋失效选项标注
- [x] 5.6 保存与卡片不吞新清单：页面同步 `editConfig`、hook 回填 chips

## 6. 前端测试

- [x] 6.1 `modelCatalog.test.tsx`：加载/合并与 version/lastErrors/节流/请求失败/启动竞态/挂载触发（7 例）
- [x] 6.2 `apiConfigForm.test.tsx`：已存密钥路可拉到新模型、失败重试同路、改参数回 raw、清单就地刷新、失效标记（新增 5 例）
- [x] 6.3 `apiKeyConfigPage.test.tsx`：Key 留空点「获取模型」命中 `refresh-models`；刷新后保存不吞清单；进页面保鲜后弹窗直接可选新模型（新增 2 例）

## 7. 回归

- [x] 7.1 后端：`tests/test_api_key_config.py` 122 passed；ruff 全绿
- [x] 7.2 前端：vitest 全量 188 文件 / 2364 passed（1 skipped）；`tsc --noEmit` 零错
- [ ] 7.3 真机走查（待装包）：不开任何刷新按钮——启动后进入 GLM 配置编辑/本书模型/助手底栏，清单已含 `glm-5.4`；断网/坏端点时选择器显示「可能不是最新」且旧清单仍可选；选中被下架的模型显示「已不在最新清单」
