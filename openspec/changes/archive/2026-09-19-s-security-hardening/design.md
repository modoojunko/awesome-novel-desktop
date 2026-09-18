## Context

S端 生产形态 = CloudBase 云托管容器跑 FastAPI，数据面走 PostgREST HTTP API（`DB_BACKEND=pg_http`，
service_role API Key 绕过 RLS）；本地开发/e2e = sqlite + SQLAlchemy。仓储层为双实现
（`repositories/pg_http/*` 与 `repositories/sql/*`），**同一安全语义必须在双实现下等价**
——本 change 的多项修复在 sqlite 侧"天然安全"，因此本地测试无法自动暴露 pg_http 侧问题。

审计复现记录（2026-09-18，证据在 todo.md「S端 安全」节）：`_build_params` 操作符透传
（`pg_http/client.py:267-287`）导致 check-auth 未登录泄 token 与 reset_password 批量改密两条链；
限流按字面路径匹配且先于归一化执行（实测 `/web/login` 35 次全 200）；空环境变量 fail-open
（空密钥伪造 JWT 通过、空 ADMIN_TOKEN 免鉴权调 admin 与 dev 注入端点）；
`activate_code` 缺属主校验；check-auth 直发 30 天 JWT 而 pc_hash 可推导；FastAPI 默认文档端点公开。

**立项后经前后端双评审复核，本文件已按代码实况修订**（下列 D 段标注了被推翻的原判断）。
评审核对出的关键事实（均有 file:line 证据）：

- 操作符字面值共 **36 处**，多数是显式 `f"eq.{...}"`/`"eq.active"` 形态——只改 `in.(...)` 一类
  会让档位查询、退货收回、注销 CAS 静默查空/400（`code_repo.py:118,127,…`、`user_repo.py:90,104,…`、
  `payments_repo.py:62,82,102,130,182,233,442`）。
- `PAYMENTS_GATEWAY` 若一律强制显式，会同时打死 `docker-compose.yml`（server-backend 用 sqlite、
  未设该变量）、`server/tests/conftest.py`（`with TestClient(app)` 会跑 startup）、
  `scripts/dev-up.sh` native 分支、CI `server-backend-ci.yml`。
- 全仓唯一 XFF 写入点是反代的 `$proxy_add_x_forwarded_for`（**追加**语义，客户端自带值留在最左），
  vite 代理未开 `xfwd` → 取 XFF 最左段等于把限流键交给攻击者。
- `get_current_user` 是死代码（无调用点）；web 面实际用 `get_current_user_or_none`（不查库）与
  `payments.py::_current_identity`（不查库）；**C端 全仓不调用 S端 `/api/verify`**，
  `verify_session()` 纯本地（`client/backend/auth_local/service.py:457-496`）。
- `passlib[bcrypt]==1.7.4` + `bcrypt==4.2.1` 已在 `server/requirements.txt`（无需新增依赖，
  但 passlib 与 bcrypt≥4.1 会打版本噪音日志）；`bcrypt.checkpw` 遇空哈希/非法哈希抛 `ValueError`。
- C端 首次授权的轮询在 **C端 前端** `LoginPage.tsx:125-131`（60×2s，打本机 check-auth），
  `service.py:383` 是 `cfg["token"] = data["token"]` 直接下标（S端 停发 token 即 KeyError → 500
  → 用户界面表现"授权超时"）。

## Goals / Non-Goals

**Goals:**

- 关闭两条实测可达的接管/爆破路径，并以规格固化防回归。
- 一切"生产配置不对"的场景 fail-closed：拒绝启动优于带病运行；本地形态零配置可用。
- 令牌可获得性从「知道 pc_hash」提升为「持有本机 256 位随机密钥」。
- 会话可撤销（存量令牌不被误伤），密码存储升级且用户零感知。
- 安全回归双后端落地，防"本地测不出生产洞"复发。

**Non-Goals:**

- 不做 Web 端 logout 服务端吊销列表（版本化撤销已覆盖主要场景）。
- 不实现账号失败锁定自动化（限流 + 恒定时间比较覆盖爆破面；锁定仍人工/运维）。
- 不给 C端 新增"配对失效"专用 UI（复用既有 session_invalid 通道）。
- 不动微信支付验签/金额/幂等核心逻辑（审计确认已正确）；只加外围背压。
- 不处置 `client/packaging/cert/cert.pfx`（仅排查登记，属 C端 范围）。
- 不做 HSTS/CSP（终止在托管网关；CSP 需排查内联脚本，另行立项）。

## Decisions

### D1 过滤器安全：显式声明替代文本形态识别（原判断已修正）

