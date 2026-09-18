## Why

2026-09-18 对 S端 做了一次全量安全审计（本地起服务实测复现，证据链完整），发现 2 个严重、
4 个高危与一批中低危问题。最严重的两条：①PostgREST 过滤器构造把用户可控值当查询指令透传，
未登录一条 `GET /api/check-auth?pc_hash=neq.x` 即可取得任意用户的 30 天 JWT（等于全站账号接管）；
②登录限流按字面路径匹配，而网关剥 `/api` 前缀的形态（`/web/login`）不限流仍能打到登录逻辑，
唯一的口令防爆破防线实测可完全绕过。这些问题只存在于 pg_http 后端（生产），本地 sqlite 栈测不出来，
必须立项一次收掉。全部安全问题收进本 change，任务按严重程度排序执行。

## What Changes

按严重程度分组（与 todo.md「S端 安全」一节一一对应）：

- **P0 查询过滤器注入**：`PgRestClient._build_params` 的操作符隐式透传改为显式声明
  （`RawFilter` 包装类型，仅内部构造允许），**替换范围=全部服务端构造的操作符表达式**
  （含 `f"eq.{...}"`、`"eq.active"`、`in.(...)`、`not.is.null`、`gt.<ts>` 等，实测 36 处；
  漏改会让档位/退货/注销查询静默查空）；用户可控值一律按字面值处理。入口层对身份/业务标识参数
  做**危险形态拦截**（操作符 token 开头或含 `,()` 引号 → 拒绝），新注册用户名另加形态白名单。
  本条同时覆盖两条致命利用链：①`GET /api/check-auth?pc_hash=neq.x` 未登录取得他人 30 天 JWT；
  ②`/api/reset_password` 的 username 注入——读一行、写多行，**一次提交可批量重置全站密码**
  （此链比①更严重，P0 用例必须两条都覆盖）。
- **P0 限流绕过**：`RateLimitMiddleware` 改为在路径归一化之后判定（剥前缀形态与带前缀形态同桶计数）；
  敏感路径清单扩展：`/api/web/register`、`/api/reset_password`、`/api/user/password`、
  `/api/user/deletion/revoke`。
- **P1 密钥门禁**：按后端形态分级——`DB_BACKEND=pg_http`（生产）时 JWT_SECRET / ADMIN_TOKEN 为空、
  为出厂默认值或长度不足即**拒绝启动**并列明原因，`PAYMENTS_GATEWAY` 空串不再回落 mock
  （生产必须显式配置，mock 需 `PAYMENTS_GATEWAY=mock` + `PAYMENTS_ALLOW_MOCK=1` 双开关）；
  sqlite 本地形态保持零配置可用（仅告警）——**分级是刻意的**：本地 docker 栈、pytest、
  dev-up 全走 sqlite，一律强制会把它们全部打死。部署链同批加"部署前断言密钥/网关非空"。
  **BREAKING**（生产配置缺失即拒绝启动，属有意为之）。
- **P1 激活越权**：`POST /api/pay/codes/activate` 增加订单属主校验（订单不属于当前登录用户 → 按订单不存在处理）。
- **P1 设备配对改挑战-应答**：C端 首次运行生成 ≥256 位本机配对密钥（仅存本地、绝不经 URL/日志
  传输），其哈希（challenge，64 位小写 hex）随授权页 URL 提交并落库到设备授权记录；
  `GET /api/check-auth` 不再返回 30 天 JWT，只返回套餐刷新数据；新增 `POST /api/pair/exchange`
  （pc_hash + 配对密钥，恒定时间比对 challenge）换取 token。仅知 pc_hash（硬件序列号派生、可推导）
  拿不到令牌。**硬约束**：C端 **本机后端**对前端的 check-auth 响应形状必须保持带 token
  （由本机后端在轮询内完成交换后注入）——C端 前端因此零改动。
  **BREAKING**（S端 check-auth 契约变化：**硬切**——存量记录一并停发 token。**产品当前无用户
  （2026-09-18 确认）→ 过渡机制整体取消**：不做双模、C端 不做旧 S端 兼容回落、S端/C端 发布顺序
  不设约束；唯一保留的兜底=授权页对 challenge 缺失的**版本错配提示**，防用户下载到发布页/CDN 上的
  旧安装包后卡在授权页——出口=升级提示 + 下载链接）。
- **P1 关闭生产 API 文档端点**：`/docs`、`/redoc`、`/openapi.json` 默认不注册（env 可显式打开供本地调试）。
- **P2 密码存储升级**：口令哈希迁 bcrypt（自带随机盐），历史 PBKDF2 哈希在登录成功时无感升级；
  比较改恒定时间；密保答案入库前归一化（去首尾空白、转小写）。
- **P2 会话撤销**：`users` 表新增 `token_version`，签发 JWT 携带该值，鉴权时比对（无版本声明按 0，
  存量令牌不误伤）；改密码、改密保、账号锁定、注销执行时自增，存量会话即刻作废；
  移除单设备**不**自增（只解绑该设备，不波及其他已登录端）。
- **P3 加固项**：微信回调验签失败背压（独立计数桶、SIGNTEST 探测豁免；来源键不可信时降级为
  高阈值告警不阻断，防被用来封微信出口）＋可选来源白名单（env，默认关闭保持兼容，解析失败即拒启）；
  CORS 收敛为显式白名单（env，默认空=仅同源；**须显式列入 www 与静态托管默认域**，否则经默认域
  直访门户会挂）；门户安全响应头（docker 形态由 nginx 提供；生产静态托管形态以平台能力为限，
  验证后登记结论）；运行日志不再输出凭据片段（env 指纹去掉 tail4，CI 侧三处同批）；
  本地 `server/secrets/*.pem` 权限收紧 600；排查 `client/packaging/cert/cert.pfx`
  是否含私钥口令（属 C端 范围，仅登记结论）。

