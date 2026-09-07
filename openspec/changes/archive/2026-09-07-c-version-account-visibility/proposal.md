# Proposal: c-version-account-visibility — C端 版本号与当前账号可视性

## Why

用户反馈原话：「C端登录后，不知道C端版本号，也不知道我登录的是哪个账号。」版本号数据链路（打包烘焙 CLIENT_VERSION → `/update-check` 的 `current`）和用户名（localStorage `auth_username`）全都现成，只是界面零展示：报障时用户答不上版本、说不清账号，每单客服沟通多一轮往返。属于纯可视性补课，零新接口。

## What Changes

- **版本号常驻（V3 落点，视觉稿已批）**：窗口底部新增一条细状态条（约 26px），版本号右对齐 muted 小字；登录态、未登录态、工作台内三态全覆盖。书架页脚既有「© 行」并入状态条，避免出现双底条。
- **设置弹窗版本行**：PrefsModal（全局偏好）与 BookPrefsModal（工作台偏好）底部各加一行 muted 版本小字（报障终点与账号同屏；打开时随现有请求并行 quiet 调 `/update-check`，失败静默显「版本未知」不弹错）。
- **账号行升级**：PrefsModal 账号行描述从「只有套餐文案」改为「用户名 · 套餐文案」（用户名取 `getUsername()`；超长 ellipsis 截断 + `title` 悬停全文）。
- **更新提示条对照文案（rider）**：UpdateNotice 文案「发现新版本 v{latest}」→「发现新版本 v{latest}（当前 v{current}）」，零额外请求。
- **省略项（随 V3 全态覆盖裁定）**：原方案的「未登录页脚版本行」兜底不再需要——状态条天然覆盖未登录态。
- dev 态版本文案「开发版 dev」（不渲染成「vdev」），获取失败「版本未知」，全程静默无 toast。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `client-update`: 两条新增需求 + 一条修订需求——ADDED ①版本号常驻展示（窗口底部状态条，含 © 行并入与三态覆盖）②设置弹窗（全局/工作台）底部版本行；MODIFIED ③更新提示条带当前版本对照文案。版本数据仍走既有「版本自报」单一来源，不新增接口。
- `frontend-auth-heal`: 新增一条需求——设置弹窗账号行展示当前登录账号（用户名 · 套餐文案），登录态账号可视可辨。

## Design Impact

- **受影响端**：仅 C端。
- **受影响屏/弹层清单**：全局状态条（ClientShell 级，覆盖 index/home/list/book/model-config 全部屏）；PrefsModal、BookPrefsModal 两弹层；UpdateNotice 提示条；书架（list）页脚 © 行并入状态条。
- **对象状态（对照状态语言总表）**：不新增业务对象状态。版本文案三态 = 正常（`v{X.Y.Z}`）/ 开发版（`dev`）/ 未知（获取失败静默降级）；均为只读 muted 展示，不引入 notice/pill/toast 新形态，语气词表（info/ok/warn/err）零改动。
- **是否触碰两端共享段**：否。状态条与版本行用既有 oklch token 与既有类组合实现，不新增 base.css 语义类、不改令牌档位；若实现中确需新增共享类，须回头补 design-system delta 并双端同批。
- **是否需要原型先行**：需要。C端 用户可见改动，须先改 `prototypes/*.html`（受影响屏补状态条、list 页脚 © 行并入）并在 `ADJUSTMENTS.md` 登记偏差原因，再改实现，最后 `design:check` 像素 parity 全绿。落点视觉稿已批：`docs/design-c/drafts/version-placement-draft.html`（V3）。
- **设计工件**：设计侧已产出（需求稿 `~/Desktop/knowledge/c-client-version-account-visibility-design-2026-09.md` §7 拍板记录 + 视觉稿 V3）；实现侧按原型→实现→parity 自查。

## Impact

- **代码**（均 client/，纯前端）：`ClientShell.tsx`（挂载状态条）、`PrefsModal.tsx`（账号行 + 版本行）、`BookPrefsModal.tsx`（版本行）、`UpdateNotice.tsx`（rider 文案）、新增状态条组件与 `src/lib/version.ts`（版本文案单源 + 版本缓存 hook）各一处；`auth.ts` 复用 `getUsername()` 不改。
- **接口**：零新增。复用 `GET /update-check`（`current` 字段）与本地 `auth_username`。
- **设计资产**：`prototypes/` 受影响屏 + `ADJUSTMENTS.md` 登记；`design:check` 基线随原型更新。
- **不做**（非目标）：不动顶栏信息架构；不做独立「关于」页；用户名不脱敏；不展示设备授权状态；不动退出登录/注销流程（注销入口已裁定在 S端）；BookPrefsModal 不新增账号身份展示（其既有账号行=套餐文案/升级入口，PR5 功能保持不动）；不修系统窗口标题「AI Novel」与品牌名不一致问题（视觉稿旁注观察项，属独立微改，不入本 change 范围）。
