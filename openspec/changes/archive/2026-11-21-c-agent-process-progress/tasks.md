## 1. 前端过程缓冲与状态行

- [x] 1.1 Aui2Dock：procBuf 扩 `{items, live, startedAt, endedAt, failed}`；提交即出状态卡；onDone/onError 停表；`toProcCards`/回放插 `trace_status`——验证：单测 live/finish/replay 文案
- [x] 1.2 `TraceStatusCard`＋CSS＋注册表：运行中/完成/已停止、当前动作、第 N 步、已等/用时（fake timers）——验证：单测计时与步骤计数
- [x] 1.3 工具卡参数：`AgentEvent.args`、process item args 预览、body「参数」行——验证：单测展开可见参数

## 2. 后端参数预览

- [x] 2.1 `router._consume` step_end 写 process item `args`（JSON 截断 ≤600）——验证：HTTP 级 process payload 断言

## 3. 回归

- [x] 3.1 前端 Aui2Dock 测试＋`npm run coverage`/`tsc --noEmit`/`npm run build`；后端定向＋全量 `pytest tests/ -q --timeout=60 --ignore=tests/test_kb_baseline_fullchain.py`；`ruff`；design:lint 本改动文件零违规——记录结论
- [ ] 3.2 可选真机：隔离栈跑一轮多步，确认状态行实时走秒/步数递增、收口停表、工具参数可展开

## 4. 评审与合入

- [x] 4.1 合前 `review-agent` 审 diff，findings 修完再合。证据：review 3 findings（回放中断态/状态行溢出/空参数一致性）已修，无剩余
- [x] 4.2 建 PR，CI 双绿 squash 合 main，清 worktree/分支。证据：PR #1114 squash=`607d13c8`，CI check 3m32s＋test 9m37s 双绿；worktree/分支已清
