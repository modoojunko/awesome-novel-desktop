## 1. 实现

- [x] 1.1 `assistant/context.py`：`latest_reminder_text()`（Asia/Shanghai/中文星期/空 location/App/中文）＋`build_outbound_window(reminder=)` 在当前最后 user 前插入，text/native 白名单放行——验证：固定日期与插入位置单测
- [x] 1.2 `ai_client.py::supports_latest_reminder`（openai+deepseek）；`loop.py` LoopConfig 字段＋两分支透传；`router.py` 门控生成并传入——验证：能力矩阵/loop 透传/HTTP 级断言

## 2. 回归

- [x] 2.1 定向：context/loop/loop_native/ai_client_native_tools/chat_stream_http/prompts；全量 `pytest tests/ -q --timeout=60 --ignore=tests/test_kb_baseline_fullchain.py`；`ruff check`——记录结论。证据：定向 71 过；全量 3387 passed/1 failed（唯一红为存量竞态，单跑 PASS）；ruff 过
- [x] 2.2 可选真机：隔离栈 DeepSeek 一轮确认 SSE 正常、llm.log 无拒参——实测 DeepSeek 问「今天几号/星期几」正确答 2026-11-21 星期六；run_end 无 error；role 被接受；非 DeepSeek 配置不外发该 role。首版仅提醒无纪律行时模型仍按「没有日历」拒答；补静态系统纪律行「以 latest_reminder 为准」后正确答出（判例：隐藏 role 需配可信任说明）

## 3. 评审与合入

- [x] 3.1 合前 `review-agent` 审 diff，findings 修完再合——No findings；判例：latest_reminder 只给 role 不够，需静态系统纪律行告诉模型它是可信当前日期来源
- [x] 3.2 建 PR（根因/改法/门禁），CI 双绿 squash 合 main，清 worktree/分支。证据：PR #1113 squash=`3faca4ff`，CI `test` 8m55s 绿；真机日期答对；worktree/分支已清
