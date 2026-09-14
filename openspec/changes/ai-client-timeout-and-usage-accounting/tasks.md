# ai-client-timeout-and-usage-accounting — Tasks

## 1. 客户端层：超时与超时异常类型化（ai_client.py）

- [x] 1.1 `AIClient.__init__`/`_init_client` 注入默认 `timeout`（非流式 `Timeout(connect=10, read=90, write=30, pool=10)`；流式 read=120 同构造）与 `max_retries=1`，Anthropic/OpenAI 两分支都生效；验证：单测断言构造的 SDK 客户端 kwargs 携带 timeout/max_retries
- [x] 1.2 定义 `AITimeoutError`；`chat`/`chat_stream` 捕获 SDK 超时/连接类异常转抛之，其余异常原样；验证：单测 mock SDK 抛 `APITimeoutError`/`ReadTimeout` 断言转抛类型
- [x] 1.3 `record_usage` 加 `force: bool = False`（`usage.py`），零 token + force 也落库；验证：单测覆盖 force 落库与非 force 早退两分支

## 2. 判定包装：`_judge_chat` finally 回填（settings/ai_router.py）

- [x] 2.1 `_judge_chat` 三处 `_flush_usage` 收敛为 `try/finally` 单点，任何退出路径回填累计 token；验证：单测 mock `client.chat` 抛超时断言 caller usage 含首次尝试 token；既有「重试成功合计记账」用例保持绿
- [x] 2.2 六处判定端点（418/601/715/818/941/1070 行段）异常路径补 `record_usage(operation+"_fail", force=True)`，`except AITimeoutError` 分支文案改「AI 服务响应超时，请稍后重试」；验证：端点测试 mock 抛超时断言 502 文案 + token_log 有 `_fail` 行

## 3. 写作与章节侧：失败记账补齐（write/ chapters/ prompt/ novels/）

- [x] 3.1 `write/router.py`：流式写章 yield 循环包 try/except，中断落 `write_chapter_fail`（tokens_out 取已累计事件 tokens，缺失记零）后重抛；润色/扩写等非流式端点异常路径补 `_fail` 记账；验证：mock 中途抛错断言 `_fail` 行与 SSE 错误事件
- [x] 3.2 `write/auxiliary.py`、`chapters/ai_draft.py`、`prompt/router.py`、`novels/router.py` 各 AI 端点异常路径补 `_fail` 记账（超时文案同 D2 口径）；验证：各文件对应端点测试补失败记账断言
- [x] 3.3 `settings/characters_ai.py` 现役失败/空结果记账对齐 `_fail` 后缀（成功路径不动）；验证：`test_characters_ai.py` 既有失败用例改断言后缀后保持绿

## 4. 全链验证与收尾

- [x] 4.1 后端全量 pytest 绿（主仓根 venv 跑，实数记录）；ruff/design-lint 门禁绿
- [x] 4.2 手工冒烟：本地栈断网/错 Key 模拟超时，确认 502 文案、token_log `_fail` 行、用量页汇总不异常
- [x] 4.3 specs/character-settings 遗留 4.5 注销核对（该 change tasks 已归档，无需改，仅确认口径闭合）；e2e 全量（若角色用例受 502 文案影响则同步修 mock）
