# c-session-flip-stability

## Why

C端 e2e 实测发现「会话翻转→整树重挂」病灶：e2e 注入的会话是半真的（用户已注册、pc_hash 未在 S端 配对），后端校验面（verify/config/devices）随时返回拒绝 → `api.ts` 401 拦截器清凭据+踢 `/login` → `ClientShell` 按 `isLoggedIn()` 分支切换导致**整棵壳层子树重挂**（更新提示条/到期提示条/状态条/路由全部卸载重建、各自重打启动请求）。实测健康加载 ~5 请求/3 秒，翻转态 ~20/3 秒（最坏 2017/2.5 秒）；「新建作品」按钮在点击瞬间被重挂（element detached 反复重试），是 UI 建书又慢又脆的直接原因。真实用户同样受害：任何瞬时 401（如网络抖动后的单次失败）都会把正在编辑的页面踢回登录页。

## What Changes

- `api.ts` 两处 401 全局拦截器：对探测类请求（已有 `quiet` 机制）豁免「清凭据+踢登录」副作用；用户动作请求的 401 踢出行为不变。`useAuthHeal` 的显式失效信号（code 1 + session_invalid）踢出路径不受影响。
- `ClientShell`：登出分支改为渲染透传型权益上下文（不包装时子树身份不变），`isLoggedIn()` 翻转只增删上下文与路由内容，不再重挂更新提示条/到期提示条/状态条等壳层组件。
- e2e 守卫固化：新增「书架空闲期请求预算」用例（静止窗口内 `/api` 请求 ≤ 上限）钉死重挂风暴这一类回归；`createNovel` 辅助加点击前稳定等待作保险。
- 明确不做：不改 e2e 的半真会话手法（S端无 API 级设备配对端点，配对走浏览器 auth_url 流程，桩 check-auth 仍是必要手段）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities
- `frontend-auth-heal`: ① 认证失效踢出要求收窄——探测类（quiet）请求的 401 不再触发清凭据与导航，踢出口径收敛到「用户动作请求的 401」与「显式失效信号（useAuthHeal code 1 + session_invalid）」两条路径；② 新增壳层稳定性要求——会话状态翻转不得重挂互不相关的壳层组件（更新提示条/到期提示条/状态条）。

## Impact

- `client/frontend/src/lib/api.ts`：两处 401 分支加 quiet 豁免。
- `client/frontend/src/components/ClientShell.tsx` + `LicenseProvider`：登出分支透传渲染。
- `client/frontend/e2e/helpers.ts` + 新守卫 spec + 受影响 spec 的建书辅助。
- 用户可见变化：无视觉变更、无文案变更；行为变化=探测类瞬时 401 不再踢出登录（真实用户受益）。

## Design Impact

- 受影响端：仅 C端。受影响屏：全部已登录路由的壳层（行为级，无视觉差）。
- 不触两端共享段（base.css 令牌/基础组件类零改动），无需原型先行，设计工件由实现侧自查（本 proposal 即登记）。
- 无新增按钮/提示条/徽标，不涉语气词表与 §13 文案口径。
