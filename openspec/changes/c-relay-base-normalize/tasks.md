## 1. 归一单源与探针链路

- [x] 1.1 `api_configs/connection.py` 新增 `_VERSION_SEG` 段锚正则与 `normalize_openai_base`（裸域名补 `/v1`；版本段段以 `v+数字` 开头即算；rstrip 尾斜杠）
- [x] 1.2 `_openai_models_url` 收口走归一（替掉行尾锚内联判断）
- [x] 1.3 对话探针主链（test_connection 内 `POST {base}/chat/completions`）与 `_build_probe` 404 降级 fallback 地址同走归一
- [x] 1.4 `ai_client._init_client` openai 分支：base 先归一再传 SDK，`self._base_url` 同步归一形（留痕/禁思考记忆同形）；anthropic 分支不动
- [x] 1.5 `_non_api_response` 网页体文案追加「（若地址确认无误，尝试在末尾补 /v1）」；模块 docstring 归一口径同步

## 2. 测试

- [x] 2.1 `TestNormalizeOpenAiBase` 参数化钉子：裸域名补 /v1（kakou 案）/尾斜杠/带 /v1、/v4、compatible-mode/v1 原样/Gemini `v1beta/openai` 中段不误补/`v1beta` 行尾不误补/空串
- [x] 2.2 kakou 案主钉：裸 base 连接测试全链——models GET `/v1/models`、对话探针 POST `/v1/chat/completions`
- [x] 2.3 SDK 构造钉子：裸 base → sentinel 客户端收到归一 base 且 `_base_url` 同步；anthropic base 不归一；版本段 base 原样
- [x] 2.4 更新既有断言：`test_openai_format_urls` fallback 改归一地址＋补 Gemini models 行（`…/v1beta/openai/models`）；`test_openai_chat_probe_405_fails_with_actual_url` 点名地址改 `/v1/chat/completions`；网页体文案钉 `/v1` 指引
- [x] 2.5 回归：`pytest tests/test_api_format.py tests/test_llm_probe_logging.py` 全绿＋ruff 触文件零新增

## 3. 门禁与收尾

- [x] 3.1 `openspec validate --change c-relay-base-normalize` 通过
- [x] 3.2 Design Impact 判定：单端（C端后端）不触共享段，无 UI 结构变更——无原型先行、无 design:check/design-cross 义务（回归门禁＝pytest＋ruff＋coverage，见 2.5）
- [x] 3.3 按路径提交（backend 两文件＋tests＋openspec change），推分支开 PR

## 4. 评审整改（2026-10-09 review-agent 三发现）

- [x] 4.1 网页体「补 /v1」出口按格式分流：`_v1_hint`（openai 兼容格式专属，anthropic/ollama 出空串），`_non_api_response`／`_probe_verdict` 传参贯通；spec delta 场景同步拆分
- [x] 4.2 design.md 风险段如实化：裸根端点改动前经 404 降级链端到端可用，归一化后「锁死」为显式接受的取舍（escape 出口待真实反馈另行立项）；proposal 过程留痕补评审轮记录
- [x] 4.3 前端登记表三处理由句更新（vendorDefaults.ts／ProviderIcon.tsx／apiVendorDefaults.test.ts 用例名——「SDK 不自补版本段」表述随归一化过时）
- [x] 4.4 回归：pytest 触文件＋ruff＋vitest apiVendorDefaults 全绿
