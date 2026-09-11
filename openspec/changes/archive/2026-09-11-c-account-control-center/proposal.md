# Proposal: c-account-control-center

## Why

用户在登录后首页（书架）看不到自己的账号与套餐——#336 把账号行收进设置弹窗，可见性不足。经 PM 评审稿四轮迭代、用户逐条拍板，终审定稿为「V4' 控制中心面板」方案：顶栏右侧收敛为头像唯一入口，账号与套餐徽章常驻触发钮，设置弹窗细项全部并入面板。设计基准：`docs/design-c/drafts/account-visibility-draft.html`（已评审通过·用户终审，实施基准版）。

## What Changes

- **顶栏动作区收敛为头像唯一入口**：移除「联系客服」「设置」两枚常驻按钮（登录态动作区 2→1），新增头像胶囊（用户名首字头像 + 四态套餐徽章 + caret）；工作台顶栏的「联系客服」按钮同批移除、其「设置」（本书偏好）入口由面板承接（工作台语境面板增挂「本书偏好」项，BookPrefsModal 不孤儿化）。
- **新增控制中心面板**（popover，280px，右对齐）：账号区头（头像 + 用户名 + 套餐完整档徽章）/ 数据组（备份 · 恢复）/ 模型配置 · API Key / 支持（联系客服，新窗口打开）/ 底部退出登录（轻确认）+ 版本行。自然高度约 270px，窄窗内滚动兜底。
- **徽章两层口径**：触发钮短档四态——PRO 会员（accent）/ 试用·剩N天（充裕 muted，≤3 天转 warn，含 0 天）/ 免费版（含已过期，muted 合并单档）/ 未登录不出现（书架登录门控）；档位判定完全本地——**S端无响应或本地断网（权益同步失败）时，徽章文案照常显示既有档位、仅整体转 warn 色，恢复后自动回常规色，MUST NOT 因网络失败清缓存降级**（含修掉现有「刷新失败清缓存降免费」行为；失联信号取自前端同步失败状态）；`entitlement_degraded`（快照不完整防御态，用户裁定实际不会出现）不作为徽章信号。菜单头展示套餐完整档原文；文案单源统一收敛到共享模块（现两份 tierLabel 已分叉，统一为「PRO 会员」）。
- **设置弹窗（PrefsModal）退役**：细项承接映射——备份/恢复/模型配置/联系客服/退出登录 → 面板菜单项；全局字号/行距 seg 裁撤（与工作台「本书偏好」重复，数据层回退链保留不动）；归档 AI 摘要全局开关移除——书级控制本就存在于本书偏好弹窗（既有 seg，规格化确认而非新增），书级未设置回退全局存量值（无存量值时默认开），归档行为不变。RestoreModal 随迁不删。
- **退出登录上浮至面板底部**（警示调），前置一步轻确认，登出后回落地页（未登录首页）。
- **原型库同步重铸**：list.html / book.html / model-config.html 三屏 appbar 同批重铸头像胶囊 + list.html 控制中心面板段落（book.html 本书偏好既有归档 seg 核对保留），ADJUSTMENTS.md 登记 + design-language §13 tier 对照表回填；design-parity 三屏基线重录。
- **文案与语气词**：按钮词全部动词（备份/恢复/退出登录），无内部术语；语气词沿用 info/ok/warn/err（warn 用于试用临期与 S端失联变色），不引入新形态。

## Capabilities

### New Capabilities
- `account-control-center`: 顶栏头像触发钮与控制中心面板——账号/套餐常驻可视性（四态徽章+降级换色）、设置细项承接（备份恢复/模型配置/客服/退出登录）、面板交互口径（开合/Esc/外点/键盘）、内页顶栏同步可用。

### Modified Capabilities
- `frontend-auth-heal`: 「设置弹窗账号行展示当前账号」→ 账号可视性展示面迁移至控制中心面板账号区头（用户名 · 套餐完整档），全局偏好弹窗退役。
- `client-update`: 「设置弹窗版本行」→ 版本行迁移至控制中心面板底部（本书偏好弹窗版本行保留不变）。
- `contact-support`: 「C端 顶栏外跳入口」→ 顶栏按钮改为控制中心面板「联系客服」菜单项，外跳行为不变（target=_blank 锚点，禁编程式 window.open）。
- `workbench`: 规格化确认本书偏好弹窗既有「归档 AI 摘要」per-book 开关（含移除全局入口后的回退语义：书级未设置回退全局存量值，无存量值默认开）；工作台顶栏客服入口随面板收敛、「设置」（本书偏好）由工作台语境的面板项承接。

## Impact

- **C端前端**：`Navbar.tsx` 重构（动作区收敛+触发钮）；新组件 `AcctMenu`（popover 面板）；`PrefsModal.tsx` 删除（RestoreModal 随迁，`onGoConfig` 闭包改为关面板+跳配置）；`tierLabel` 抽共享模块（统一两份分叉文案为「PRO 会员」口径，四态短档映射同模块）；`BookPrefsModal.tsx` 归档开关为既有实现仅核对不新增；`lib/prefs.ts`、`lib/auth.ts`、`/api/auth/verify` 数据层零改动（`design-vocab.mjs` 登记簿同步换 PrefsModal→AcctMenu）。
- **e2e 迁移**：modals-pr5（设置弹窗定位用例改链路）、design-parity-list / design-parity-book / design-parity-config（三屏基线重录）、**support-link.spec.ts（顶栏按钮可见性用例重写为面板外跳链路）**；update-notice 经核无涉本 change 不动。
- **原型库**：`docs/design-c/prototypes/list.html`（顶栏+设置弹窗段→控制中心面板段）、`book.html` 与 `model-config.html`（appbar 同批重铸）、`ADJUSTMENTS.md` 登记、design-language §13 tier 对照表回填。
- **后端**：无改动（verify 契约不变；注：`entitlement` 快照缺失时省略该字段、token 缺失时返回 `{"valid":false}` 无套餐字段——徽章以 valid 会话为前提）。
- **S端**：不触碰两端共享段。

## Design Impact

- **受影响端**：C端。
- **受影响屏/弹层清单**：书架顶栏（动作区重构）、工作台等内页顶栏（同步减法）、控制中心面板（新弹层）、本书偏好弹窗（增归档开关）、设置弹窗（移除）。
- **对象状态**（对照状态语言总表）：账号套餐徽章四态——PRO 会员 / 试用·剩N天 / 免费版（含过期）/ 未登录（参考，书架不可达）；S端失联（前端同步失败信号）文案保持既有档位仅转 warn 色（`entitlement_degraded` 不消费）。语气词：warn 用于试用临期与 S端失联，不引入 --err、不新增第四种胶囊形态。
- **是否触碰两端共享段**：否。
- **是否需要原型先行**：是——设计基准已由设计侧会话产出并终审定稿（`docs/design-c/drafts/account-visibility-draft.html`，评审稿含四变体对照与全部拍板口径）；实现侧须同步重铸 prototypes/list.html、book.html 并登记 ADJUSTMENTS，按稿自查 parity。
- **设计工件产出方**：设计侧会话（PM，已交付定稿）；实现侧自查。
