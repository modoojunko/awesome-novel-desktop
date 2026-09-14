## Why

设定推进顺序是 01 简介 → … → 04 角色。作者走到「角色」时，简介里往往已经把主角写了（六段模板第一段就是「主角身份」），但角色页首次进入是一张白板：要先点「添加角色」（默认建的是**配角**空卡）、手动切成主角、再把简介里写过的主角名等信息重敲一遍，AI 四行才有的放矢（四行以卡名为输入，且不产出名字）。首次体验断层、重复劳动，与本仓「前面填过的信息后面不再要」的产品直觉相悖。

## What Changes

- **首次进入引导**：角色列表为空时，中栏不再只给一句「左侧添加或选择一个角色」，改为引导卡——简介已填时给「从简介立主角」（主）＋「手动建主角」（次）；简介未填时提示先补简介、手动建主角兜底。
- **新 AI 能力「从简介立主角」（bootstrap）**：输入书名＋题材＋简介（世界已填则带上），一次出稿返回名称/别名/一句话人设/基础档案与认知的空格建议；先出稿、采纳才写入；性别、年龄照旧永不代填。采纳复用既有单格写入（空态＝建主角卡＋单格补写；主角待立＝单格补写），不新增独立写路径。PRO 门控与「免费可见点不动」沿用现有 AI 行机制；未配模型给出「先去模型设定」的出口提示。
- **主角待立也放同一入口**：主角卡存在但名称为空时，右栏出现「从简介立主角」行，同一出稿能力只补空格。
- **首卡默认主角**：列表为空时点「添加角色」直接建主角卡；之后再添加仍默认配角。
- **readiness 收紧**：「角色管理已填」从「至少一张卡」收紧为「至少一张名字非空的卡」（顺手修正 readiness spec 中 characters 行与 v2 实现的口径漂移：readiness 只判内容非空，两档确认门禁留在 character-settings）。

## Design Impact

- 受影响端：**C端**（client/frontend 设定视图「角色」面板 ＋ client/backend 角色 AI 与 readiness）。S端 不涉及。
- 受影响屏/弹层：设定视图 · 角色面板中栏空态（新增引导卡）、角色卡头部（无结构改动）、右栏 AI 栏 CharsAiRail（条件新增一行）。无新弹层。
- 对象状态：复用现有状态语言（info/ok/warn/err；pill-warn「待立」既有），不新增语气词、不新增胶囊形态、不触碰两端共享段。
- 原型先行：不需要——全部复用设定页既有外壳与组件词汇（设计侧工件 = 本 proposal + design.md，实现侧自查）。
- 文案口径：按钮均为动词（「从简介立主角」「手动建主角」）；不出现门控/就绪度等内部术语。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `character-settings`: 新增「首次进入引导与从简介立主角」requirement（空态引导卡、bootstrap 出稿采纳契约、性别年龄不代填、PRO 门控、手动兜底、首卡默认主角）；「免费 / PRO 门控」requirement 的 AI 行范围扩至新行。
- `readiness`: 「Content-based checkers」中 characters 判定收紧为「至少一张名字非空的卡」，并修正该行与 character-settings-v2 实现的口径漂移（readiness 只判内容非空；两档确认门禁归 character-settings）。

## Impact

- 代码：`client/backend/prompts/settings_characters_bootstrap.prompt`（新）、`client/backend/settings/ai_router.py` 或 `settings/characters_ai.py`（新端点）、`client/backend/workflow/readiness.py`（checker 收紧）、`client/frontend/src/lib/charactersApi.ts`、`client/frontend/src/components/novel/settings/CharacterManager.tsx`、`client/frontend/src/components/novel/settings/AiWriterAssistant.tsx`（CharsAiRail）、`client/frontend/src/components/novel/workbench/SettingsView.tsx`（透传）。
- 测试：后端 pytest（bootstrap 出稿/门控/性别年龄/readiness）、前端 vitest（引导空态/采纳编排/首卡默认主角/rail 行条件）、e2e（角色面板首进引导一条）。
- 兼容：不迁移数据、不改既有端点契约；readiness 收紧只影响「只有空名卡」的书（本就不该算已填）。
