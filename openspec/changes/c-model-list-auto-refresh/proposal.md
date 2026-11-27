# c-model-list-auto-refresh — 模型清单后台保鲜：任何选择器打开前就是最新

## Why

用户实绩（2026-11-27）：GLM-5.4 上线后（Coding Plan 全档可用，官方文档 2026-11-23 起），
模型配置页「编辑配置」里看不到它——GLM 配置的清单还停在上次拉取的 11 个旧模型
（`glm-4.5`/`glm-4.5-air`/`glm-4.7`/`glm-5.3-flash`…）。

根因有两层：

1. **清单是已存快照**：全系统唯一持久化的候选清单是 `ApiConfig.models`，书籍模型、助手
   底栏、拆书创建/详情全部只消费 `GET /api-configs` 的这份快照，没有任何 TTL / 定时刷新；
   `models_updated_at` 只被序列化，没有任何「新鲜度」消费者。
2. **没有刷新出口**：编辑弹窗「获取模型」走 raw 轻探针需要明文 Key，Key 未重填时按
   2026-10-09 规格禁用（当时挂账：「`refresh-models` 端点现为 stub，如后续要做已存密钥
   刷新清单再立项」）。

用户要求的是更彻底的口径：**不是「打开选择器时再拉」，而是「使用前清单已经是最新的」**——
打开选择器不能等网络，新模型要在用户看到列表之前就出现。

## What Changes

- **清单后台保鲜端点（后端）**：新增 `POST /api-configs/ensure-models-fresh`（body：
  `config_ids?`/`force?`）。对每个活跃写作配置按 `models_updated_at` 判断：超过 TTL
  （默认 10 分钟）才用已存密钥走只拉清单轻探针（零生成，单次超时 5 秒）；成功按「已选首项
  保头」归一写库，未过期直接回快照。失败记 5 分钟退避（`force` 绕过），已存清单不清空；
  不写 `last_test_*`（轻探针不证对话可用）。同配置单飞、跨配置并发上限 3。
- **已存密钥单配置刷新端点（后端）**：`POST /api-configs/{id}/refresh-models` 从 stub
  接实现（ensure 与编辑弹窗手动「获取模型」共用同一执行体）；成功非空才写，空清单/失败
  原样透传。
- **前端全局 ModelCatalog（单一数据源）**：配置与模型清单收进 `lib/modelCatalog` 模块级
  store（`useSyncExternalStore`）；`useApiConfigs` 改为读写该 store。任何一次保鲜更新的
  清单会推给所有订阅者——书籍模型、助手底栏、拆书页不再各自持有一份可能过期的快照。
- **保鲜调度（使用前更新）**：应用启动、前台每 5 分钟、窗口回焦/可见时触发；进入含模型
  选择的页面/面板（模型配置页、本书模型面板、工作台助手、拆书创建/详情）时再触发；任何
  模型选择器打开时兜底触发。客户端 30 秒节流，服务端 TTL 决定是否真出网。未登录不触网。
- **编辑配置不再要求重敲 Key**：Key 留空且连接参数未改时「获取模型」走已存密钥轻探针，
  失败重试同路；改了 Base URL/接口格式或重填 Key 仍走 raw（清单必须对应当前填写值）。
- **失效选中保留＋标记**：清单更新后不自动改选。当前选中模型不在新清单时，选择器/模型
  面板标「已不在最新清单」，书内就绪度沿用现有 `ai_model ∈ config.models` 判据；不静默换模型。
- **失败轻提示**：保鲜失败不弹 toast、不打断选择；选择器弹层/模型面板显示一行「清单可能
  不是最新」；「正在更新清单…」在途提示同样走这行。
- **保存与卡片不吞新清单**：后台刷新成功后，正在编辑弹窗的清单、配置卡片 chips、列表页
  的编辑目标同步更新；保存时的 models 拼装使用刷新后的清单，不按旧快照覆盖。
- 明确不做：每次生成前强制同步（延迟/成本不划算；生成按绑定模型不变，模型被下架时按真实
  错误提示）；自动改选/自动切换本书模型；图像模型（独立 `image_configs`）；网络推送/服务
  端常驻定时器（只在应用运行时保鲜）；S 端。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`：
  - MODIFIED「模型清单自动拉取」——编辑态「获取模型」不再因 Key 未重填禁用；已存密钥
    轻探针端点契约（保头落库、失败/空清单不覆盖、不动连接测试结果、重试同路、连接参数
    有未保存变更时回 raw）。
  - ADDED「模型清单后台保鲜」——ensure 端点、TTL/退避/单飞/并发/超时、调度触发面、
    全局单一数据源、失效选中保留+标记、失败轻提示、未登录不触网。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：模型配置页（编辑弹窗、卡片 chips）、书设定「模型」面板、写作助手
  底栏模型选择与弹层、拆书创建页模型下拉、拆书详情换模型弹层。
- **对象状态**：沿用既有按钮可用/禁用、`.mp-meta`/`.mp-note`/`.mp-err` 文案位与模型面板
  的无效态提示；不新增状态语言、不加新控件（提示均为一行既有字号文案）。
- **共享段**：不触碰 base.css 令牌与基础组件类。
- **原型先行**：不需要——无新增/改变的可见形态；仅按钮可用条件、提示文案与清单数据
  新鲜度变化。实现侧自查 `design:lint`。
- **设计工件产出**：实现侧自查。

## Impact

- `client/backend/api_configs/service.py`：`refresh_models_with_stored_key`（timeout/回显
  时间戳）；新增 `ensure_models_fresh`（TTL/退避/单飞/并发/超时，逐配置独立 session）；
  `MODEL_LIST_*` 常量与进程内保鲜状态。
- `client/backend/api_configs/router.py`：`POST /api-configs/ensure-models-fresh`（静态路径
  先于参数路径）；`refresh-models` 接实现。
- `client/backend/api_configs/schemas.py`：`EnsureModelsBody`。
- `client/frontend/src/lib/modelCatalog.ts`：模块级 store、`loadModelCatalog`、`ensureModelsFresh`
  （30 秒节流/在途复用/启动竞态暂存）、`useModelCatalog`、`useModelCatalogVersion`、
  `useEnsureModelsFresh`、`useModelCatalogScheduler`。
- `client/frontend/src/hooks/useApiConfigs.ts`：改为 store 适配层（CRUD 写穿、status/test 回填）。
- 触发接线：`App.tsx`（调度器）、`ApiKeyConfigPage`、`ApiConfigForm`、`ModelSettingForm`、
  `Aui2Dock`、`CreateTaskPage`、`TaskDetailPage`、共享 `ModelPicker`（modals.tsx）。
- `client/frontend/src/lib/deconstructApi.ts`：`fetchModelOptions` 保持原接口（拆书页按
  store version 重取）。
- 测试：后端 `tests/test_api_key_config.py`（refresh 5 例＋ensure 6 例）；前端
  `modelCatalog.test.tsx`（7 例）、`apiConfigForm.test.tsx`（3 例）、`apiKeyConfigPage.test.tsx`
  （2 例）。
