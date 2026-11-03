# c-chars-draft-all — 角色右栏合并：三补充＋一键立卡 →「起草角色」

## Why

角色页右栏现有「人设补充 / 基础信息补充 / 认知补充」三行，本质都是「补这张卡的空格」，却拆成三次 AI 调用；「一键立卡」又在配角/反派上做同一件事。入口重叠、成本翻倍，作者还要先手建空卡才看得到一键立卡。boss 拍板（2026-11-02）：合并为一个「起草角色」。

同时明确输入口径：起草角色**只读已确认的设定**（题材/简介/世界/主线）＋现有角色名册＋本卡，不只看简介；未确认项不入参。

## What Changes

- 右栏只留：`从简介立主角`（空书/主角待立）/ `起草角色` / `一致性体检`；人设补充、基础信息补充、认知补充、一键立卡从 UI 退役。
- **起草角色**一次覆盖名称/别名/人设/档案/认知：
  - 有选中卡且仍有空格 → 只补空格，不建卡；
  - 无选中卡（列表非空）→ 新建一张卡，角色限配角/反派（默认配角，提示词编辑段可切），采纳才建卡；
  - 路人卡只补基础档案；
  - 四项已确认设定全无 → 行置灰「先确认设定」，不发起请求。
- 新提示词模板 `settings_characters_from_settings`：只使用【已确认的设定】与【已有角色】，未列出不编造；不重名/不撞定位；配角/反派写与主角这条线的关系；守新拟名禁令。
- 新端点 `POST /api/novels/{id}/settings/ai/characters/draft-all`：preview 只渲染提示词，生成走既有 AI 客户端，采纳复用既有 create＋单格 PATCH。
- 旧 `settings_characters_card` / 三补充端点保留但不再被 UI 调用（批次清理另议）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `character-settings`：
  - REMOVE「AI 四能力契约」「AI 立卡（配角/反派一键拟稿）」；
  - ADD「AI 能力契约（起草角色＋体检）」「起草角色（已确认设定＋名册＋本卡）」；
  - MODIFY「新拟名禁令」的适用口径（从简介立主角 / 起草角色）。

## Impact

- 前端：`charactersApi.ts`、`CharacterManager.tsx`、`AiWriterAssistant.tsx`、`SettingsView.tsx`、对应单测。
- 后端：`settings/characters_ai.py`（新端点）＋`tests/test_characters_ai.py`。
- 提示词仓：新模板＋CURATED＋禁字测试＋一次提示词包发布（additive，不 bump min_client）。
- 规格：本 change 的 delta；实现 PR 内 sync＋归档。
- 不改：主角「从简介立主角」链路、章纲抽卡、文风/伏笔、关系行、多候选 UI。