`_build_params` 增加包装类型 `RawFilter(str)`：**先判 `isinstance(value, RawFilter)` 再判 `str`**
（顺序颠倒=未修或双前缀）。裸字符串一律 `eq.<值>` 字面处理；**替换范围=全部服务端构造的操作符
表达式，含显式 `eq.` 前缀**（36 处：pg_http 四仓储 + payments_repo + cas.py）。落地配一条 grep 门禁：
`server/app/infrastructure/repositories` 下不得再出现未包装的 `"eq.` / `f"eq.` / `in.(` / `is.null` /
`not.is` / `gt.` / `lte.` 字面值。`select/order/limit/offset` 现状全为内部常量，规格补一条
"不得接收请求输入"防未来回归。`RawFilter` 只允许包常量/库内值，禁止包请求输入。

入口危险形态拦截实现为 FastAPI 依赖，**分档**：受拦截参数（订单号/激活码/设备码/SKU/新注册用户名）
命中危险形态 → 拒绝；**用户名在登录/改密/注销/授权等既有账号路径上不拦截**（存量用户名零约束，
拦截会锁人；修复后这些名字本可正常使用）。拒绝响应 MUST 为 `{code,msg}` 信封
（HTTP 200 业务码或 4xx + 同信封 body）——`HTTPException(detail=...)` 会被门户拦截器显示成
"服务器错误"（`request.ts:96` 只读 `data.msg`），spec 里"提示合法形态"也就不可达。

**替代方案**：只加入口白名单不改仓储层——新增端点易漏，且拦不住已存在的 36 处内部值；两层都做。

### D2 真实标识形态（写死正则前以此为准）

- 订单号：`S{YYYYMMDD}-{16 位大写 hex}`，26 字符（`domain/payments/pricing.py:97-106`）。
- 激活码三形态：`O-{订单号}`（28）、`TRIAL-{8 位大写 hex}`（14）、`AC-XXXX-XXXX-XXXX-XXXX`（22）
  （`fulfill_payment.py:74`、`register_user.py:40`、`admin_api/codes.py:32-34`）。
- 设备码：C端 生成 32 位小写 hex，但**存量数据/测试夹具存在非 hex 值**（`hash-103` 等），
  且门户预热发空串（`request.ts:119-134`）→ 只做危险形态拦截、空串放行，禁用 hex 白名单。
- SKU 标识：库配置文本，只做危险形态拦截。

### D3 限流：归一化后判定 + 可信来源键（原 XFF 判断已推翻）

中间件修正（**实施期按实测校正**）= **限流器内部两形态归一**：`_sensitive_path(path)` 对
"带前缀命中"或"剥前缀 + `/api` 命中"同判——与中间件嵌套顺序解耦、版本无关。
原设计写的"反向排列 add_middleware"在本仓 venv（Starlette 1.6.0 + 当前 FastAPI）实测**不成立**：
`app.user_middleware` 的实际嵌套顺序与该假设不符（反向排列后行为不变、访问日志仍打印原始路径），
故弃用该机制；`register_middleware` 维持历史顺序（访问日志在最外层，429 照常可见）。
红绿实证：模拟修复前（去掉两形态归一）两条方向用例全红（200），恢复后全绿。

来源键：**默认不信任 XFF**（`TRUSTED_PROXY_HOPS=0` → 回落 `client.host`，与今天行为一致）；
仅当显式配置跳数时取 `XFF.split(",")[-hops]`（最近可信代理注入的那一跳），解析失败回落。
上线前加临时日志同时打 `client.host`/完整 XFF 链/派生键，实测云托管网关行为后（写进 tasks 证据）
再决定是否开启跳数。**取最左段是错的**：nginx 用 `$proxy_add_x_forwarded_for` 追加，最左可伪造 →
轮换该头即轮换限流桶。限流器 history 加定期清理。

清单扩展（含归一化形态）与 pytest 连带：清单加 `/api/user/deletion`、`/api/pair/exchange` 等后，
`server/tests/conftest.py` 必须在 `import app` **之前**注入 `RATE_LIMIT_LOGIN_PER_MIN=2000`
（`LIMIT` 在类定义期求值），否则单次 pytest 的注册/登录/授权总量必超阈值 → 大面积 429 假失败。

### D4 密钥门禁：按 DB_BACKEND 分级（原"一律拒启"已修正）

