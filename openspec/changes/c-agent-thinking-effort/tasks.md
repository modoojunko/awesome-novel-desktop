## 1. 实现

- [x] 1.1 `ai_client.py`：`_explicit_thinking_params` 非 disabled 分支补齐配置强度（GLM 嵌套/其余顶层；显式 effort 优先；不支持 base 不发）——验证：单测覆盖五态
- [x] 1.2 测试：显式 enabled 默认 low、GLM high 嵌套、显式 max 优先、disabled 无 effort、不支持 base 不发——验证：`test_ai_client_layering`/`test_ai_client_native_tools` 新用例

## 2. 回归

- [ ] 2.1 定向：`test_ai_client_layering` / `test_ai_client_native_tools` / `test_assistant_loop` / `test_assistant_loop_native` / `test_thinking_display` / `test_ai_client_logging`；全量 `pytest tests/ -q --timeout=60 --ignore=tests/test_kb_baseline_fullchain.py`；`ruff check`——记录实际结论
- [x] 2.2 可选真机：隔离栈助手开思考（DeepSeek）确认请求带 `reasoning_effort=low` 且正常流出 thinking——实测 DeepSeek 显式 enabled＋配置 low：thinking 222 字（此前默认 high 4003 字），无拒参、run_end 正常

## 3. 评审与合入

- [x] 3.1 合前 `review-agent` 审 diff，findings 修完再合——No findings；全量首跑唯一红是 volc_doubao 旧不变量测试（显式 enabled 原样透传），已按新 spec 更新为「按配置强度补齐＋显式 effort 优先」
- [ ] 3.2 建 PR（根因/改法/门禁），CI 双绿 squash 合 main，清 worktree/分支
