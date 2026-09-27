# 提示词分层协议（每模板各自 system/user）

## Why

用户 2026-09-27 定：**每个提示词模板都要区分 system / user；逐模板独立、不做跨模板共享层**（每个页面的 AI 功能独立演进）。此前 system 只有一句"你是…只输出 JSON"，角色/优先级/禁止项/输出契约全塞在 user 一大坨里：恒定段被几千字素材稀释，也吃不到供应商的 prompt 缓存。

## What Changes

- **协议**：`prompts/__init__.py` 增 `<<system>>` / `<<user>>` 标记与 `load_layers()`（未分层文件返回 `("", 全文)` 保持兼容）。
- **首批迁移**：主线页四能力（arc_draft/calibrate/check/tone）各自分层：system＝角色＋优先级裁定＋禁止项＋任务与输出契约（恒定）；user＝设定素材＋作者输入。共享片段 `arc_hard_rules.prompt` 退役（各自内联，符合"不拉通"）。端点 `run_arc_ai` 改分层调用。
- **闸门**：`tests/test_prompt_layering.py` 把"全部模板都要分层"变成可跟踪不变量（名单外必须已分层、名单内必须尚未分层；当前名单＝其余 57 个模板，按族分组，迁完即删）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `storyline-settings`: MODIFIED「右栏 AI 三行」——素材顺序条款里「任务与输出契约压尾」改为「任务与输出契约 SHALL 住 system 段（恒定）；user 段只放素材与本次输入，素材顺序固定」。

## Design Impact

无用户可见界面改动（后端提示词装配方式）。受影响端＝仅 C端 后端。

## Impact

- **代码**：`prompts/__init__.py`、`prompts/arc_*.prompt`（4）、`settings/ai_router.py`、`tests/test_story_arc.py`、`tests/test_prompt_layering.py`（新）；`prompts/arc_hard_rules.prompt` 删除。
- **计费**：token 总量不变（system/user 只是分送），恒定前缀可按供应商能力吃到缓存。
- **真机**：隔离栈起草主线 579 字、零旧派系词、零告警。