`pg_http`（生产）：JWT_SECRET（非空/非默认/≥32）、ADMIN_TOKEN（非空/非默认/≥16）、
PAYMENTS_GATEWAY（缺省或空串即拒启；mock 需 + `PAYMENTS_ALLOW_MOCK=1`）全部 fail-fast，
错误信息列明不合格变量（不回显值）。`sqlite`（本地/CI/docker/pytest）：维持"缺省即 mock + 弱密钥仅告警"，
**本地栈与 CI 零配置改动**。`dev_inject._check_admin` 改为 `if not ADMIN_TOKEN: return False`（现行
`token == ADMIN_TOKEN` 在空串下等价放行）。部署链同批：`s-server-deploy.yml` 增"部署前断言
PAYMENTS_GATEWAY 非空 + JWT_SECRET≥32 + ADMIN_TOKEN≥16"步骤（不满足 exit 1 并列变量名），
并更新 46-48 行"空串回落 mock"的注释语义；`server/tests/unit/test_config.py` 的 mock 缺省断言同步改写。

### D5 设备配对：挑战-应答（PKCE 形态）

一次性短码方案已否决（短码在轮询响应里，知道 pc_hash 者自取自换，等于没防）。定案：

- C端 首次运行生成 `device_secret = secrets.token_urlsafe(32)`（32 字节 = 256 位熵），存 `config.json`，
  绝不出现在 URL/日志/轮询响应；`challenge = sha256(device_secret).hexdigest()`（64 位小写 hex）
  随授权页 URL 与授权请求提交。
- `device_grants` 加 `challenge` 列；落点（全清单）：`domain/devices/device.py` 的 DeviceGrant、
  `repositories/base.py` 抽象、sql/pg_http 两个 `upsert`（**新参数必须带默认值且 keyword-only**
  ——`tests/unit/test_pg_http_repos.py:349` 用位置传参）、`authorize_device.py`、`models/grant.py`、
  alembic 新版本、`pg_schema.py` 自检清单。
- `GET /api/check-auth` 只回刷新数据；新增 `POST /api/pair/exchange`（client_api 路由族；
  `SENSITIVE_PATHS` 记归一化形态 `/api/pair/exchange`），恒定时间比对，NULL challenge 一律失败；
  重新授权覆盖 challenge。
- **C端 本机契约（硬约束）**：本机后端对 C端 前端的 check-auth 响应形状保持不变（code 0 带 token）——
  在**轮询链路内**完成 exchange 并注入 token（新机器无本地 token 时也能一次授权进主界面）；
  `service.py:383` 的 `data["token"]` 直接下标改为"有则取、无则保留本地"；exchange 401/429 不得清凭据，
  429 按可重试；exchange 加调用闸门（仅本地无 token / 已判失效时调用），避免与路由切换刷新叠加撞限流。
- 过渡策略（**用户 2026-09-18 拍板：B 硬切；同日确认"当前没有用户"→ 过渡机制整体取消**）：
  硬切——S端 上线即停发令牌，含 `challenge IS NULL` 的存量记录一并不再返回 token。
  **因无存量用户，下列过渡件全部不做**：双模分支、C端 "对旧 S端 回落读 token" 的兼容路径、
  S端/C端 发布顺序约束、客服通告、存量令牌自然过期的窗口管理。唯一保留的兜底=**授权页版本错配提示**
  （challenge 缺失 → "请升级桌面应用 + 下载出口"）：发布页/国内 CDN 上仍挂着旧安装包，用户装到旧版
  会在授权页卡死，提示即出口。
  备查（若将来二次评估，两者的准确差别）：存量 grant 存的是授权当时签发的令牌（check-auth 只回原
  令牌、不续签），A 的暴露窗口=每张存量令牌的剩余寿命（≤30 天）且期间发放口持续可用；B 立即关闭。
  两者收敛路径相同（到期后一次浏览器重新授权），差别只在窗口长度与静默刷新是否退化。
- 原判断修正：C端 的轮询在前端 `LoginPage.tsx`（`service.py` 的 `POLL_INTERVAL/POLL_TIMEOUT` 是死常量）；
  C端 不调 `/api/verify`，故 **exchange 同时承担 token 刷新通道**（本地 token 失效时换新），
  D7 里"走 /api/verify 比对版本"的表述作废。
- 界面：**并非零界面改动**——授权页新增 challenge 缺失/不合法兜底提示（复用 `notice warn` + 可点击
  出口，口径"升级桌面应用"，硬切后旧 C端 的**任何新授权**都会命中，不只首次）；注册页加用户名列
  hint（§13）。

### D6 密码哈希：bcrypt + 登录时无感升级（原表述已修正）

