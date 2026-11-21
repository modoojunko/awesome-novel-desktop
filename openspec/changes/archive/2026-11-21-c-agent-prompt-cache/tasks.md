## 1. 提示词拆分

- [x] 1.1 `assistant/context.py`：新增 `build_book_brief_parts`（stable=书名/题材，dynamic=进度三态）；`build_book_brief` 改为两段拼接（既有调用/测试零改）——验证：新测试断言进度变化不改 stable、dynamic 含进度
- [x] 1.2 `assistant/router.py`：system 用 stable brief；dynamic brief＋memory_section 拼到当前 user 消息尾部的 note（`\n\n` 分隔），memory 不再进 system——验证：单测/集成断言 system 不含进度/记忆、note 含两段

## 2. 缓存命中留痕

- [x] 2.1 `ai_client.py`：openai 流式 usage 读 `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`（含 model_extra 兜底）；`_log_call` 成功行可选追加 `cache_hit=`/`cache_miss=`——验证：`test_ai_client_logging` 新用例（有/无字段两态）

## 3. 回归

- [x] 3.1 后端定向：`test_assistant_router_helpers` / `test_assistant_prompts` / `test_assistant_memory` / `test_ai_client_logging` / `test_assistant_chat_stream_http`；全量 `pytest tests/ -q --timeout=60 --ignore=tests/test_kb_baseline_fullchain.py`；`ruff check`——实测定向 56/56；全量 3373 passed / 328 skipped / 0 failed（530s，排除 KB fullchain 子进程挂起）；ruff 通过
- [x] 3.2 可选真机：隔离栈连续两轮对话，llm.log 看到 cache_hit/cache_miss；——实测 DeepSeek 两轮：首调 cache_hit=128/miss=7963，第二步 8064/655，后续 7808/1135、8832/166、8960/331；字段已进 ai_call 行，前缀缓存生效

## 4. 评审与合入

- [x] 4.1 合前 `review-agent` 审 diff，findings 修完再合——审查 No findings；残余风险：note 不持久化使缓存命中点在上一条 user 原文处截断（既有页面新鲜度取舍，design 已登记）
- [x] 4.2 建 PR（根因/改法/门禁），CI 双绿 squash 合 main，清 worktree/分支。证据：PR #1111 squash=`ddc97a32`，CI `test` 绿；真实两轮 cache_hit 128→8064；worktree/分支已清
