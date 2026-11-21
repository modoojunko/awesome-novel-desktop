## 1. 后端实现

- [x] 1.1 `ai_client.py`：`chat_stream` openai 组包保留 `tool_calls`/`tool_call_id`；新增 `requires_reasoning_echo()`（openai＋vendor=deepseek）；`reasoning_content` 仅在能力位为真时透传——验证：`test_ai_client_native_tools` 新用例捕获实发 messages
- [x] 1.2 `assistant/context.py::build_outbound_window(native=True)`：assistant 行透传 `reasoning_content`（存在才带），tool 行字段不变——验证：native 循环测试第二次请求含该字段
- [x] 1.3 `assistant/loop.py` native 分支：逐步累积 thinking，按 `requires_reasoning_echo` 挂到 assistant 转写行（工具调用行＋最终行）；文本分支零改动——验证：native 两步测试断言 assistant 行与最终行

## 2. 测试与门禁

- [x] 2.1 `tests/test_ai_client_native_tools.py`：deepseek 带 reasoning_content＋tool 字段保真；glm 不附加 reasoning_content 但 tool 字段保留——验证：新用例通过
- [x] 2.2 `tests/test_assistant_loop_native.py`：echo client 两步循环第二次 messages 含 assistant(tool_calls, reasoning_content)＋tool(tool_call_id)；最终行带 reasoning_content；非 echo client 不带——验证：新用例通过
- [x] 2.3 回归：后端定向（上述两文件＋`test_assistant_loop.py`）＋全量 `pytest tests/ -q --timeout=60 --ignore=tests/test_kb_baseline_fullchain.py`；`ruff check`——实测定向 43/43；全量 3369 passed / 328 skipped / 0 failed（479s，排除 KB fullchain 子进程挂起）；ruff 通过
- [x] 2.4 可选真机：隔离栈 `ASSISTANT_HARNESS=native` 用支持 native FC 的配置（GLM/OpenAI，或 DeepSeek 单轮两步）验证同 run 工具历史不再 400；DeepSeek 跨轮 native 不在本 change（需转写持久化）——实测 GLM 端点 429「每周/每月使用上限，2026-11-23 17:36:01 重置」，真机未完成；请求形状由 fake SDK 捕获测试覆盖（tool_calls/tool_call_id/reasoning_content 实发断言）

## 3. 评审与合入

- [x] 3.1 合前 `review-agent` 审 diff，findings 修完再合——审查 No findings；全量回归揪出的 `__new__` 测试实例缺 `_vendor` 已修（getattr 兜底）；残余风险：GLM 真机 429 未跑、DeepSeek 跨轮 native/prime 行不在保证范围（design 已登记）
- [ ] 3.2 建 PR（根因/修法/门禁），CI 双绿 squash 合 main，清 worktree/分支
