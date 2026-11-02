# c-chars-draft-all — 设计

## D1 一个能力，两种形态（有卡/无卡）

- 有选中卡：`character_id` 必带；服务端以卡上此刻空值为唯一基准，只输出空格；采纳 = 既有单格 PATCH。
- 无选中卡（列表非空）：不带 `character_id`，body 带 `role`（配角/反派，默认配角）；采纳 = 既有 create(role)＋单格 PATCH。**不先建空卡**，关闭弹窗不留孤儿卡。
- 判定放在服务端：带卡即补空格；不带卡必须 role ∈ {配角, 反派}，否则 400。

## D2 输入只读已确认设定

`settings/settings-status.yaml` 严格 `is True` 的 `genre/synopsis/world/story-arc` 才进 `{confirmed}` 块；复用：

- `genres.service.resolve_genre_context` + `build_genre_section`
- `story.synopsis`
- `settings.characters_ai._world_summary`
- `settings.characters_ai._story_arc_text`

四项全未确认 → 400（前端行已置灰＋hint，400 是兜底）。现有角色名册总带（`list_characters`＋`prompt.context.cast_profile_block`，带卡模式排除本卡）；本卡已写内容走 `{filled_lines}`（名字/别名/人设/档案/认知），保证模型知道作者已写的字。

## D3 提示词模板

新模板 `settings_characters_from_settings`（prompts 仓）：

- system：立卡师＋只读已确认设定＋输出 JSON 契约（name/aliases/persona/fills/skipped）。
- user：本书＋本次任务（补齐/新建）＋卡类型＋已确认设定块＋现有角色＋本卡已写＋空格键位＋六层框架/每格口径/禁令/新拟名禁令。
- 占位符 `<<...>>`，服务端用顺序 replace，避免素材花括号炸 `str.format`。
- 路人：`{cog_briefs}` 明确「不写认知」，服务端再按角色过滤 cells。

## D4 前端状态机

- `cardAction`：`bootstrap` / `draftAll` / `check`；各自独立缓存槽与版本号。
- `draftAll` 两段：preview（只渲染）→ generate（真跑）；「换一个」按当前编辑稿重跑。
- 无卡时提示词编辑段给角色 chips（配角/反派）；切角色 = 重新 preview（不调 AI），提示词与 sources 同步更新。
- 迟到守卫：有卡用 `selectedIdRef`；无卡用递增 token（换卡/清 AI 递增）。
- 采纳：有卡逐格以服务端 rev 记账，单格 409 重同步后跳过续走；无卡 create→选中→逐格 PATCH。

## D5 退役与兼容

- 三补充行／一键立卡从 UI 移除；旧端点与模板保留（不动主角 bootstrap，避免字节级回归）。
- 规则：空书不出现「起草角色」（先立主角）；主角待立不出现（走「从简介立主角」）；卡满不出现（无空格可补）。
