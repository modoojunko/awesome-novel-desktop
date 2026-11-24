## Why

Agent 字段级写（`write_chapter_fields` / `write_settings_field`）的字段模型与页面脱节，作家会遇到三类「授权了却不对」：

1. **写反/静默丢**：世界页 `no_power` 是布尔开关、`history/factions/constraints/extra` 是条目数组，写核一律 `str(value)` 落库——`str(False)` 经 `bool()` 归一后变「开」；列表变成 Python repr 字符串，页面读回为空。授权卡说写了，页面什么都没有。
2. **同族互覆**：章纲一次写 `summary + characters` 时浅合并让后者覆盖 `outline` 族，summary 静默不落库；`required_changes + prohibitions` 同 `memo` 族同理，回执仍显示已写入。
3. **空头授权卡 + 旧标签**：写前 preview 只查字段名，不校验写链契约（阶段闭集、数组形状、数字、题材列表项形状/上限），批了才报错；章纲卡面仍用「概要/禁则/剧情条目」，与章纲页「章纲概要/禁止事项/剧情」对不上。

2026-11-24 真机截图实锤设定页「核心承诺」对不上（设定页题材部分已由 #1140 修复），同根问题在世界页与章纲写路仍在，且前两类是静默数据错误。

## What Changes

- **世界字段写保留原生类型**：`no_power` 落布尔；`history/factions/constraints/extra` 落条目数组；写前用 `WorldIn` 同源校验，不再 `str()` 字符串化。
- **章纲多字段按族合并**：一次写多个字段时按 `outline` / `memo` / `emotional_design` 族深合并，所有 provided 字段都进入 patch（siblings 不再互覆）。
- **授权卡 preview 与写链同源校验**：`write_settings_field`（genre 列表/数值）与 `write_chapter_fields`（阶段闭集、数组形状、目标字数为数字）复用写核校验；不可写的值不弹卡，回喂模型改对再来。
- **卡面字段名对齐页面**：章纲 `summary→章纲概要`、`prohibitions→禁止事项`、`plot_items→剧情`；世界开关/条目按页面口径显示（开/关、条目行），不显示 `True`/Python repr。
- **02 标签退出 agent 字段写**：`core_promise` 只是给作家省字的短标签，移出 agent 写白名单；agent 只能写 02 主句 `promise_note`，标签走「出爽点」采纳卡。
- **页面字段说明书（read_page_schema）**：给 agent 一个零参数工具，按当前页面返回「页面说法/别名 → 字段键｜类型/上限｜写入口」；agent 先精确/语义匹配作家说的字段，再按写入口请求授权写入。无字段级写入口的页面如实说明，不编字段。
- **工具参数说明同步**：各字段的新值类型与页面实际形态一致（含 promise_note 主句/core_promise 标签的既有口径）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `assistant-tools`: 字段级写工具 SHALL 保留字段原生类型、按字段族合并全部 provided 字段、卡面/描述使用设定页与章纲页的可见字段名；SHALL NOT 用字符串化或浅合并导致静默丢失。新增 `read_page_schema` 页面字段说明书工具（页面说法/别名 → 字段键｜类型/上限｜写入口），覆盖设定/章纲/卷纲字段写页面。
- `writing-assistant`: 授权卡 preview SHALL 与真实写链同源预校验（不可写的请求不弹卡），字段名与页面一致；世界字段按页面口径呈现，不显示内部/英文表示。
- `world-settings`: agent 字段级写的世界字段 SHALL 经 `WorldIn` 契约落库（`no_power` 布尔、条目数组），SHALL NOT 以字符串形态持久化。
- `intro-genre-settings`: agent 字段级写题材 02-05 SHALL 经 `NovelGenreIn` 契约与页面字段映射；02 主句写 `promise_note`，标签 `core_promise` SHALL NOT 由 agent 字段写直接改（走「出爽点」采纳卡）；preview SHALL 校验列表形状/条目上限/数值范围。

## Impact

- 后端：`client/backend/assistant/caps/settings.py`（world/genre 写核与 preview 校验共用）、`assistant/caps/chapter.py`（族合并与校验复用）、`assistant/tools.py`（preview/工具说明）、新增 `assistant/page_schema.py`（页面字段说明书）、`assistant/tools_settings.py`＋`assistant/scopes.py`（read_page_schema 注册与页签可见性）、复用 `settings/world_model.WorldIn` 与 `genres/novel_genre_service.NovelGenreIn`（不改契约）。
- 前端：无布局改动；`CardBody` 设定标签已在 #1140 对齐，本次无新增 UI。
- 测试：assistant caps / preview / world / chapter 写核单测；无新增接口或依赖。

## Design Impact

- 受影响端：仅 C端。
- 受影响屏：工作台·章纲页签的授权卡；设定页·世界/题材面板的授权卡。
- 对象状态：无新增状态，沿用现有授权卡与 AI 卡形态；不改状态语言总表。
- 共享段：不触碰令牌、基础组件类或两端共享段。
- 原型：不需要（字段名/取值口径与写链正确性修复，卡面结构不变）。
- 设计工件：实现侧自查（文案按 design-language §13 口语化，卡面结构与组件不变）。
