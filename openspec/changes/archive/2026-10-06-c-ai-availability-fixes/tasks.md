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
- [x] 4.3 提交＋PR（标题不带硬编码 PR 号）；打包随下一版本窗口（内测同学需要修好的包才能复验 3.3）
  - 证据：PR #689 已合入 main（squash 504d0f18）

## 5. 探针升级为「你好」真实生成（2026-10-05 用户拍板；取代 3.1/3.2 的探针语义）

- [x] 5.1 `connection.py` 对话探针改造：payload 换「你好」＋关闭思考（openai 走 `extra_body={"thinking": {"type": "disabled"}}`／anthropic 走 `thinking: {"type": "disabled"}`，与 `ai_client` 禁思考约定同源；端点拒绝该参数时去参重试一次）＋短输出预算（max_tokens=32）；成功判据改为「响应体按接口格式可解析出助手回复且含可见回复文本」（openai `choices[0].message.content`／anthropic text 块），400/422 业务性拒绝由「不拦」翻转为判败并点名所试模型 id；探针模型 id 取用顺序＝配置已选模型→列表首个→vendor 候选首个→anthropic 占位探测模型；anthropic 降级路径同此探针（`POST {base}/v1/messages`）
  - 证据：`_probe_chat_path`／`_build_probe` fallback／`_post_with_thinking_retry`／`_openai_reply_text`／`_anthropic_reply_text` 落地（PR #689 第 3 笔）
- [x] 5.2 `tests/test_api_format.py` 探针用例随语义翻转：原「探针 400 宽松」改判败点名 id；补「2xx 空回复判败」「2xx 格式错体判败」「thinking 拒绝去参重试」「你好 payload＋禁思考参数断言」「anthropic 降级走最小生成」用例；全套绿
  - 证据：探针组 **46/46 绿**（旧宽松钉翻转＋新增 6 钉：空回复/错体/thinking 重试/无 id 提示/降级空回复/429）；`test_ai_layers` 降级桩随语义补真回复
- [x] 5.3 `client/backend` 全量 pytest 复跑零红＋`openspec validate c-ai-availability-fixes --specs` 复验通过
  - 证据：全量 **1819 passed / 0 failed**
- [x] 5.4 无可用模型 id 分支（评审揪出）：openai 格式模型列表为空且无候选时由「跳过对话探针报通」改为判失败并提示填写模型名＋用例
  - 证据：`test_no_model_id_fails_with_prompt` 绿（断言错误含「模型名称」且无 POST 发出）

## 6. 评审整改（PR #689 review-agent 三发现）

- [x] 6.1 **P0**：探针在 `async with` 之外发起（client 已关闭→RuntimeError 炸掉 openai 成功路径）——判定与探针整体收进 client 存活期；补真 httpx 生命周期回归钉（`test_probe_within_real_client_lifecycle`，MockTransport 无 fake 关闭盲区）
- [x] 6.2 **P3**：anthropic 列表可用时零探针与判据文本不一致——实现补齐 `POST {base}/v1/messages`「你好」探针（`_probe_generation` 双格式共用），spec 补「anthropic 格式对话探针」场景
- [x] 6.3 **P3**：文件头「max_tokens=1 最小请求验证鉴权」过时段落更正
  - 证据：探针组 47/47 绿；全量 pytest 复跑见 PR
