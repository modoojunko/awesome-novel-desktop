## 1. 双端影响判定

- [x] 1.1 双端影响判定：纯 C端 后端（记账/埋点/AI 客户端），不触前端与共享段——Design Impact「不适用」，无需原型先行
- [x] 1.2 盘点 record_usage / log_event_async / log_event 全部调用点，确认无「依赖记账 rollback 回退主写入」的隐藏用法——清单贴进 change 目录

## 2. 记账/埋点 SAVEPOINT 化

- [x] 2.1 `api_configs/usage.py`：add+flush 置于 `begin_nested()`；失败 warning 日志（`event=usage.write_failed`）后返回，外层 commit 保留——diff 贴进 change 目录
- [x] 2.2 `novels/events.py`：`log_event_async`/`log_event` 同批 savepoint 化（保留既有 warning）——diff 贴进 change 目录
- [x] 2.3 单测：FK 失败时同会话业务写入存活、调用方无异常、warning 在场——`pytest tests -k usage` 绿

## 3. chat_stream 正确性

- [x] 3.1 OpenAI 分支：choices 判空跳过；用量在循环内捕获（空流不 NameError）；done 拆 completion/prompt——diff 贴进 change 目录
- [x] 3.2 anthropic 分支：message_start 抓 input_tokens、message_stop 用 output_tokens——diff 贴进 change 目录
- [x] 3.3 `StreamEvent` 增加 `tokens_in`；`write/router.py`、`write/auxiliary.py` 记账补 `tokens_in=event.tokens_in`——diff 贴进 change 目录
- [x] 3.4 单测：usage-only 末块不炸且带拆分用量；空流 tokens=0；anthropic 双向拆分——`pytest tests -k stream` 绿

## 4. 回归

- [x] 4.1 `pytest client/backend/tests`（全量）输出结论贴进 change 目录
- [x] 4.2 `ruff check client/backend` 输出结论贴进 change 目录
- [x] 4.3 本 change 无前端改动，design:lint / design:check / tsc 不适用（判定依据见 1.1）