用 `bcrypt` 模块**直接调用**（已在 requirements；passlib 1.7.4 + bcrypt≥4.1 会打版本噪音），
存标准 `$2b$` 格式（列宽 256 足够），`startswith("$2")` 分派新算法、其余走历史 PBKDF2 兼容验证，
成功即改写（惰性迁移）。**fail-closed**：`if not hashed: return False` + `try/except ValueError: return False`
（历史空哈希、测试种子 `"*"` 都不得冒泡 500）。**72 字节策略**：注册/改密/重置统一显式限制并给可读
错误（bcrypt 静默截断会让 100 字符与 72 字符等价）。密保答案归一化后走同一通道，历史空答案维持
"未设置=必失败"。惰性升级写库路径确认：sqlite 走请求级 `db.commit()`（`models/base.py:32-45`，
login 端点在该依赖下），pg_http 即时 PATCH。**文档口径纪律**：不得宣称"迁移即消除风险"——
升级发生在登录成功时，未登录用户的旧全局盐哈希在窗口内仍可离线爆破。

### D7 会话撤销：users.token_version（原三条前提已修正）

- 领域/模型/仓储：`User.token_version`（默认 0）双实现 `_to_domain` + `models/user.py`
  `server_default="0"`；alembic + pg_http DDL + pg_schema 自检清单。
- 签发：`sign_jwt(username, uid, ver=0)` 默认参（不破 `sign_jwt("x", 999)` 类既有调用），
  login/register/authorize 三处带真实版本。
