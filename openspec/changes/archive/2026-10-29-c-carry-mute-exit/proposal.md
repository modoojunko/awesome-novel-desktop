## Why

书架顶部迁移提醒行的「本版不再提醒」是个死按钮：点了以后常驻行不消失，用户反复点也没用（2026-10-29 用户报修：「我点了本版本不再提醒还是消失不掉」）。

根因是两处实现与 spec 打架：

- `db-generation` 主 spec 的「部分迁移态呈现与缺口清单」要求常驻行给「本版不再提醒」次级出口，且场景写明「点后常驻行消失、账户 › 本机旧版本数据 仍可达」；
- 但「搬运不完整必须提示用户」（2026-10-09 拍板）又写着「SHALL NOT 提供静默/永久不再提醒出口」，其场景明说「无『不再提醒』」。

实现取了两边各一半：按钮照新版 spec 渲染出来，可见性判断却把 `suppressed`（已被静音）当成**显示**条件，于是部分迁移态和普通稍后带态下点静音都不会消失。两条要求互相矛盾必须收敛成一条口径。

## What Changes

- **收敛静音语义**：统一为「本版不再提醒」＝按候选指纹抑制当前版本（下一版本建新库自动重评估），抑制后顶部常驻提醒行 SHALL NOT 渲染（含 `carried_partial` 部分迁移态）；缺口清单与重迁入口始终经「账户 › 本机旧版本数据」可达。
- **禁止的是「永久静默」**，不是「本版不再提醒」：不提供永久删除提醒/永久不再提示的出口；抑制态与 `migration.*` 同存当前版本库 `app_meta`，装回旧版读不到，语义不变。
- 前端可见性条件从 `suppressed || carryLater || carried_partial` 改为 `!suppressed && (carryLater || carried_partial)`。
- 顺带收敛展示口径：非部分迁移行的源书数在「稍后带」后才出现（卡要求 `book_count>0` 才弹），删除不可达的 `?` 占位分支。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `db-generation`：
  - 「部分迁移态呈现与缺口清单」新增「抑制优先于部分迁移态」条款——`suppressed` 时常驻行不渲染，入口仍可达；
  - 「搬运不完整必须提示用户」把「SHALL NOT 提供静默/永久不再提醒出口」收窄为「SHALL NOT 提供**永久**静默出口」，明确「本版不再提醒」是本版本、绑候选指纹的次级出口；对应场景 THEN 同步。

## Impact

- 前端：`client/frontend/src/pages/NovelListPage.tsx`（常驻行可见性条件与文案）；`client/frontend/src/__tests__/novelListPage.test.tsx`（三例改写＋两例新增：静音后常驻行消失、部分迁移＋静音不渲染）。
- 不改后端：`/dismiss`（snooze）与 `suppressed` 载荷语义本就正确，纯前端取反。
- 不涉及迁移引擎、数据搬运、模板与提示词；无 **BREAKING** 数据/接口变更。
