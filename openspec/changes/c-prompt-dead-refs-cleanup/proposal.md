# Proposal: c-prompt-dead-refs-cleanup

## Why

提示词纳管实勘（2026-10-04，awesome-novel-prompts 仓库 CURATED 注释）发现两处死代码：

1. **`backfill_outlines.prompt` 死占位符**：模板 user 段写有「设定信息：`{settings}`」「已有章节：`{chapters}`」两节，但唯一消费方 `novels/ai_backfill.py:57-59` 的 `_call_ai` 只做 `user + "\n\n---\n" + context` 纯拼接、从不 `.format`——两个占位符以**字面量**随文发给模型。且 step2 只喂 step1 反推结果，「已有章节」永远没有数据可填。同批清理模板 ：3/:7 里「（和）已有章节」的 prose 指涉——只删占位符不删指涉，等于把「有空标签无数据」换成「指令里凭空指涉一份永不到达的素材」。
2. **`name_canon` 片段死注入**：`settings/ai_router.py:1068` 每次主线 AI 调用（draft/calibrate/check）都执行 `"name_rules": name_canon_text()`（含文件 IO），但 grep 全 `prompts/*.prompt` 已无任何 `{name_rules}` 占位符——规则在 2026-09-27 分层重构（#538/#542）时内联进 `arc_draft`/`arc_calibrate`/`arc_check` 的 system 段，且是**按各模板语境改写的三处变体**（非逐字副本：arc_draft 带生成侧禁令、arc_calibrate 措辞更软、arc_check 为裁判口径无生成侧禁令）。片段成了「改了不生效」的假单源，spec（storyline-settings 硬约束②）里「同一份口径措辞（单源片段…）」的机制描述也随之失真。

## What Changes

- `client/backend/prompts/backfill_outlines.prompt`：删除「设定信息：{settings}」「已有章节：{chapters}」两个死标签节，**并**改写 ：3/:7 两处「（和）已有章节」prose 指涉（如「依据给出的设定素材（简介/设定/角色），规划卷结构与章纲」）；输出格式说明（`# 卷`/`## 章` 锚）与 `---` 拼接语义保持（与另外三个 backfill 模板同形）。
- `client/backend/settings/ai_router.py`：`_arc_material()` 返回 dict 删除 `name_rules` 键及 `name_canon_text()` 调用；`from settings.name_registry import ...` 同步去掉不再使用的名字；:1066-1067 两条腿旧注释按现状改写。
- `client/backend/settings/name_registry.py`：`name_canon_text()` docstring 与模块头注释更新为现状（片段=参考存档；现行规则=arc_* 三模板 system 段的语境化改写变体；活注入腿=`{roster}` 名册）。函数保留（片段加载器，未来恢复动态注入须重新接线＋对拍）。
- `client/backend/prompts/name_canon.prompt`：头部 `## ` 注释改写为参考存档状态（见 design 口径，每行保持 `## ` 前缀）。
- `client/backend/tests/test_prompt_layering.py`：`MIGRATION_PENDING` 删除 `name_canon` 重复登记（ASSETS 已覆盖）；ASSETS 注释补「现为文档副本」。
- spec delta：`storyline-settings` 的「右栏 AI 三行」requirement MODIFIED——硬约束②去掉「同一份口径措辞（单源片段…）」失真机制描述，改为行为口径（名册＋规则同时给、规则住各模板 system 段与行角色相适、片段退役为参考存档）；15 个场景逐字保留。
- close-out：提示词纳管仓库（awesome-novel-prompts）`sync.py` 的 CURATED 同步更新，**合入 main 后**重跑 `python3 sync.py` 推送（时序见 tasks 5.x）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `storyline-settings`: 硬约束②的专名口径机制描述——删「单源片段」注入机制表述（该机制自 2026-09-27 分层重构起已不存在），改为「规则文本住各模板 system 段、与行角色相适」的行为口径＋片段退役注记。SHALL 行为本体（名册＋规则同时给出、只给规则不给名册无效）不变；15 个场景零改动。

## Design Impact

无 UI 改动——纯后端提示词文本与死代码清理，不触原型、不触两端共享段、不需要 design 门禁。

## 非目标

- `story_character`/`story_stage` 的 `.format()` KeyError（剧情推演空转）——**另立 change**：涉及模板转义＋formatability 闸门＋e2e/真机推演验证，体量与本改不同级。
- 不改 `_call_ai` 的拼接机制，不给 backfill 链新增 format 能力。
- 不动 arc_* 三模板 system 段里的内联规则文本——三处措辞分叉为**已知现状**（arc_check 无生成侧禁令系裁判角色使然，非缺陷）；对齐措辞属规则演进类改动（模型可见行为变更，须真机验证），另立 change。
- `novels/ai_backfill.py:16-29` 的 `_load_prompt`/`_PROMPTS` 死缓存（全仓无调用方）——评审顺带发现，留后续清理，本改不碰。
