# frontend-auth-heal Specification

## Purpose

C端 登录态的维护与呈现：本地凭据自愈、认证失效清理与回登录页，以及登录身份在界面上的可视（当前账号展示）。维护侧保证本地状态与服务端会话收敛且静默；呈现侧让用户随时可辨认当前登录的是哪个账号。

## Requirements

### Requirement: 应用启动自愈本地登录态

- The system SHALL provide a `useAuthHeal` hook that on mount issues a single `GET /auth/check-auth` request.
- When the response has `code === 0` and a non-empty token that is not `"dev-token"`, the hook SHALL write the returned token and username into `localStorage` (`auth_token`, `auth_username`).
- When the response indicates not logged in, or the request fails, the hook SHALL NOT clear or modify existing `localStorage` state and SHALL NOT throw or navigate.
- The hook SHALL be invoked once from the application shell (`ClientShell`) so it covers every route, not just `/login`.

#### Scenario: valid backend session heals frontend token
- Given `localStorage` has no `auth_token`, and `GET /auth/check-auth` returns `code: 0` with a valid token and username
- When `useAuthHeal` mounts
- Then `localStorage.auth_token` equals the returned token and `localStorage.auth_username` equals the returned username

#### Scenario: backend not logged in leaves frontend untouched
- Given `localStorage` already has some `auth_token`
- When `GET /auth/check-auth` returns `code: 1` (not logged in) and the hook mounts
- Then the existing `localStorage.auth_token` is unchanged

#### Scenario: network failure is silent
- Given `GET /auth/check-auth` rejects with a network error
- When `useAuthHeal` mounts
- Then no error escapes to the app and `localStorage` is unchanged

### Requirement: 认证失效时清理本地登录态并回到登录页

C 端在收到认证失效响应（会话过期、账号已注销等导致的服务端拒绝）时，SHALL 清空本地持久化的登录凭据（config.json 中的 JWT 与用户名）并导航回登录页；本地作品数据 MUST 原样保留，且失效处理 MUST NOT 触发循环请求或静默吞掉用户当前操作上下文——回到登录页时应能重新登录并恢复使用。

踢出副作用（清凭据+导航）仅对「用户动作请求的 401」与「useAuthHeal 显式失效信号（code 1 且 session_invalid）」两条路径生效；探测类请求（`quiet` 标志：启动探测、后台刷新、静默预取）收到 401 时 MUST NOT 清凭据、MUST NOT 触发导航，仅按各自的静默降级逻辑呈现状态。

#### Scenario: 注销导致的会话失效回到登录页

- **WHEN** 用户账号已在服务端完成注销，客户端携带原 JWT 发起请求并收到认证失效响应
- **THEN** 客户端清空 config.json 中的 JWT 与用户名，导航回登录页，本地作品数据不受影响

#### Scenario: 失效后重新登录恢复正常使用

- **WHEN** 会话失效处理完成、客户端回到登录页后，用户以有效账号重新登录
- **THEN** 客户端写入新凭据并正常进入工作台，不残留失效会话导致的异常状态

#### Scenario: 探测类 401 不踢出

- **WHEN** 启动探测/后台刷新类请求（quiet）收到 HTTP 401
- **THEN** localStorage 登录凭据原样保留，页面不发生导航，无全局错误 toast

#### Scenario: 用户动作 401 仍踢出

- **WHEN** 用户主动操作触发的业务请求收到 HTTP 401（会话确已失效）
- **THEN** 清凭据并导航回登录页，行为与既有口径一致；本地作品数据保留

#### Scenario: 显式失效信号仍踢出

- **WHEN** useAuthHeal 收到 code 1 且 session_invalid 的失效信号
- **THEN** 清凭据、持久化提示并回登录页，行为与既有口径一致

#### Scenario: 失效处理不循环

- **WHEN** 上述任一路径反复返回失效响应
- **THEN** 不得形成请求循环（同一会话内踢出动作至多一次，无重挂风暴连环请求）

### Requirement: 壳层会话翻转不重挂无关组件

`ClientShell` 的登录态翻转（`isLoggedIn` 变化）SHALL 仅切换权益上下文与路由内容；更新提示条、到期提示条、状态条等壳层常驻组件 MUST NOT 因翻转被卸载重挂，MUST NOT 在无真实路由变化时重复发起各自的挂载请求（更新检测、到期检测等）。

#### Scenario: 翻转不重挂壳层组件

- **WHEN** 登录态在会话存续期间发生一次翻转（如凭据写入或清除）
- **THEN** 更新提示条/到期提示条/状态条组件实例保持挂载（各自挂载请求不重复触发），仅权益上下文与路由区域按新状态渲染

#### Scenario: 书架空闲期请求预算

- **WHEN** 书架页完成加载后进入静止 3 秒
- **THEN** 该窗口内 `/api` 请求总数 ≤ 8（e2e 守卫用例固化此口径）

### Requirement: 控制中心面板账号区头展示当前账号

已登录用户打开控制中心面板时，账号区头 SHALL 同时展示当前用户名与套餐完整档文案，格式「{用户名} · {套餐文案}」；用户名 SHALL 取自本地既有登录态字段，MUST NOT 为展示新增后端请求。用户名超长时 MUST 以省略号截断且不撑破布局，悬停 MUST 可见完整用户名。本地无用户名时 MUST NOT 硬造用户名，仅展示套餐文案且头像退化为通用人形图标。用户名 MUST NOT 脱敏。

#### Scenario: 面板账号区头用户名与套餐同屏

- **WHEN** 已登录用户（本地用户名 `writer01`）打开控制中心面板
- **THEN** 账号区头同时显示「writer01」与套餐完整档文案（如「writer01 · PRO 会员」）

#### Scenario: 长用户名截断且悬停可见全文

- **WHEN** 用户名为 40 字符时打开控制中心面板
- **THEN** 用户名以省略号截断、不撑破布局，悬停该文本可见完整用户名

#### Scenario: 防御态不硬造用户名

- **WHEN** 本地登录态无用户名（校验失败防御态）时呈现账号区头
- **THEN** 仅显示套餐文案，头像为人形图标，不出现占位或伪造的用户名

### Requirement: 认证失效处理必须经统一出口

C端 全部请求路径（中心请求栈、配置域、导入解析、AI 请求）收到认证失效时，SHALL 经同一出口执行踢出副作用（清凭据 + 写反弹熔断时间戳 + 导航回登录页），SHALL NOT 存在绕过该出口自行处理的路径；探测类请求（quiet）仍按既有口径不踢出。统一出口 SHALL 保持至多一次踢出的防循环语义。

#### Scenario: 配置域请求 401 与主栈同行为

- **WHEN** API Key 列表请求（配置域）收到 401
- **THEN** 清凭据并导航回登录页，行为与主栈用户动作请求一致；不出现「HTTP 401」原始状态码文案

#### Scenario: 导入解析 401 写熔断时间戳

- **WHEN** 导入解析请求收到 401 并触发踢出
- **THEN** 反弹熔断时间戳被写入（与主栈同口径），登录页自动登录反弹熔断按既有语义生效

#### Scenario: AI 请求 401 走统一出口

- **WHEN** AI 去AI味/扩写类请求（非流式）收到 401
- **THEN** 清凭据并回登录页，不停留在原页只报一条错误文案

#### Scenario: 探测类 401 仍不踢出

- **WHEN** 启动探测/后台刷新（quiet）收到 401
- **THEN** 凭据保留、无导航（与既有口径一致）
