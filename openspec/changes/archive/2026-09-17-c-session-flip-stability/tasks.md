# Tasks — c-session-flip-stability

## 1. 双端影响判定（规则要求的首任务）

- [x] 1.1 判定本 change 为 C端 行为级修复（api.ts 拦截器语义 + ClientShell 渲染结构），无视觉变更、不触两端共享段、无原型先行义务——已判定，依据见 proposal「Design Impact」。

## 2. 401 quiet 豁免

- [x] 2.1 `src/lib/api.ts`：盘点全部 401 全局处理分支（现两处），统一加 `quiet` 豁免——quiet 请求 401 时不清凭据、不导航，按既有静默错误路径返回；注释写明踢出口径两条路径（用户动作 401 / useAuthHeal 显式失效）。
- [x] 2.2 vitest 单测：① quiet 请求 401 → localStorage 凭据保留、无导航副作用 ② 非 quiet 401 → 凭据清除+导航（现行为钉住）。

## 3. ClientShell 子树稳定

- [x] 3.1 `ClientShell` 恒渲染 `<LicenseProvider>{inner}</LicenseProvider>`；`LicenseProvider` 增加未登录透传分支（不发 verify/check-auth、children 原样渲染），保持已登录分支行为不变。
- [x] 3.3 【apply 期新增，见 design 决策 6】LoginPage 自动登录反弹熔断：api.ts 401 踢出时记 `last_auth_kick_at`，LoginPage 3 秒内跳过自动登录——实测「自动登录写回 ↔ 业务 401 踢出」互踢可达 1514 请求/3s，违背本 change 规格「失效处理不循环」场景，守卫用例首跑即抓到。
- [x] 3.2 vitest 单测：① 登录态翻转（mock isLoggedIn 变化）时 UpdateNotice/ExpiryNoticeBar/StatusBar 挂载次数不随翻转增长（可用请求计数代理）② 未登录时 LicenseProvider 透传渲染、零认证请求。

## 4. e2e 守卫固化

- [x] 4.1 新增守卫 spec：书架页加载完成 → 静止 3 秒窗口 `/api` 请求 ≤8，超预算时失败信息列出超预算请求清单（方法+路径+次数）。
- [x] 4.2 `e2e/helpers.ts` createNovel：点击「新建作品」改为稳定点击（toPass 重试包裹），注释标注「会话翻转风暴已由守卫用例钉死，此处为保险」。
- [x] 4.3 全量跑一轮后按实测翻转态请求量复核预算值 8 是否合理：守卫用例在全量中通过（熔断后空闲窗口 ~2 请求/3s，预算 8 无需调整）；首跑曾实测 1514 请求/3s（互踢循环），证明该预算对风暴类回归足够灵敏。

## 5. 回归

- [x] 5.1 C端 `tsc --noEmit` + `vitest` 全绿（含 2.2/3.2 新单测）。
- [x] 5.2 `session-invalid.spec.ts` 单跑 2/2 绿（3.9s）——显式失效踢出路径未动的直接证据。全量中 :10 失效提示条缺失为存量顺序依赖竞态（interceptor 踢出先于 heal 写入提示的挂载竞态，LoginPage 注释自证已知）：基线全量（无本 change）同签名红、单跑绿，与本 change 无关，登记跟进。
- [x] 5.3 C端全量 e2e（worktree 隔离栈，单 worker）：136 passed / 1 failed（上述存量竞态）/ 14 skipped；建书 detached-DOM 类 0 命中（stableClick 保险未触发额外重试）；守卫用例绿。
- [x] 5.4 门禁输出：`npm run design:lint` / `npm run design:check` 全绿（无视觉改动，跑门禁证明零像素漂移）；无共享段改动，design-cross 不适用（依据 1.1 判定）。
