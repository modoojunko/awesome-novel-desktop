# c-agent-page-field-truth——助手「页面字段真值」注入

> **2026-11-22 修订**：页面字段自动注入已由 `c-agent-page-context`（PR #1123）撤除——字段值改由只读工具 `read_page_fields` 按需查询；本 change 只保留面板名注入、brief 题材键修复、`read_settings(genre/intro)` 与 `promise_note` 白名单。归档时以更新后的 delta 为准，不要恢复 `build_genre_panel_note`。

## Why

作家在设定·题材面板问助手「当前页面有几个问题」，助手答「我这边看不到你页面上具体哪儿出问题了」——模型对作家当前看的页面有哪些字段、哪些填了哪些没填一无所知，无法帮助作家处理初始设定。实勘四个断点：

1. 书情 brief 题材行是死代码：`assistant/context.py` 读 `gctx.get("genre")`，而 `resolve_genre_context` 返回键是 `theme` ——「题材：X」永不注入；五格全空时 resolve 返回 None，连「未填」都不说。
2. `set:*` 线程无面板名真值：页签真值注入只认 `ch:` 前缀（`_THREAD_TAB_ZH` 仅章内七页签），设定面板名在前端编码进 thread 键后后端无人解析；`［当前页面：初始设定］` 不分面板——模型不知道作家在题材页还是角色页。
3. 题材五格与简介 synopsis 无任何读取通道：`read_settings` area 枚举 premise/world/cast/hooks 无 genre/intro；`build_genre_section` 只喂整章写作链不在助手对话链路。
4. 写白名单缺 `promise_note`：作家说「把我刚说的这段写进主要看什么」时助手写不进去（theme/sub_genre 已由 c-agent-genre-pick 的 catalog 卡成对写，不在此重复建路）。

## What Changes

- 修复书情 brief 题材行死代码：改读 `theme`/`sub_genre`，题材已填时真实注入「题材：大类（子类）」。
- `set:*` 页签真值扩展：注入「［当前页签：设定·<面板名>］」（genre/intro/world/chars/arc/style/foreshadow 七面板中文名；default 与未知键回退「设定」）。
- `set:genre` 面板字段值改由 `read_page_fields` 按需读（#1123）：提示词只留面板名，不再随 user 尾注入五格填空状态。
- `read_settings` 加 `genre`/`intro` 共享读分区：genre 分区给五格现值＋未填点名；intro 分区给简介现值或「还没有内容」。
- `write_settings_field` genre 白名单加 `promise_note`（标签「主要看什么」），走既有整卡合并校验路径。
- 零前端改动、零界面改动——全部落在后端提示词装配层与工具注册表。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `assistant-chat-ui`: 新增两个 requirement——「设定页签与字段读取边界」（面板名可注入、字段值只走 `read_page_fields` 工具）与「书情 brief 题材行」（brief 题材行真实反映题材目录现值）。
- `assistant-tools`: MODIFIED「页面操作工具族——导航与字段级写」（genre 写白名单四字段→五字段，加 promise_note）；新增「设定读面——五格与简介真值」requirement（read_settings 的 genre/intro 分区契约，及与题材目录工具的分工）。

## Impact

- 后端：`client/backend/assistant/context.py`（brief 修复）、`assistant/router.py`（set:* 面板名注入）、`assistant/tools.py`（read_settings 两分区）、`assistant/caps/settings.py`（写白名单加一行）、`genres/service.py`（五格真值渲染函数，供 read_settings/read_page_fields 共用）。
- 测试：`tests/test_assistant_router_helpers.py`、`tests/test_agent_page_ops.py`、`tests/test_genres_injection.py` 补五处锚点。
- 提示词 token 增量只剩面板名一行；字段值不再每轮占用上下文，按需由工具返回。

## Design Impact

本改动纯后端提示词装配层与工具注册表，无任何用户可见界面变化（dock/面板/卡片均不动，前端零改动）——免原型先行，无需登记 ADJUSTMENTS.md。模型话术属对话内容，不受 §13 按钮词表约束。
