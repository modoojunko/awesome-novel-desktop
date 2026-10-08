# c-chars-stale-reconfirm — 「内容有变 / 重新确认」状态链收口

## Why

`c-chars-confirm-scope`（#753/#758）把卡级保存与整项确认分了家，但**第三态「内容有变 · 待重新确认」这一段还没收口**——同一屏里两处结论打架、且其中一处不会自愈：

1. **同屏两个结论**：内容改过后，面板头徽标显示「内容有变 · 待重新确认」（warn），而页脚同时显示「已确认 · 改动自动保存，可随时重新确认」**加一枚绿色「✓ 已确认」**。用户被告知"待重新确认"与"已确认"各一次。
2. **徽标不会自愈（角色的硬伤）**：`useOnboarding` 只取一次 `characters/gate/status`（deps `[projectId, confirmedStatus]`），且回填逻辑**只置真不清假**（`if (confirmed && stale) setTrue` / `if (!confirmed) setFalse`）。于是：改过内容后的角色面板，点「重新确认」把存档重新盖过之后，徽标仍写着「内容有变 · 待重新确认」，**要刷新页面才恢复**。伏笔面板同场景是即时恢复的（本地指纹快照派生）——两个自动保存制面板在这一点上行为不一致。

## What Changes

- **角色的确认存档状态改「精确值 + 主动重取」**：`charStale` 回填改为 `confirmed && stale` 的精确判定（不再只置真）；并以 `refreshCharStale()` 暴露重取口——**每次进入/返回角色面板的数据刷新后**（`CharacterManager.reloadList` 成功即通知父层，含单卡保存落库后的重取）与**每次确认/重新确认成功后**重取。效果：徽标与页脚在同一次渲染里同源，且重新确认后立即恢复「已确认」。
- **stale 期间页脚让位**：角色/伏笔两面板，内容有变时页脚提示改「内容改过了——点「重新确认」即可，改动已自动保存」，并且不渲染绿色「✓ 已确认」标注（warn 语气由面板头徽标承担，不在页脚二次告警）；**缺口优先于 stale**——有缺口照旧点名缺口（那才是点下去会被拦的原因）。
- **伏笔面板同口径**：`HooksSettingForm` 已本地派生 `stale`，把它并入上报的面板状态，页脚按同一判据让位（不新增请求）。
- 明确不做：不改门禁判据与指纹算法（后端零改动）；不给「内容有变」单独加提示语气；不动 `内容有变 · 待重新确认` 徽标文案（设计语言硬规则：该文案不含「已确认」）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `character-settings`: 「确认门禁两档与退回」补齐第三态的**页脚让位口径**（stale 时不以「已确认」表述、不渲染已确认标注）与**状态刷新口径**（进入面板的数据刷新与每次确认成功后重取确认存档；重新确认成功即恢复「已确认」）。
- `foreshadow-settings`: 「确认门禁与内容有变降级」补齐同一让位口径（其指纹为面板本地派生，刷新口径不需要）。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：设定屏 · 角色面板（页脚提示 + 已确认标注）、设定屏 · 伏笔面板（页脚提示 + 已确认标注）。面板头徽标文案不变。
- **对象状态**：仍用既有档位（warn 徽标 + note 行 + 绿色 done-note），不新增语气/形态；本批**减少**一处同屏重复告警。
- **共享段**：不触碰。
- **原型先行**：需要——`docs/design-c/prototypes/character-settings.html`（`syncFoot` 补 stale 态与让位；demo 用确认时的门禁字段快照判定内容有变）与 `foreshadow-settings.html`（同名处同口径），偏差登记 `ADJUSTMENTS.md`。
- **设计工件产出**：实现侧自查（design:lint + parity 记录）。

## Impact

- 前端：`hooks/useOnboarding.ts`（精确回填 + `refreshCharStale`）、`components/novel/NovelWorkspace.tsx`（透传）、`components/novel/workbench/SettingsView.tsx`（让位判据 + 重取时机）、`components/novel/settings/CharacterManager.tsx`（列表刷新成功后通知）、`components/novel/settings/HooksSettingForm.tsx`（上报 stale）。
- 测试：`useOnboarding` 精确回填单测；`SettingsView` 让位三态（stale 无缺口 / stale 有缺口 / 非 stale）+ 重新确认后重取；e2e 角色链补「改内容 → 徽标与页脚同步为内容有变 → 重新确认 → 双恢复」；伏笔 e2e 已在测徽标恢复，补页脚让位断言。
- 原型：`character-settings.html`、`foreshadow-settings.html` + `ADJUSTMENTS.md`。
- 后端：零改动。
