## ADDED Requirements

### Requirement: 工具档位归属（三档会员）

- 工具注册表 SHALL 按三档会员声明最低档，启动校验 SHALL 继续保证：写类工具必须声明 `requires_feature`（`assistant-execute`，PRO 起）；读类/产卡类 SHALL NOT 声明 `requires_feature`。
- **标准（免费）可用**：`read_chapter`、`read_outline`、`read_settings`、`read_story_state`、`read_progress`、`read_chapter_versions`、`read_page_fields`、`read_genre_catalog`、`read_write_prompt`、`switch_tab`、`navigate`、`update_plan`、`profile_read`/`profile_update`、`recall_book_memory`/`remember_book_memory`/`forget_book_memory`、`remember_decision`/`recall_decisions`、本地库 `kb_search`/`kb_read`。
- **PRO 起**：`ai-plan` 系产卡（卷规划/拆章/章纲/剧情/人物/命名/体检/设定域/故事弧/简介/题材）、`draft_prose_plan`（`ai-generate`）、`kb_search_craft`（`kb-official`，官方写作库）、写类工具（`assistant-execute`：改设定/建卷建章/改章纲/确认归档/知识库收录）、`chapter-review`/`style-suggest` 系。
- **MAX 起**：`read_prose_checks`（`human-taste`：人味检测＋逐行修改指引）、`diverge_character_group`/`diverge_plot_branches`（`assistant-diverge`）、`simulate_plot`（`ai-plot`）、`style-quant` 系；`allow_book` 自动执行仅 MAX 可用。
- 本地库与官方库 SHALL 分层：`kb_search`/`kb_read` 只查本书/本地层；`kb_search_craft` 只查官方层并挂 `kb-official`；`kb_create_entry`/`kb_update_entry` 写本地层但属写类工具，挂 `assistant-execute`。
- 档位不足时工具调用 SHALL 回对话内 gate 事件（说明开通后能做什么），SHALL NOT 403/异常打断。

#### Scenario: 标准（免费）只读工具

- **WHEN** 标准（免费）用户让助手「翻一下第三章讲了什么」
- **THEN** 助手调用 `read_chapter` 回答；不调用产卡/写类工具

#### Scenario: 标准（免费）要拆书/官方库

- **WHEN** 标准（免费）用户让助手「查官方库里开头三章怎么写」
- **THEN** `kb_search_craft` 因 `kb-official` 未授权回 PRO gate；本地库 `kb_search` 仍可用

#### Scenario: PRO 写类工具声明

- **WHEN** 启动校验扫描工具注册表
- **THEN** 全部写类工具均声明 `requires_feature=assistant-execute`；缺失即 fail loud

#### Scenario: MAX 人味工具

- **WHEN** PRO 用户让助手「查这章的人味问题」
- **THEN** `read_prose_checks` 因 `human-taste` 未授权回 MAX gate；MAX 用户可调用并拿到逐行改法