## Capabilities

### New Capabilities

- `s-query-filter-safety`: S端 PostgREST 查询过滤器构造安全——操作符透传必须显式声明、
  用户可控值按字面值处理、身份/业务标识参数入口格式白名单。
- `s-security-baseline`: S端 服务加固基线——生产密钥强度门禁（fail-fast）、mock 网关显式开关、
  API 文档端点默认关闭、口令哈希与密保答案存储策略、会话撤销（token_version）、
  CORS 白名单与安全响应头、诊断日志凭据卫生。

### Modified Capabilities

- `s-api-ratelimit`: 限流匹配语义改为「路径归一化之后判定」（剥前缀形态与带前缀形态同桶）；
  敏感路径清单扩展至注册/找回密码/改密码/注销受理/撤销注销/配对交换。
- `s-payments`: 激活动作增加属主校验——激活请求只能操作当前登录用户自己的订单。
- `wechat-pay-gateway`: 回调端点增加验签失败背压与可选来源白名单（默认关闭）。
- `device-auth-page`: 设备授权与轮询契约改为挑战-应答配对——check-auth 不再携带 token、
  新增 pair/exchange 端点、授权请求携带 challenge（本机配对密钥哈希）、S端 /auth 页同批适配。

## Impact

- **代码**：`server/app/infrastructure/repositories/pg_http/client.py`（过滤器构造）、
  `server/app/interfaces/middleware.py`（限流）、`server/app/config.py` + `server/app/main.py`
  （密钥门禁/文档端点/mock 开关）、`server/app/application/payments/activate_code.py`（属主校验）、
  `server/app/interfaces/client_api/authorize.py` + 新增 pair 路由（挑战-应答配对）、
  `server/app/infrastructure/security/password.py`（bcrypt 迁移）、
  `server/app/infrastructure/security/jwt.py` + `server/app/interfaces/deps.py`（token_version）、
  `server/app/infrastructure/notify.py` 所在回调链、`server/frontend/nginx.conf`（P3，仅 docker 形态）、
  `server/frontend/src/views/AuthPage.vue` + `RegisterPage.vue` + `src/api/client.ts`（challenge 透传与
  两处文案）、`client/backend/auth_local/service.py` + `auth_local/router.py`（配对与 token 交换；
  C端 前端 `client/frontend` 零改动）。
- **同批必改的配套文件**（漏一处即本地栈/CI 起不来或全量红，见 tasks）：`server/tests/conftest.py`
  （限流阈值 + 在 import app 前注入）、`server/tests/unit/test_config.py`、
  `server/tests/unit/test_pg_http_repos.py`、`server/tests/test_web_api.py`、
  `server/tests/test_device_activation.py`、`server/tests/contract/*`、
  `server/frontend/e2e/mocks/api-handlers.ts`、`server/frontend/e2e/tests/auth-page.spec.ts` +
  `beian.spec.ts`、`client/backend/tests/test_entitlement_sync.py` + `test_auth_url.py`。
- **数据**：`users` 表加 `token_version` 列（alembic 迁移 + pg_http 侧 DDL，走 pg-schema 门禁）；
  `device_grants` 表加 `challenge` 列（同批 DDL）；口令哈希沿用标准 `$2b$` 格式（`startswith("$2")`
  分派新算法、其余走历史 PBKDF2 兼容路径，零自造格式）。
- **测试**：`server/tests/` 新增安全回归（注入两条利用链、限流绕过、越权用例、空密钥拒启用例、
  配对成功/失败/轮换用例、哈希迁移用例）；同批更新会被打红的既有用例清单见 tasks 6.3/10.1；
  `server/frontend/e2e`（auth-page 五处 /auth URL + beian 一处需补 challenge、mock 需校验 challenge
  与新增 pair/exchange 路由）；`client/backend/tests`（无 token 字段 → 走 exchange 的新分支）。
- **部署**：`s-server-deploy.yml` 增加部署前断言（`PAYMENTS_GATEWAY` 非空、`JWT_SECRET` ≥32、
  `ADMIN_TOKEN` ≥16，不满足 exit 1 并列变量名）并更新既有注释语义（"空串回落 mock"已废除）；
  生产 secrets 已配齐（2026-08-15 起在库），门禁上线不影响现网启动；
  check-auth 契约变化为**硬切**：产品当前无用户（2026-09-18 确认），发布顺序不设约束、无需通告，
  未升级客户端不存在；发布说明指引从发布页下载最新版 C端。

## Design Impact

- 受影响端：S端 后端 + S端 门户（两处纯文案/提示）；C端 仅本机后端 `client/backend/auth_local/`
  逻辑适配，**C端 前端零改动**（硬约束：本机 check-auth 响应保持带 token，见 proposal What Changes）。
- 界面/弹层：无布局、无组件、无令牌变化，但**并非"零界面改动"**——新增两处可见文案：
  ①S端 授权页 challenge 缺失/不合法时的兜底提示（复用既有 `notice warn` 形态 + 可点击出口，
  口径指向"升级桌面应用"）；②S端 注册页用户名列 hint（design-language §13 要求上限可见、
  不藏在报错里）。两处均由实现侧按既有组件与文案口径产出。
- 对象状态：无新增或变化（对照状态语言总表：仅复用既有 warn 语气）。
- 两端共享段：不触碰（`@cross` 段、base.css 令牌、语义类家族零改动）。
- 原型先行：不需要（纯 S端 文案 + C端 本机后端逻辑；S端 无像素基线）。
- 设计工件：实现侧自查即可，无需设计侧会话。
