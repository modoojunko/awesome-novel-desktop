# Tasks

- [x] 1.1 压缩全链：`prompts/compress_text.prompt`＋`auxiliary.compress_text`＋`POST /write/compress`（门控/失败账/成功账）——验证：`tests/test_write_transform_modes.py` 3 例（200 提示词与记账/400/超时 502 失败账）
- [x] 1.2 前端压缩：`compressText`＋ContrastPreviewModal 三态＋ProsePane 模式扩展＋右栏正文页签动作接 `onAiSelection("compress")`（选中门槛）——验证：`AiAssistPanel.test.tsx`「压缩真按钮」例＋tsc
- [x] 2.1 收尾按类触发：`start_reconcile_job(kinds)`＋`POST /reconcile/run`（白名单 400/缺省全量/门控/单飞）——验证：`test_reconcile.py::TestRunNow` 4 例（按类/全量/400/免费 403）
- [x] 2.2 右栏三入口接线（set_changes/relations/hooks，归档后可点，toast 指路）——验证：`AiAssistPanel.test.tsx` 三入口例＋e2e reconcile「登记新伏笔→run 端点→toast」断言
- [x] 3.1 回归：后端 pytest 全量；vitest 354；e2e reconcile 全链 2 例——验证：本轮执行
