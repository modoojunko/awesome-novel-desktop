## 1. 门禁归位（#679 互换修复）

- [x] 1.1 `write/router.py`：`POST /write` 挂回 `ai-generate`、`POST /write/polish` 挂回 `ai-polish`（口径单源 `docs/contracts/entitlement-defaults.json` v2；tier-plan-four-tiers tasks 3.2「ai-polish×1（去AI味 /polish）」）
- [x] 1.2 `tests/test_ai_feature_http.py` 补 4 条档位回归钉（standard 打 /write→403 feature_required(pro)；trial 过门；pro 打 /write/polish→403(max)；max 过门）；修复前 3 红、修复后 6/6 绿实证

## 2. 生成期可诊断（内测 405 案）

- [x] 2.1 `ai_client.py`：上游 404/405 归一 `AIRequestError`（文案点名实际请求地址 `{base}/chat/completions` / `{base}/v1/messages` 与「模型配置」去处）；chat 与 chat_stream 双路径；非 404/405 原样透传不改写
- [x] 2.2 `tests/conftest.py` SDK stub 补 `APIStatusError`（真 SDK 同形：`status_code = response.status_code`）；`_guarded` 归一改实例方法（业务异常路径不触碰 provider/base_url，裸实例测试路径兼容）
- [x] 2.3 `tests/test_ai_client_upstream_errors.py` 新增 4 例（openai 405 / anthropic 405 / 流式 405 / 400 透传）

## 3. 连接测试收紧（「通」＝对话路径可用）

- [x] 3.1 `connection.py`：200 非 JSON 判败（网页/SPA 首页误报「连接正常」的口子）；anthropic 降级探针 404/405 判败；openai 追加对话探针（`POST {base}/chat/completions`，与生成同址同鉴权头，max_tokens=1，id＝列表首个/候选，400/422 不拦）
- [x] 3.2 `tests/test_api_format.py`：fake 扩展 payload/content-type＋新增 6 例（HTML 判败/错误信封判败/探针 200 同址断言/探针 405 点名地址/探针 400 宽松/降级 405 判败/候选 id 路径）；`test_ai_layers` 假体补 headers；全套 38/38 绿
- [ ] 3.3 真机复验：用错误 Base URL 配置点「测试连接」应报失败并给出提示；内测「去AI味」链路复验（需内测同学提供模型配置截图——待用户侧回收）

## 4. 验收与收尾

- [x] 4.1 `client/backend` 全量 pytest：1807 passed / 0 failed（改动前存量 2 红已随判据更新归零：`test_ai_layers` 假体补 headers、`test_ai_timeout_accounting` 语义随新归一更新为 400 透传钉）
- [x] 4.2 `openspec validate c-ai-availability-fixes --specs` 通过
- [ ] 4.3 提交＋PR（标题不带硬编码 PR 号）；打包随下一版本窗口（内测同学需要修好的包才能复验 3.3）
