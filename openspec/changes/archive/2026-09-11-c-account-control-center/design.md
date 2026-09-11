# Design: c-account-control-center

## Context

设计基准已定稿：`docs/design-c/drafts/account-visibility-draft.html`（PM 评审稿·用户终审通过，含全部拍板口径与四变体取舍记录）。现状：`Navbar.tsx` 顶栏动作区为「联系客服 + 设置」两枚 ghost 按钮；`PrefsModal.tsx`（全局设置弹窗）承载字号/行距/AI 摘要/备份恢复/模型配置/账号行/版本行；`BookPrefsModal.tsx`（本书偏好）已有字号/行距与版本行；数据层 `lib/auth.ts`（auth_token/auth_username）、`lib/prefs.ts`（全局与书级偏好回退链）、`/api/auth/verify`（tier/is_member/expired/trial_remaining_days/entitlement/entitlement_degraded）全部现成，本 change 无后端改动。

## Goals / Non-Goals

**Goals:**
- 顶栏头像胶囊 + 控制中心面板（popover），账号/套餐徽章四态 + 降级换色，两层文案口径（触发钮短档 × 面板头完整档）
- PrefsModal 退役且功能零丢失（承接映射见 spec）；书级归档开关落入 BookPrefsModal
- 原型库同步重铸（list.html / book.html + ADJUSTMENTS 登记），parity 基线重录，e2e 迁移全绿

**Non-Goals:**
- 不动后端与两端共享段；不动 `lib/prefs.ts` 数据层与回退链（只删界面入口）
- 不做「账号独立页 / 多账号管理」（面板形态为其预留 IA 位置，另期立项）
- 不新增第四种胶囊形态、不引入 --err 语气（沿用 info/ok/warn/err 词汇表）

## Decisions

1. **新组件 `AcctMenu`（popover）而非复用 AppModal**：面板是锚定触发钮的非模态轻弹层，需要 Esc/外点关闭、焦点圈、aria-expanded——与模态弹窗（遮罩+焦点困留）语义相反。C端 无现成 popover 基建，此为本 change 唯一新组件；实现遵守 daisyUI 弹层教训（portal 防 containing block 劫持、退场竞态收窄 `.show` 口径）。
2. **文案统一收敛到共享单源，而非「tierLabel 零改动」**：现状有两份已分叉的 tierLabel（PrefsModal「PRO 会员」/ BookPrefsModal「PRO 版 · AI 能力已解锁」），且 PrefsModal 即将删除。抽取共享模块 `lib/tier.ts`：tierLabel 完整档（判定优先级 expired → trial → is_member → 免费版）与四态短档映射函数同模块，AcctMenu 与 BookPrefsModal 共同消费；会员文案统一取用户终审看过的「PRO 会员」口径（BookPrefsModal 归一）。
3. **S端失联变色：文案保持本地档位，仅转 warn 色**（用户终审裁定）：真正要兜的场景是「登录后某段时间 S端无响应/作家本地断网」。verify_session 为纯本地读，断网时徽章文案照常（既有档位）；**失联信号取自前端**——LicenseProvider 同步刷新失败即置失联标志，徽章据此整体转 warn（触发钮与面板头同步），同步成功自动回常规色。失联期间 MUST NOT 清缓存、MUST NOT 降级展示；需修 LicenseProvider 既有 catch「刷新失败清缓存降免费」→ 改为「保留上次快照判定 + 置失联标志」，与同文件「绝不因网络降级会员」注释对齐。`entitlement_degraded`（后端快照不完整防御态）不作为徽章信号。
4. **徽章数据源复用 LicenseProvider，Provider 上移至壳层已登录分支**：`LicenseProvider` 现仅挂 `/novels`、`/novel/:id`，`/config` 无 Provider——AcctMenu 挂 ClientShell 后徽章在 `/config` 会落 SAFE_FREE 翻车。将 Provider 上移到 ClientShell 的 loggedIn 分支与 AcctMenu 同层（保留未登录页不发 verify 的门控），徽章消费 `useTier`/模块级 `cachedVerify`，零新增请求点位、零新增轮询（节奏=Provider 既有两跳刷新 60s 节流；`useAuthHeal` 是启动期一次性自愈，与徽章无叠加）。catch 分支「失败清缓存降免费」一并修正为「保留上次快照判定 + 置失联标志」（对齐「绝不因网络降级会员」注释），失联标志驱动徽章变色，徽章与书架横幅口径一致。
5. **PrefsModal 直接删除而非置灰**：承接项全部迁入面板后无残留功能；`RestoreModal.tsx` 随迁保留（备份/恢复流程复用，其 `onGoConfig` 闭包改为「关面板 + 跳配置」）。`getDefaultFontSize/getDefaultLineHeight/getArchiveAiSummaryEnabled` 等 prefs 导出保留（回退链消费中），仅删界面入口；归档开关为 BookPrefsModal 既有实现（seg-archsum），本 change 只规格化确认不新增代码。
6. **退出登录轻确认 + 内页顶栏同步**：退出登录面板内联二步（点「退出登录」→ 变「确认退出？」二次点击执行，Esc/外点复位），不弹模态；登出走既有 `logout()` 回落地页（未登录首页）。工作台顶栏客服/设置动作同批收敛为头像入口，`AcctMenu` 挂载点为全局壳层级（`ClientShell`）一份实例；工作台语境下面板增挂「本书偏好」项承接 BookPrefsModal（其唯一既有挂载点是原「设置」按钮），避免书级偏好孤儿化。

## Risks / Trade-offs

- **e2e 面最大**：modals-pr5 / **support-link（顶栏按钮可见性断言必改）** / design-parity-list / design-parity-book / design-parity-config（appbar 三屏同批重铸后基线重录）——迁移清单见 tasks；设计 parity 基线必须先重铸原型再重录，顺序不能反。
- **LicenseProvider 上移 + catch 行为修正**：需保留未登录页不发 verify 的门控语义；catch 改「保留上次快照判定」后，断网期间书架横幅（试用引导）与徽章的口径需一并对拍。
- **popover 新组件的可达性与双触发**：焦点圈、aria-haspopup/aria-expanded、方向键不逃逸、外点白名单必须含触发钮——按面板交互口径 spec 验收；键盘路径回归放进 e2e。
- **原型先行纪律**：先改 prototypes（ADJUSTMENTS 登记）再动实现，否则 parity 门禁红——本 change 的 CI 成本主要在此。
