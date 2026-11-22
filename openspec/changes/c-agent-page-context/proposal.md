## Why

作家在设定页说「这个/这格/这里」时，助手只拿到页面名「初始设定」和未保存标记，不知道当前是哪个面板、页面上有哪些字段、现在填的是什么。于是它只能猜，甚至把「题材」理解成四格而不是 01 目录。要把「页面上的东西」变成可指代的上下文。

## What Changes

- 前端随消息带 `page_state.panel`（设定面板键：genre/intro/world/chars/arc/style/foreshadow/aiModel）与 `page_state.chapter_tab`（章内页签键）。
- 后端新增页面字段上下文：设定页按面板注入「本页字段＋当前值」（01 题材/02 主要看什么/03 绝对禁止/04 吃苦指数/05 本小说斗什么；简介；世界八格；主线；文风；角色/伏笔摘要）；章内页签只报页签名。
- 注入只进当轮提示词（L2 尾随），不落库、不渲染；读取失败 fail-soft 为空/只报面板名，不打断对话。
- 值一律裁短并限总预算，不把长正文/清单灌进上下文；禁用词等标签保持人话。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `assistant-chat-ui`: 新增「页面字段上下文」要求（当前面板/页签随行＋字段清单与当前值注入）。

## Impact

- 前端：`Aui2Dock` 组 `page_state`、`chatApi` 类型；测试请求体。
- 后端：新增 `assistant/page_context.py`；`router` 解析 page_state 并把上下文拼进 L2 note；测试。
- 无 DB/schema 迁移；页面上下文是增强面，失败不影响对话。
