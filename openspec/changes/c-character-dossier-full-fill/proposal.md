# 提案：角色档案八格全进 AI 候选（性别/年龄/种族照补空格）

## Why

用户实测反馈：角色右栏 AI「基础信息补充」缺年龄、性别、种族字段。排查实况：

- 性别/年龄是 character-settings-v2 时拍板的 `author_only`（「这两格永远由作者本人填」）——spec 冻结条款＋模板禁令＋前端文案三处钉死；
- 种族本就在候选里，但模板口径「不确定就跳过这格」过保守，真机出稿常整格跳过；
- UI 上性别·年龄·种族合一行，出稿后这行恒空，作者观感就是「这三格 AI 补不了」。

作者主权格的口径本次翻转：性别/年龄/种族与档案其余格同口径——**只补空格、采纳才写入**，主权由「永不代填」改为「写过的字一个不动＋出稿确认制」（c-settings-ai-confirm-modal 已把所有设定域出稿收进弹窗确认）。

## What Changes

- `character_model.py` 单源：`DOSSIER_FIELDS` 的 `author_only` 标志退役，`DOSSIER_FILL_KEYS`＝全 8 键；`apply_character_fills` 删 `author_only` 拒写分支（skipped reason 枚举同步收窄）。
- 两份模板（`settings_characters_dossier` / `settings_characters_bootstrap`）：删「禁止输出性别、年龄」禁令；补性别/年龄每格口径；种族口径放宽为「优先取世界已有；世界没写就按题材惯例给一个」（不再允许「不确定就跳过」）；输出 JSON 示例补 `gender`/`age`。
- 前端镜像 `characterModel.ts` 同批（parity 正则只锁 `k/label`，无格式变化）；`AiWriterAssistant.tsx` 与 `CharacterManager.tsx` 弹窗脚注的「性别、年龄不代填」文案撤除；档案缺口计数上限 6→8。
- 受益能力（全部既有端点，零新路由）：
  - 基础信息补充（`draft?target=dossier`）：targets 含 gender/age/race 空格；
  - 从简介立主角（`bootstrap`）：`_BOOTSTRAP_FILL_KEYS` 由 `DOSSIER_FILL_KEYS` 单源派生，自然跟进。
- **不动**：只补空格基准（服务端此刻空值）、采纳才写入、弹窗确认制、人设唯一覆盖型、免费档门控——全部照旧。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `character-settings`：AI 四能力契约——删「性别与年龄 SHALL NOT 由 AI 代填」条款与「性别年龄永不代填」Scenario，改为性别/年龄/种族照进候选、同「只补空格」口径；「从简介立主角」Requirement 同步（删「性别与年龄照旧 SHALL NOT 出现在草稿中」与对应 Scenario）。

## Impact

- **代码**：C端 后端 `settings/character_model.py`、`settings/characters_ai.py`（仅注释）、`prompts/` 两模板；C端 前端 `lib/characterModel.ts`、`AiWriterAssistant.tsx`、`settings/CharacterManager.tsx`（仅文案与计数上限）。
- **测试**：`test_character_model.py`（形状计数 6→8、删 author_only 断言、apply 性别照写）、`test_characters_ai.py`（draft targets 含 gender/age、bootstrap cells 含 gender/age）、`CharacterManager.bootstrap.test.tsx`（mock dossierGap 6→8）。parity（`test_shared_constants_parity.py`）与分层闸门（`test_prompt_layering.py`）不受影响（前者只锁 k/label，后者只锁 <<system>> 标记）。
- **与在途 change 的归档顺序**：`c-settings-ai-confirm-modal` 的 delta 同改「AI 四能力契约」（其文本仍保留性别年龄不代填句）；本 delta 基于其归档文本续改——归档顺序须 confirm-modal 先、本 change 后，否则后者须 rebase delta。

## Design Impact

- **受影响端**：仅 C端（S端 无对应界面）。
- **受影响屏/弹层**：设定视图「角色」右栏 AI 行文案与出卡弹窗脚注文案；无新增屏/弹层/组件。
- **对象状态**：无新增状态档位；性别/年龄/种族出稿后与其他格同为「待采纳空格建议」。
- **是否触碰两端共享段**：否。
- **是否需要原型先行**：否——纯行为口径翻转＋文案撤除，无新视觉词汇。
- **设计工件产出方**：实现侧自查。
- **判定依据**：不触共享段、不新增令牌/档位；文案措辞沿既有行词汇。