- 校验：**`payload.get("ver", 0)` 与列值比对**（缺声明视作 0 → 存量令牌不被误伤，规避全站强登）。
  免费落点=已取 user 的端点（user/me、user/password、user/deletion*、verify）；需新增 1 次查库的端点
  （devices/*、pay/*）用 **uid → token_version 的 60 秒 TTL 缓存**（沿用 TierRepo 缓存范式，
  撤销最迟 60 秒生效）——比"只读 GET 不比对"更完整，比每请求直查更省往返。
- 自增四点：改密、改密保（同一 PATCH 带 `token_version: 当前值+1`，零额外代价）、锁定、注销执行。
  注销执行里 `mark_deleted` 是 PostgREST CAS（不支持 `col = col + 1`）→ 写**固定哨兵值 1**
  （该行终态不可复活、uid 不复用，等价且单语句）。"锁定"现状无代码路径（仅人工 SQL）→ 规格按
  "鉴权依赖顺带拒绝 `status=='locked'`"实现（行已取到，零成本，不依赖有人记得 +1）。
- **设备授权令牌（C端 配对所得）不受本机制管辖**（失效靠 grant 删除/覆盖：注销执行、移除设备、
  重新授权）；C端 侧的"令牌被版本作废"由 exchange 刷新自然覆盖。
- 前端影响入发布说明：改密成功即当前浏览器也被登出（`request.ts:61-65` 401 → /login），属有意行为。

### D8 回调背压：独立桶 + 来源可信才阻断（原"复用限流原语"已修正）

现有 `RateLimitMiddleware` 是"进前预检"，无法感知验签结果 → 背压需"先查暂封 → 调 handler →
按结果计数"，**独立计数桶**（复用计数器类，不复用 `_history`，否则 notify 失败吃掉登录配额）。
SIGNTEST 探测（`notify.py:54-55`）豁免计数。阈值 10 次/60 秒（微信单笔重试节奏 15s/15s/30s/3m…
远低于阈值，不误伤）。**来源键不可信时只告警不阻断**（D3 的 `TRUSTED_PROXY_HOPS=0` 默认下即此态）。
白名单 `WXPAY_NOTIFY_ALLOWLIST` 解析失败 → 拒启（fail-fast）。失败达阈值 SHALL 走既有
`NotifyService` 告警（避免"验签配置错误"这类真故障被 429 掩盖）。429 ≤ 官方语义"失败重试"，兼容。

### D9 CORS 与响应头（范围已修正）

`CORS_ALLOW_ORIGINS`（逗号分隔）。默认空=不允许浏览器跨域——本仓浏览器调用全部同源：S端 门户走
统一域名 `/api` 分流、本地 docker 走门户 nginx 反代、dev/e2e 走 vite proxy、C端 桌面端只经本机
后端 server-to-server。**但生产 MUST 显式列入**：①统一域名 www；②静态托管默认域
（`novel-s-web-*.webapps.tcloudbase.com`，否则经默认域直访门户登录/注册全挂）。S端 e2e 全 mock
（`e2e/fixtures.ts`）→ 不能拿它当 CORS 安全证据，验证走手工 `curl -H Origin` 与真实栈。
安全响应头 `X-Content-Type-Options/X-Frame-Options/Referrer-Policy` 加在 `server/frontend/nginx.conf`
——**仅 docker 形态生效**；生产是静态托管（`tcb app deploy`），不经该 nginx → tasks 增"验证托管
平台是否支持自定义响应头并登记结论"。日志卫生：`main.py:114-118` 去 tail4；CI 侧
`s-server-deploy.yml:92,101,143` 与 `secret-fingerprint.yml:17` 同批去 tail4。

### D10 测试策略：安全回归双后端 + 连带用例同批改

新增 `server/tests/test_security_regression.py`（注入两条链、限流绕过、越权激活、空密钥拒启、
配对成功/失败/轮换、哈希迁移；pg_http 侧用 MockTransport 断言**出站过滤形态**）。
**被打红必须同批更新**（评审已逐一核出）：`tests/unit/test_pg_http_repos.py`（`eq.`/`in.(` 透传断言、
upsert 位置参数）、`tests/unit/test_config.py`（mock 缺省三条）、`tests/test_web_api.py`
（authorize 无 challenge、check-auth 取 token）、`tests/test_device_activation.py`（fixture 的
pc_hash 非 hex）、`tests/test_account_deletion.py`、`tests/contract/*`、
`server/frontend/e2e/mocks/api-handlers.ts`（authorize 校验 challenge、register 白名单分支、
check-auth 双形态、路由表补 `**/api/pair/exchange`）、`e2e/tests/auth-page.spec.ts`（5 处 URL）+
`beian.spec.ts:51`、`client/backend/tests/test_entitlement_sync.py` + `test_auth_url.py`。

## Risks / Trade-offs

- [check-auth 契约硬切] 理论上会让"不匹配的旧客户端"静默刷新失效 → **当前无用户，实际命中面为零**；
  唯一现实路径=用户从发布页/国内 CDN 下载到旧安装包 → 由授权页版本错配提示（升级 + 下载出口）承接；
  发布说明指引下载最新版。
- [token_version 60 秒 TTL 缓存] 撤销最迟 60 秒生效 → 属可接受窗口（改密场景用户预期即时，
  缓存键与失效路径写在 tasks 里要求测试覆盖）。
- [bcrypt cost × 登录突发] 登录限流 30/min/IP 恰好约束总算力；cost 实测定档（Open Question）。
- [XFF 跳数误配] 配错 → 要么退回共享桶（更严）、要么信任可伪造段（更松）→ 默认 0（不信任）+ 实测后开启。
- [CORS 白名单漏列域名] 门户整体不可用 → 部署说明与 tasks 明确列出 www + 托管默认域，上线后手工验证两域名。
- [生产静态托管不支持自定义响应头] → 该场景降级为登记结论（spec 已按交付形态分档）。
- [双后端语义漂移] 入口拦截是双端共享统一防线；规格按"任一后端不得解释用户值为操作符"表述，
  sqlite 侧补一条等价回归。
- [连带用例遗漏导致"全绿"假象] → D10 的清单直接写进 tasks，先跑一次全量确认红清单再动手。

## Migration Plan

1. 合入后按严重度分批部署同一构建（无独立开关，回滚=回退镜像）。**P0 止血（注入/限流/越权/文档端点）
   与本段的配对改造解耦**：止血批可立即上线，不受下方发布顺序约束。部署前确认 GitHub secrets
   五件套在位（已在，2026-08-15 起）+ 新增部署前断言步骤先跑通。
2. **无存量用户（用户 2026-09-18 确认）→ 发布顺序不设约束**：S端 与 C端 可同批（或任意先后）发布，
   不做双模分支、不做旧 S端 兼容回落、不做通告；配对改造随本 change 一次到位。
3. pg_http DDL 先行：`users.token_version`、`device_grants.challenge`（可空默认 NULL/0，
   旧代码忽略之，回滚无需回滚 DDL），启动自检（pg-schema 门禁）护航。
4. S端 发布后观察 CLS：归一化与限流命中、check-auth 响应形态、notify 背压计数、
   新增的 XFF 探针日志（用于定 `TRUSTED_PROXY_HOPS`）；S端 e2e 与手工演练单各过一遍。
5. 授权页版本错配提示（升级 + 下载出口）随 S端 发布；发布说明指引下载最新版 C端。

## Open Questions

- bcrypt cost 取 12 还是 14：以本地 0.25C 容器实测登录 P95 定（≥300ms 则取 12）；不影响规格与拆分。
- `TRUSTED_PROXY_HOPS` 最终取值：待云托管网关 XFF 行为实测（tasks 3.4 的探针日志）后拍板。
