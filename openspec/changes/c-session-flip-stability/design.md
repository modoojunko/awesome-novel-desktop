# Design — c-session-flip-stability

## Context

诊断链（2026-09-16 实测 + 代码实勘）：

- 循环燃料：e2e 半真会话（注册用户 + 随机 pc_hash，未配对）→ 后端校验面拒绝。S端无 API 级设备配对端点（配对走 auth_url 浏览器流程，`server/app/interfaces/web_api/devices.py` 仅 my/remove），故「setup 配对设备」不可行，桩 check-auth 仍是必要手段。
- 放大器一：`api.ts` 两处 401 拦截器（约 :64 业务请求、:220 另一封装）无条件 `removeItem("auth_token")` + `location.href = "/#/login"`；`ExpiryNoticeBar.tsx:37` 注释自证团队已知此坑并逐点绕行。
- 放大器二：`ClientShell` 按 `isLoggedIn()` 返回不同树形（裸 `inner` vs `<LicenseProvider>{inner}</LicenseProvider>`），两条分支子树身份不同 → 一次翻转 = app-shell 整树卸载重挂，UpdateNotice（挂载即拉更新检测）、ExpiryNoticeBar（挂载即拉 check-auth）、StatusBar、路由全部重打启动请求。实测：健康 ~5 请求/3s，翻转态 ~20/3s，异常态 2017/2.5s。
- 次级放大：`App.tsx` `key={location.pathname}` 路由整树重挂（page-enter 动画设计，**本 change 不动**）。

## Goals / Non-Goals

**Goals**
- 会话翻转不再重挂壳层常驻组件；书架空闲期请求预算固化为 e2e 守卫。
- 探测类 401 零全局副作用；踢出口径收敛为两条明确路径。
- UI 建书路径稳定（detached-DOM 重试类清零）。

**Non-Goals**
- 不改 e2e 半真会话手法（见 Context，配对端点不存在）。
- 不动 `App.tsx` 的 key 重挂（动画语义，另行评估）。
- 不改后端任何代码（本 change 纯 C端）。

## Decisions

1. **透传型 Provider**：`ClientShell` 恒渲染 `<LicenseProvider>{inner}</LicenseProvider>`，由 `LicenseProvider` 内部处理未登录态（不发起 verify/check-auth 请求、直接透传 children、不注入上下文值或注入空档位）。子树身份稳定，翻转只变上下文内容。备选「外壳保持条件分支但用同一 key」不可行——React 树形不同位置即重挂，与 key 无关。
2. **quiet 豁免而非白名单端点**：`request(options.quiet)` 机制已存在（错误静默），扩展其语义为「零全局副作用」（含 401 踢出）；两处 401 分支同批改。选它而非「敏感端点白名单」：端点清单会漂移，请求语义（探测 vs 动作）才是稳定口径。
3. **useAuthHeal 显式失效路径不动**：code 1 + session_invalid 的踢出是产品契约（session-invalid e2e 已钉），quiet 豁免不覆盖 hook 内部逻辑。
4. **守卫口径**：书架页加载完成（书卡或空态出现）后静默 3 秒，统计 `/api` 请求 ≤8。依据：健康实测 ~5/3s，留余量；预算含轮询类（状态条等）。数值写进 spec 便于回归对拍。
5. **createNovel 稳定等待**：点击「新建作品」前对按钮做 `expect(async () => 点击成功).toPass()` 式稳定点击（或先等列表渲染 settled），风暴消失后此条退化为纯保险。

## Risks / Trade-offs

- quiet 豁免可能让「探测全 401 但用户无感」的状态持续更久——用户下一个动作请求仍会踢出，且有到期提示条呈现降级状态，可接受。
- LicenseProvider 未登录分支的档位语义需与现状对齐（登出页本就不挂 Provider，透传后登录页读不到上下文——与现状一致，无行为差）。
- 守卫预算 8 是经验值，环境抖动可能误报——预算内区分端点归属（日志列出超预算请求清单）便于甄别。

## Migration Plan

一步落地。回归关键点：session-invalid.spec 的踢出用例必须仍绿（显式失效路径未动）；全量 e2e 建书 detached-DOM 类 0 命中；书架守卫用例上线即跑。

## Decisions（apply 期增补）

6. **LoginPage 自动登录反弹熔断**：守卫用例首跑实测「自动登录写回凭据（check-auth 桩 code 0）↔ 业务端点真 401 踢出」互踢成环，1514 请求/3 秒（每圈 5 请求 ~100 圈/秒），直接违背本 change 规格「失效处理不循环」场景。修复：api.ts 401 踢出时记 `sessionStorage.last_auth_kick_at`，LoginPage 自动登录 3 秒内跳过（停留手动登录页）。真实用户受益：任何踢出后 3 秒内不再自动重登，循环物理上不可持续。

## Open Questions

（无）
