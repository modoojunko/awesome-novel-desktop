## Why

DeepSeek 官方「用户元信息标记」：API 调用方可用一条 `{"role":"latest_reminder","content":"<date>,<weekday>,<location>,<platform>,<language>"}` 消息告诉模型当前日期/星期/语言，格式如 `2026-11-09,星期一,新加坡,Web,中文`；该消息**紧挨在所属 user 消息之前**，可随每轮携带。我们的助手只有历史里的跨日标记，长对话/跨天后模型对「今天」没有真值；把它放在当前 user 消息前，还能与历史一起作为前缀缓存的一部分（DeepSeek 文档：不回传旧提醒会降低缓存命中）。

## What Changes

- 新增 `latest_reminder_text()`：按 Asia/Shanghai 本地日期生成 `<date>,星期X,,App,中文`（location 留空、platform=App、language=中文）。
- `build_outbound_window` 增 `reminder` 参数：有值时在当前**最后一条 user 消息之前**插入 `{"role":"latest_reminder","content":...}`（文本/native 两分支都保留该 role）；无值零变化。提醒不进 compact、不落库、不进历史。
- `LoopConfig.latest_reminder` 透传到两分支的窗口；router 仅当 client `supports_latest_reminder()`（openai 协议＋vendor=deepseek）时生成并传入。
- 测试：时间格式/星期固定值、窗口插入位置（最后一条 user 前、不进旧轮）、vendor 能力矩阵、loop 透传。
- 不做：不持久化提醒（页面/日期会过期）；其它供应商不发（未知 role 风险）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `writing-assistant`: 新增「DeepSeek 当前日期标记」要求（每轮当前 user 消息前 latest_reminder；不落库；其它 vendor 不发）。

## Design Impact

- **受影响端**：仅 C端后端；无前端/UI、无 S端、无共享设计段、无原型。
- **对象状态**：无新增用户可见状态；模型可见的当前日期真值。
- **设计工件**：无（供应商协议对齐）。

## Impact

- `client/backend/assistant/context.py`（提醒文本＋窗口插入）
- `client/backend/assistant/loop.py`（LoopConfig 字段与两分支透传）
- `client/backend/assistant/router.py`（能力门控与生成）
- `client/backend/ai_client.py`（`supports_latest_reminder` 能力位）
- 测试：`test_assistant_context`/`test_assistant_loop*`/`test_ai_client_*`/`test_assistant_chat_stream_http`
- 无数据/API/schema 迁移。
