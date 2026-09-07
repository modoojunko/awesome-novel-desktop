# Design: c-version-account-visibility

## Context

版本号与用户名的数据面全部现成：`GET /update-check` 响应带 `current`（UpdateNotice.tsx 已在调，但只用了 `latest`）；`localStorage.auth_username` 由 `lib/auth.ts` 读写。缺口纯在展示层：全应用零版本展示、PrefsModal 账号行只有套餐文案。视觉落点已批 V3（窗口底部状态条），稿见 `docs/design-c/drafts/version-placement-draft.html`。C端 设计门禁约束：用户可见改动必须原型先行 + ADJUSTMENTS 登记 + `design:check` 像素 parity（<0.2%）。

## Goals / Non-Goals

**Goals:**

- 三态（登录/未登录/工作台）版本常驻可见，一条实现路径全覆盖
- 版本文案口径三处（状态条/弹窗/rider）单源不漂移
- 零新增接口、零共享段（base.css）改动、零新语气形态

**Non-Goals:**

- 不动顶栏两变体；不做「关于」页；不展示设备授权状态；不脱敏用户名
- 不修系统窗口标题「AI Novel」与品牌名不一致（独立微改，另行立项）
- 不改 UpdateNotice 的检测节流/dismiss 语义（rider 只动文案）

## Decisions

### D1. 状态条挂在 ClientShell 最外层底部，不进任何屏

ClientShell 已是全局层（UpdateNotice / ExpiryNoticeBar / useAuthHeal 都挂这），状态条作为其最底部子元素，天然三态覆盖、路由切换不消失，工作台沉浸模式也盖得到（沉浸模式只收顶栏，不收 ClientShell 层）。唯一豁免：免登录营销落地页 `/` 不呈现（该页自带品牌页脚已含版本行——home.html 原型 pagefoot 右侧即 `v0.9` 字样；营销页非应用态，且其页脚经 c-home-redesign 三轮评审定稿，不叠加系统条）。
备选「各屏各自挂」否决：六个屏重复实现，必然漏态。备选「pywebview 原生状态栏」否决：无此能力，DOM 内固定条是唯一路径。

### D2. 版本数据用模块级缓存的一次性 quiet 获取

新增轻量 `useClientVersion()`：首次调用发一次 `GET /update-check` 取 `current`，模块级 Promise 缓存，后续消费方（状态条、两弹窗）直接复用——版本在进程运行期不变，无失效问题；仅缓存成功结果，失败不缓存，后续消费方挂载时自动重试（防启动瞬间本地后端未就绪把整会话锁死在「版本未知」）。弹窗打开本身不发新请求，直接吃应用级缓存。dev 构建后端本就返回 `dev` 并跳过外呼（既有「版本自报」语义），前端透传即可。请求失败静默返回空，消费方显「版本未知」，与 UpdateNotice 同款静默哲学，不弹 toast。

### D3. 版本文案单源函数

`formatVersion(current: string | null)`：`"0.15.1"` → `v0.15.1`；`"dev"` → `开发版 dev`（防「vdev」）；`null` → `版本未知`。状态条、弹窗版本行、UpdateNotice rider 三处共用，杜绝口径漂移。落 `src/lib/version.ts`。

### D4. 书架 © 行整体并入状态条

状态条左侧放原页脚版权文案（原样式照搬、字号沿 muted 口径），右侧版本号；书架屏删除原 pagefoot 常驻条，保证窗口底部只有一条。其他屏本来没有页脚条，无并入问题。

### D5. 样式走既有 token + 局部组件，不新增 base.css 共享类

状态条约 26px 高、`border-top` 细线、muted 前景色，全部用现有 oklch 令牌档位与既有类组合；不新增共享语义类 → 不触发双端同步义务，不进 design-vocab 词表变更。字号/间距用词表既有档位，避免任意值登记簿新增条目。状态条与版本行文本保持可选中复制（勿加 `user-select:none`）——客服场景用户直接复制版本号最省事。

### D6. e2e 断言钩子沿用 data-od-id 约定

`app-status-bar`（状态条）、`pref-account`（账号行）、`pref-version`（弹窗版本行）。验收场景直接译自 change specs 的 Given/When/Then。

### D7. 原型与基线一次性同批重铸

受影响屏（list / book / model-config）同批补状态条 + ADJUSTMENTS.md 逐处登记（理由：版本常驻可视性，V3 已批），list 页脚 © 行同步移入状态条；`home.html` 豁免（自带品牌页脚已含版本行）、`index.html` 为设计说明页非应用态均不加；原型版本号字面量随 parity 打桩口径取值（list/book=`v0.11`、model-config=`v0.13`）。实现完成后 `design:check` 重铸基线。分批改原型会导致 parity 中间态长期红，必须同批。

## Risks / Trade-offs

- [状态条吃掉工作台 26px 纵向空间，编辑器可视高度变化] → 工作台内容区 flex 自适应；e2e 全部语义定位无坐标断言，不受像素位移影响；视觉稿已画工作台关卡态确认可行。
- [design:check 基线全屏变更，一次性 diff 噪音大] → 原型同批改+登记，parity 用「原型↔实现」成对验证而非逐屏挑拣；diff 图落 baselines 留档。
- [UpdateNotice rider 的 `current` 字段理论上缺失] → rider 仅在「有更新」分支渲染，该分支检测必然成功、`current` 必有值；仍防御性判空，缺失时只显示「发现新版本 v{latest}」不带括号。
- [版本缓存与真实版本不一致] → 安装包运行期版本不变，模块级缓存无失效场景；dev 态每次启动重新求值，无陈旧窗口。

## Migration Plan

纯前端无数据迁移。合并后随下次 `v*` tag 发版生效；回滚 = revert 对应提交。上线顺序即实现顺序：原型 → 实现 → parity 门禁 → e2e → 发版。归档时补 `frontend-auth-heal` 主 spec 的 Purpose（现遗留 TBD 占位），写明该 capability 覆盖「C端 登录态的维护与呈现」——本 change 的账号展示需求即归入此口径，未来账号展示类需求增多时再考虑拆分。

## Open Questions

（无——落点、文案口径、范围边界均已由需求稿 §7 拍板记录与视觉稿 V3 定版。）
