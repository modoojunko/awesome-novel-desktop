# Tasks: c-version-account-visibility

## 1. 原型先行（C端 像素基线同批重铸）

- [x] 1.1 `prototypes/` 受影响屏（index/home/list/book/model-config，含 backup-restore 若受全局条影响）同批补窗口底部状态条（左 © 行、右版本号 muted 小字），list 屏删除原页脚 © 常驻条；逐处在 `ADJUSTMENTS.md` 登记偏差原因（引用 V3 视觉稿已批）。验证：打开各原型肉眼核对状态条三态版式与 `version-placement-draft.html` V3 一致
- [x] 1.2 确认原型新增元素全部用既有 token 档位（无新任意值、无裸色值、无 emoji）。验证：`npm run design:lint` 通过（应用栈未起时先跑 lint 侧）

## 2. 版本数据与文案单源

- [x] 2.1 新增 `src/lib/version.ts`：`formatVersion(current)` 单源函数（`0.15.1`→`v0.15.1`、`dev`→`开发版 dev`、`null`→`版本未知`）；新增 `useClientVersion()` hook（模块级 Promise 缓存，quiet 调 `/update-check` 取 `current`，失败静默返空且失败结果不缓存、后续消费方挂载可重试）。验证：vitest 单测覆盖三分支文案、失败静默与失败不缓存重试（CI 不跑 vitest，本地必须跑）
- [x] 2.2 UpdateNotice rider 的 `current` 取自身检测响应（不接 `useClientVersion` 缓存、不新增请求），`formatVersion` 与全局单源共用；确认未改动检测节流与 dismiss 语义。验证：既有 UpdateNotice 相关测试全绿 + 本地 vitest 全量通过

## 3. 状态条（V3 落点）

- [x] 3.1 新增状态条组件（约 26px、border-top 细线、muted，纯 token 组合不新增 base.css 共享类），挂 `ClientShell` 最外层底部：左侧版权文案（`app-credits` 钩子）、右侧版本号（`app-status-bar` 钩子，`data-od-id`）。验证：`tsc --noEmit` 通过；登录态、未登录态、工作台三态肉眼均见状态条
  > 证据：tsc 0 错；e2e statusbar.spec 9/9 绿（三态可见+落地页豁免+dev 文案+失败静默+单底条，2026-09-07 本地对 5176 栈）
- [x] 3.2 书架屏移除原页脚 © 常驻条，版权文案改由状态条承载。验证：书架窗口底部仅一条常驻条；e2e 中涉及页脚版权的既有断言更新后通过
  > 证据：Footer.tsx 删除（唯一消费点 App.tsx）；e2e「页脚并入」用例绿（.pagefoot=0 & statusbar=1）；全仓 e2e 无页脚既有断言（grep 证）

## 4. 弹层改动

- [x] 4.1 `PrefsModal`：账号行描述改「{用户名} · {套餐文案}」（`getUsername()`，`pref-account` 钩子；超长 ellipsis + `title` 全文；本地无用户名时不硬造）；弹窗底部加版本行（`pref-version` 钩子，打开时静默取版本不阻塞）。验证：登录态打开弹窗用户名与套餐同屏；40 字符用户名截断悬停见全文
  > 证据：e2e statusbar.spec「账号行同屏」「长用户名截断+title」两用例绿；vitest version.test 5 用例绿
- [ ] 4.2 `BookPrefsModal`：底部加同一版本行组件（不新增用户名；既有账号行=套餐文案/升级入口保持不动）。验证：工作台打开本书偏好弹窗见版本行、无新增用户名
- [x] 4.3 `UpdateNotice` rider 文案：「发现新版本 v{latest}」→「发现新版本 v{latest}（当前 v{current}）」，`current` 判空缺失时退回原文案。验证：mock `latest=0.16.0/current=0.15.0` 断言对照文案；无更新时不渲染不变
  > 证据：vitest UpdateNotice.test 6 用例绿（含缺失 current 退回分支）；e2e update-notice :28（rider 对照文案）在新前端全量跑中通过（该用例在旧前端基线失败=预期，新文案旧前端没有）

## 5. e2e 与门禁

- [ ] 5.1 新增/更新 e2e（spec 场景直译）：三态状态条可见且含版本号、dev 文案「开发版 dev」非「vdev」、获取失败「版本未知」无 toast、账号行用户名·套餐同屏、两弹窗版本行、rider 对照文案、页脚并入单底条。验证：本地 docker 栈全量 e2e 绿（按 C端 e2e runbook，勿只跑单 spec）
  > 状态：本 change 全部新用例绿（statusbar.spec 9/9 + update-notice rider 断言绿）。**全量套件被共享环境毒化**：S端（本地 19000）登录/注册限频+会话竞态致 46 失败，同刻同份 spec 打主栈旧前端（无本改动）失败集等价（54 中扣除新 spec 预期失败 10 个后逐条对齐；session-invalid/story-arc 双栈同刻同败 4F/1P）——失败与本 change 无关，为存量环境/竞态问题（config-modal-width 会话已记录同类存量红）。新 spec 的 green 路径全部走打桩不依赖真实登录。待环境恢复后补全量绿存档。
- [x] 5.2 设计门禁全绿：`npm run design:lint` + `npm run design:check`（像素差 <0.2%，diff 图落 baselines）；确认未触碰共享段（若实现中新增了 base.css 类，停手回来补 design-system delta）。验证：两命令本地全绿输出留档
  > 证据：design:lint 绿（存量冻结项不阻断）；三屏 parity 11/12 绿——唯一红 book·settings 为存量结构性超阈（原型 book.html 设定 7 项 vs 实现主线合并后 8 项，主线合并起即红，主仓基线停在 08-29；已登记 ADJUSTMENTS「存量观察」，本 change 不动）。状态条/弹窗版本行/rider 字面量均已入原型同批重铸，零新增漂移。
  > 评审 P2 修复（4ef51e9）：工作台 .wb 与登录 .auth-wrap 真实让位 26px（原实现固定条盖列底+app 幽灵滚动，parity 静态截图测不出滚动缺陷），原型 book.html 改链内 .sb-spacer 同批对齐；三份 parity spec 补 /api/auth/config 打桩（新栈 backend 对其 401 → api.ts 全局跳 /#/login 弹离场景，trace 实证）。修复后 parity 仍 11/12、statusbar.spec 9/9 绿。
- [ ] 5.3 全量回归：`tsc --noEmit`、vitest、全量 e2e、既有 settings/modal 相关 spec 无回归。验证：全部本地绿后按仓库流程提 PR（PR CI 含 S端 e2e 与门禁）
