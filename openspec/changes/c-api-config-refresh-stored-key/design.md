# c-api-config-refresh-stored-key — 设计

## 背景与约束

- 2026-10-09 `c-api-config-edit-model` 把编辑态「获取模型」保持为 raw 轻探针（需明文 Key），
  Key 未重填时禁用，并明记挂账：等后续做「已存密钥刷新清单」再立项。
- `POST /api-configs/{id}/refresh-models` 自 2026-09 起是 stub（恒回空清单），
  2026-10-07 `c-api-config-auto-models` 决定「死代码不动」。本 change 把它接成活端点，
  端点语义正好落在这笔挂账上。
- 清单是配置行里的快照（`models` JSON 列）：新模型上线不会自己出现，只有
  连接测试成功 / 显式拉取才会改写。GLM-5.4（2026-11-23 上线）即撞上这个时间差。

## 决策

### D1 端点复用 `fetch_models`，不新增第二套清单逻辑

`refresh_models_with_stored_key` 只做三件事：查配置行 → 解密 Key → 调 `fetch_models`
（与 `POST /api-configs/fetch-models` 完全同一实现：端点归一、鉴权头、判废、anthropic 404
候选/说明全部同源）。这样「清单是什么」只有一份答案，raw 路与已存密钥路不会分叉。

### D2 落库口径与测试/自动落库一致：非空才写、保头、归一/截断

沿用 `_persist_probe_result` 的两条不变量：

- **非空才写**：空清单（端点不提供）与失败一律不写库——轻探针失败不该把用户可用的快照清空。
- **保头**：配置当前已选模型（models 首项）在清单内时置于首位，其余按供应商原序；
  超 300 条截断保留前 300（`_normalize_models(truncate=True)`）。

### D3 不动连接测试结果字段

`last_test_status` / `last_test_error` / `last_tested_at` 只由真实生成探针（连接测试 /
保存门禁）写。轻探针只证明「清单端点可用」，不证明对话可用——写「连接正常」会是假阳性。

### D4 前端分流：连接参数未变才走已存密钥路

已存密钥轻探针只能用**落库**的连接参数。若用户先在表单里改了 Base URL / 接口格式
（尚未保存）再点「获取模型」，返回的清单会与当前填写值错位。因此：

- Key 留空 且 表单 Base URL / 接口格式 与已存值字面一致 → 已存密钥轻探针；
- 其余（改了参数 / 重填 Key / 新建态）→ raw 轻探针（既有路径不动）。

这与「编辑态未重敲 Key 试连走已存配置」的既有口径同构；改了端点还想看新端点的清单，
本来就需要新 Key 参与 raw 探针。

### D5 刷新成功必须回写编辑目标

页面保存时 models 由 `editConfig.models` 拼装（改选值置首 + 其余保留）。如果刷新只更新
表单内清单、不更新 `editConfig`，保存会按旧快照把刚拉到的新模型整段丢掉（实测路径：
刷新 → 直接保存 → 卡片 chips 回退）。故页面在刷新成功时同步 `setEditConfig`，hook 同步
回填列表 chips。

### D6 失败重试与首次同路

`.mp-err` 的「重新拉取」按当前分流再走一次（已存密钥路失败不退回 raw，否则必然再报
「Key 为空」类错误）。`fetching` / 序号作废与 raw 路共用，切供应商/格式照旧作废在途响应。

## 端点契约

`POST /api/v1/api-configs/{config_id}/refresh-models`

- 404：配置不存在（含不属于当前用户）。
- 400：配置已禁用。
- 200：`{ok, status, models?, candidates?, note?, error?}`——与 `fetch-models` 同形。
  - 成功且清单非空：已落库（保头/归一/截断），`models` 即落库清单；
  - 成功但清单为空：`models: []`，不落库（已存清单保留），可带 `candidates`/`note`；
  - 失败：`ok: false` + `status`/`error`，不落库、不动连接测试结果。

## 边界与不做

- 打开弹窗不自动调（零隐式出网）；只有显式「获取模型」与失败重试触发。
- 不做客户端缓存/频控——单次 GET，量级与「测试连接」同。
- 不新增 GLM 候选登记：该端点会返回真实清单；候选只在「端点不提供清单」时兜底。
- 不改 `fetch-models` raw 端点、不改连接测试、不改保存门禁。

## 测试

- 后端（`tests/test_api_key_config.py`）：已存密钥解密透传＋保头落库；失败不清库；
  空清单不清库且回传候选/说明；未知 id 404。
- 前端（`apiConfigForm.test.tsx`）：已存密钥路可拉到新模型并可改选、已存首项不被覆盖；
  失败提示可重试且重试仍走已存路；改 Base URL 或重填 Key 回 raw 路。
- 前端（`apiKeyConfigPage.test.tsx`）：Key 留空点「获取模型」命中 `refresh-models` 而非
  `fetch-models`；刷新后直接保存，PUT models 为刷新后的清单（不按旧快照覆盖）。
