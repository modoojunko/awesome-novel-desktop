# c-char-ai-card-generic

## Why

内测用户吐槽：「主角可以使用 AI 帮助配置，配角就没有了。」实勘：设定 → 角色的右栏四行（人设/基础信息/认知补充、体检）对配角/反派其实可用，但「一键式 AI 帮配置」只有主角有——「从简介立主角」占满空态引导、待立徽章与右栏首行，配角新建后落在一张全空卡上，无等价入口也无引导，感知上就是「配角没有 AI」。

## What Changes

- 右栏新增「一键立卡」行：选中**配角/反派**卡且卡上还有空格（人设/档案八格/认知格任一为空）时，右栏首行出现一键拟稿入口，单次出稿覆盖名称、别名、人设、档案与认知空格建议——与「从简介立主角」同一弹窗出卡确认制（先出稿、采纳才写入、只补空格）。
- 后端 `POST /api/projects/{id}/settings/ai/characters/bootstrap` 泛化：带角色卡 id 时按卡的角色分派提示词——主角待立沿用现行主角模板（字节不动），配角/反派改用新增的角色通用立卡模板；`ai_feature("settings-ai-fields")` 门控、只补空格基准、skipped 语义、幂等/重开缓存全部沿用。
- 提示词仓 companion：新增 `settings_characters_card.prompt`（system/user 分层，{role} 占位区分配角/反派，剧情定位口径按角色调整）；主角模板零改动，故 e2e 桩短语与主角链零回归面。
- 路人不提供该行（与「路人不参与体检」同口径，路人卡只填基础档案）。
- 角色卡主区加一行指引：配角/反派卡名称与人设皆空时，显示一句指向右栏的提示文案（不可点，不破坏「卡片上不放 AI 按钮」的既定拍板）。
- 不改动：主角「从简介立主角」全链、右栏既有四行、免费档「看得见、点不动」门控、AI 四能力契约。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `character-settings`: 新增 Requirement「AI 立卡（配角/反派一键拟稿）」——右栏一键行出现条件、出稿与只补空格契约、采纳单格写入、路人排除、未配模型/简介未填出口；既有「首次进入引导与从简介立主角」「AI 四能力契约」等需求不动。

## Design Impact

- 受影响端：**仅 C端**（S端 无涉及，不触两端共享段，无需 design-cross）。
- 受影响屏/弹层：设定域「角色」页签——右栏 AI 卡（新增一行 ra-step，沿用既有行组件）、AI 出卡确认弹窗 AiCardModal（沿用既有 loading/预览/采纳态）、角色卡主区（新增一行 info 提示文案）。
- 对象状态：全部沿用状态语言总表既有条目（ra-step 的正常/禁用/运行三态、弹窗既有状态）；无新增组件形态、无新语气词，不触 design-system。
- 原型先行：**需要**——`docs/design-c/prototypes/character-settings.html` 补右栏行与卡区提示行，`ADJUSTMENTS.md` 登记偏差项；设计工件由实现侧自查产出（无新视觉形态，纯既有组件复用）。

## Impact

- 后端：`client/backend/settings/characters_ai.py`（bootstrap 端点内模板分派＋配角分支的简介未填文案与解析失败措辞）；无新端点、无 DDL。
- 前端：`CharacterManager.tsx`（runAi 新 key「cardDraft」＋采纳 patch-only 分支＋卡区提示行）、`AiWriterAssistant.tsx`（CharsAiRail 行门控）、`charactersApi.ts`（复用 bootstrapDraft，补类型）。
- 提示词仓（awesome-novel-prompts，companion 提交）：新模板＋manifest＋sync 重生成 README；须先于真机验收合入并走发布链，C端 dev 需确认加载到新模板。
- 测试：后端模板分派/只补空格/skipped；前端行门控（角色×空格两条件）与采纳 409 同步；e2e 角色页补 `data-aiact="cardDraft"` 钉子。
