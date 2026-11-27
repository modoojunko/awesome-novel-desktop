# c-api-config-refresh-stored-key — 编辑配置不必重敲 Key 也能刷新模型清单

## Why

用户实绩（2026-11-27）：GLM-5.4 上线后（Coding Plan 全档可用，官方文档 2026-11-23 起），
模型配置页「编辑配置」里看不到它——GLM 配置的清单还停在上次拉取的 11 个旧模型
（`glm-4.5`/`glm-4.5-air`/`glm-4.7`/`glm-5.3-flash`…）。

根因＝清单是「已存快照」，而编辑态没有刷新出口：编辑弹窗的「获取模型」走 raw 轻探针，
需要明文 Key；Key 未重填时按钮按既有规格禁用（2026-10-09 `c-api-config-edit-model`
明记挂账：「raw 轻探针无『用已存密钥拉清单』的端点；`refresh-models` 端点现为 stub，
如后续要做已存密钥刷新清单再立项」）。新模型上线后，用户只能重敲 Key 或手填 id 才能用上。

`POST /api-configs/{id}/refresh-models` 至今返回 `{"ok": false, "status": "untested",
"models": []}`（2026-10-07 记录为「死代码，不清理」）——本 change 兑现这笔挂账，
把列表来源从「上次保存时的快照」变成「一键可刷新」。

## What Changes

- **已存密钥轻探针（后端）**：实现 `POST /api-configs/{id}/refresh-models`——服务端用落库
  密钥（解密）与已存连接参数（vendor/base_url/api_format）执行与 fetch-models 同款
  「只拉清单」请求（仅 GET 清单端点，零生成调用）。成功且带回**非空**清单：按「已选首项
  保头」归一写库、响应回显同一份清单（与连接测试自动落库同一口径）；清单为空（端点不提供）
  或探针失败：原样透传，SHALL NOT 覆盖已存清单、SHALL NOT 改动连接测试结果字段
  （轻探针不证对话可用）。未知配置 404、已禁用配置 400 语义保留。
- **编辑态「获取模型」不再强制重敲 Key（前端）**：Key 留空、且表单连接参数与已存值一致时
  按钮可用并走已存密钥轻探针；失败重试同一路口径（不退回 raw）。改了 Base URL / 接口格式
  （未保存）或已重填 Key 时仍走 raw 轻探针——清单必须对应当前填写值，不在旧端点上给出错位结果。
- **保存不吞新清单**：刷新成功后页面同步更新编辑目标（`editConfig.models`）——保存时 models
  由它拼装，否则会按旧快照把刚拉到的新模型覆盖回去。
- **卡片同步**：刷新成功顺手回填列表卡片 chips（不额外发请求）。
- 明确不做：打开弹窗即自动联网刷新（保持零隐式出网，只在显式点击/重试时拉）；GLM 候选登记表
  不新增（该端点能返回清单，候选是「端点不提供清单」时的兜底）；拉取频控/缓存策略不动。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`：「模型清单自动拉取」——编辑态按钮门翻案（Key 未重填不再禁用，改走
  已存密钥轻探针）；补该端点契约（零生成、保头落库、失败/空清单不覆盖已存清单、不动连接
  测试结果、重试同路）与「连接参数有未保存变更时仍走 raw」的边界。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：模型配置页「编辑配置」弹层（`ApiConfigForm` 模型名称行的「获取模型」
  按钮与清单失败重试出口）、模型配置页配置卡片 chips（仅数据刷新）。
- **对象状态**：沿用既有按钮「可用/禁用」两态与 `.mp-meta`（已拉到 N 个模型）/
  `.mp-err`（失败提示＋重新拉取）文案位；不新增状态语言、不加新控件。
- **共享段**：不触碰（不改 base.css 令牌与基础组件类，不动 pill/notice/sk/panel/f-err 家族）。
- **原型先行**：不需要——没有新增或改变的可见形态；仅按钮可用条件与 title 提示变化
  （title 属既有 tooltip 位）。实现侧自查 `design:lint`。
- **设计工件产出**：实现侧自查。

## Impact

- `client/backend/api_configs/service.py`：新增 `refresh_models_with_stored_key`
  （解密已存 Key → `fetch_models` 轻探针 → 非空清单保头归一写库；失败/空清单不写）。
- `client/backend/api_configs/router.py`：`POST /api-configs/{id}/refresh-models` 从
  stub 接实现（404/禁用 400 语义保留）。
- `client/frontend/src/components/api-config/ApiConfigForm.tsx`：`onRefreshStoredModels`
  入参；按钮门与重试分流（已存密钥路 vs raw 路）；连接参数字面比对。
- `client/frontend/src/pages/ApiKeyConfigPage.tsx`：接线；刷新成功同步
  `editConfig.models`（保存拼装不吞新清单）。
- `client/frontend/src/hooks/useApiConfigs.ts`：`refreshModels` 类型化并回填列表 chips。
- 测试：后端 `tests/test_api_key_config.py` 新增 4 例（已存密钥透传＋保头落库/失败不清库/
  空清单不清库/未知 id 404）；前端 `apiConfigForm.test.tsx` 新增 3 例（已存路可选新模型/
  失败重试/改连接参数或重填 Key 回 raw）、`apiKeyConfigPage.test.tsx` 新增 1 例（刷新后
  保存不吞新清单）。
