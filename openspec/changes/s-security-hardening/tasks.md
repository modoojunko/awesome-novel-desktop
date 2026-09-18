# Tasks — s-security-hardening

> 分组按严重程度排序（P0 → P1 → P2 → P3），组内按依赖排序。
> 每个任务完成时把验证证据（命令输出摘要/测试名/截图路径）追加在该 checkbox 下。
> 安全回归一律**先红后绿**：先写断言漏洞现场的用例跑红，再修复跑绿。
> 每批动手前先跑一次受影响端的全量测试，确认"会被打红"的既有用例清单与 design D10 一致。

## 1. 双端影响判定（前置）

- [x] 1.1 落判定记录 `notes-impact.md`：受影响端（S端 后端 + S端 门户两处文案 + C端 本机后端）、屏/弹层清单（AuthPage 兜底提示、RegisterPage 用户名 hint）、共享段=不触碰、原型=不需要、设计工件=实现侧自查。验证：文件存在且四项结论齐备。

## 2. P0-A 查询过滤器注入（specs/s-query-filter-safety）

- [x] 2.1 先红：新增 `server/tests/test_security_regression.py`——**两条利用链**：①`GET /api/check-auth?pc_hash=neq.x` 不得返回任何 token/他人数据；②`POST /api/reset_password` 以 `in.("自己","他人")`/`neq.nobody` 形态 username 不得读取他人密保哈希、不得改写任何行。pg_http 侧用 MockTransport 断言**出站过滤器形态**。当前全红。验证：红输出留档。
  → 红证据：三条用例均因出站过滤值被当指令而红（`device_grants?pc_hash=neq.anything`、`users?username=in.("me","victim")`、`users?username=neq.anything`）；端到端探针另证泄漏（`GET /api/check-auth?pc_hash=neq.anything` → 响应含 `"token":"JWT-OF-VICTIM"`，LEAKED_VICTIM_TOKEN: True）。
- [x] 2.2 `pg_http/client.py` 增 `RawFilter(str)`，`_build_params` **先判 RawFilter 再判 str**；裸字符串一律 `eq.<值>`。**替换范围=全部 36 处服务端构造的操作符表达式（含显式 `f"eq.{...}"`/`"eq.active"`）**：pg_http 四仓储 + `payments_repo.py` + `cas.py`（`compare_and_update` 的 `merged_filter` 一并核）。验证：2.1 全绿 + 新增用例断言裸串 `eq.active` → 出站 `eq.eq.active`、包装值 → 出站原样；`pytest server/tests` 全绿。
  → 落地口径：真操作符（in./is.null/not.is.null/gt./lte.）→ `RawFilter(...)` 显式包装；eq. 类标识值一律**去掉手写前缀走字面路径**（客户端补 eq.，出站形态逐字等价）。既有方言用例 2 条同批改（`test_pg_http_repos.py`）+ 新增裸串字面回归。`server/tests` 全量 **380 passed**。
- [x] 2.3 grep 门禁：`server/app/infrastructure/repositories` 下不得存在未包装的操作符字面值（`"eq.` / `f"eq.` / `in.(` / `is.null` / `not.is` / `gt.` / `lte.`）。验证：门禁命令输出为空（可加进 CI 或 tests 一条断言）。
  → 落地为 `test_no_unwrapped_operator_literals_in_repositories`（扫 app/infrastructure/repositories，client.py 本体除外）；当前零违规。
- [x] 2.4 入口危险形态拦截依赖：受拦截参数=订单号/激活码/设备码/SKU/新注册用户名（**用户名在登录/改密/注销/授权路径不拦截**）；**pc_hash 禁 hex 白名单、空串放行**；拒绝响应为 `{code,msg}` 信封。验证：新增用例（危险形态 → 可读 msg 而非"服务器错误"；`pc_hash=""` 与 `hash-103` 形态零回归；含点号/连字符合法用户名零回归）绿。
  → 新增 `app/interfaces/guards.py`（IdentifierRejected → errors.py 渲染 400+{code,msg}），已挂 15 条路由（authorize/check-auth/verify/devices×2/orders×8/codes.activate/refund-request）；护栏先于数据层拦截（用例断言危险形态不触达 device_grants）。
- [x] 2.5 新注册用户名白名单 `^[A-Za-z0-9_\-]{3,32}$`（仅 register；文案按 §13：3–32 位字母/数字/下划线/连字符）。验证：新注册拒绝用例 + 存量怪名登录用例绿。
  → `register_user` 增白名单 + 可读提示；conftest `web_user` 夹具同批消毒（uid 被参数化为 1.5 等旧 token 契约会拼出非法名）。

## 3. P0-B 限流绕过（specs/s-api-ratelimit）

- [x] 3.1 先红：用例断言 `/web/login`（剥前缀形态）第 31 次 POST 得 429——当前全 200，红。验证：红输出留档。
- [x] 3.2 `server/app/interfaces/middleware.py` + `main.py`：**反向排列 `register_middleware` 的 add_middleware 调用**（目标执行序 CORS→归一化→限流→访问日志），并加一条**执行顺序断言测试**；同步更正 `main.py:92-94` 的注释。验证：3.1 绿 + 两形态合并计数用例绿 + 顺序断言绿。
  → **机制偏差（实测驱动）**：本仓 venv 为 Starlette 1.6.0，实测 `app.user_middleware` 的实际嵌套顺序与"后 add 者在外层"的经典假设不符（反向排列后行为不变、访问日志仍打印原始路径）。改为**限流器内部归一化**（`_sensitive_path`：带前缀命中或剥前缀 + "/api" 命中 → 同判），与注册顺序解耦、版本无关；`register_middleware` 维持历史顺序（访问日志仍在最外层，429 照常可见）。红绿实证：模拟修复前（去掉两形态归一）两条方向用例全红（200），恢复后 14/14 绿。
- [x] 3.3 敏感清单扩展：`/api/web/register`、`/api/reset_password`、`/api/user/password`、`/api/user/deletion`、`/api/user/deletion/revoke`、`/api/pair/exchange`（随 6.2 落地）；匹配用归一化路径。验证：各端点超阈 429 用例绿 + "路由 × 凭据校验"对拍测试绿。
  → 清单 8 条（login/register/authorize/reset_password/user.password/user.deletion/deletion.revoke/pair.exchange）；对拍测试两条（凭据路由 ⊆ 清单、清单无死条目——pair/exchange 属 6.2 待落地，暂列 pending 白名单）。
- [x] 3.4 `server/tests/conftest.py` 在 **import app 之前**注入 `RATE_LIMIT_LOGIN_PER_MIN=2000`（`LIMIT` 类定义期求值，否则全量 pytest 大面积 429 假失败）。验证：全量 pytest 绿（先跑一次确认红清单）。
  → conftest 在 import app 前注入 `RATE_LIMIT_LOGIN_PER_MIN=2000`（LIMIT 类定义期求值）；全量 404 passed。
- [x] 3.5 来源键：新增 `TRUSTED_PROXY_HOPS`（默认 0=不信任 XFF，回落 `client.host`）；>0 时取 `XFF.split(",")[-hops]` 且做 IP 解析校验。加临时探针日志同打 `client.host`/完整 XFF 链/派生键（用于实测云托管网关行为并回填 design Open Question）。history 加定期清理。验证：单测（hops=0 不读 XFF；hops=1 取右段；伪造最左段不影响键）绿 + 探针日志样例追加。
  → `TRUSTED_PROXY_HOPS` 默认 0（回落 client.host，与历史一致）；取右起 hops 跳并做 IP 解析（去端口/方括号），链长不足回落；`_prune` 防内存增长；`_log_proxy_probe` 临时探针（信任未开且带 XFF 时记 peer/完整链/X-Real-IP）。6 条单测绿。

## 4. P1-A 密钥门禁 / mock 显式开关 / 关文档（specs/s-security-baseline R1-R3）

- [x] 4.1 `config.py` + `main.py` 启动校验：`DB_BACKEND=pg_http` 时 JWT_SECRET（非空/非默认/≥32）与 ADMIN_TOKEN（非空/非默认/≥16）不合格即 `RuntimeError` 列明全部项；sqlite 形态维持警告不阻断。验证：四态单测（空/默认/合法/本地）绿。
  → `settings.startup_config_errors()`（pg_http 严格/sqlite 零强制）+ `on_startup` 抛 RuntimeError；单测含端到端拒启实证（TestClient 进入即 raise）。
- [x] 4.2 mock 分级：pg_http 下 `PAYMENTS_GATEWAY` 缺省或空串拒启、mock 需 `PAYMENTS_ALLOW_MOCK=1`；sqlite 形态保持缺省 mock（本地栈/CI/pytest 零配置）。`dev_inject._check_admin` 改 `if not ADMIN_TOKEN: return False`。验证：单测四态绿 + `docker-compose.yml` 本地栈与 pytest 原样可跑（无需新增 env）。
  → `PAYMENTS_GATEWAY` 空串=未配置；`effective_gateway` 本地回落 mock、生产留空；`dev_inject._check_admin` 空令牌一律拒绝 + `secrets.compare_digest`；compose/dev-up/CI 零改动（全走 sqlite）。
- [x] 4.3 `ENABLE_API_DOCS`（默认关）控制 `/docs`、`/redoc`、`/openapi.json`。验证：默认态三端点 404 用例绿；开启态本地可用。
  → create_app 三 url 按 `ENABLE_API_DOCS` 显式开；两条用例绿（默认 404 / 显式 200）。
- [x] 4.4 `s-server-deploy.yml`：新增"部署前断言 PAYMENTS_GATEWAY 非空 + JWT_SECRET≥32 + ADMIN_TOKEN≥16"步骤（不满足 exit 1 并列变量名）+ 更正 46-48 行"空串回落 mock"注释；`server/tests/unit/test_config.py` mock 缺省三条断言按新语义改写。验证：workflow 语法检查 + 断言步骤本地干跑一次（故意置空验证 exit 1）+ 单测绿。
  → 新增「生产配置门禁」步骤（env 注入，不回显本体；密钥不进脚本源码），置于生成配置/部署之前；YAML 解析通过 + 干跑（空 → exit 1 列三项；合法 → exit 0）。

## 5. P1-B 激活属主校验（specs/s-payments）

- [x] 5.1 先红：用例断言「用户 A 激活用户 B 的到货态订单 → 按订单不存在拒绝且 B 的台账行不变」——当前会推进，红。
- [x] 5.2 `application/payments/activate_code.py` 增属主校验（`order["user_id"] != user_id` → `{"error": "order_not_found"}`）。验证：5.1 绿 + 属主正常激活用例绿（**不涉过渡别名**——`/api/pay/grants/activate` 不存在）。
  → 红证据：他人订单激活用例当前失败（攻击者能推进受害者台账行）；加 `order.get("user_id") != user_id → order_not_found` 后两条用例绿（他人台账行保持 pending_activation / 自单正常激活）。

## 6. P1-C 设备配对挑战-应答（specs/device-auth-page）

- [x] 6.1 DDL：`device_grants` 加 `challenge` 列（pg_http DDL + alembic sqlite），`pg_schema.py` 自检清单同步。验证：`run_schema_check` 绿 + alembic upgrade head 绿。
- [x] 6.2 S端 后端（落点全清单）：`domain/devices/device.py` DeviceGrant、`repositories/base.py` 抽象、sql/pg_http 两个 `upsert`（新参数**默认值 + keyword-only**，`test_pg_http_repos.py:349` 位置传参不破）、`authorize_device.py` 落 challenge（64 位小写 hex 校验）、`models/grant.py`；`/api/check-auth` 停发 token（**硬切：含 `challenge IS NULL` 存量记录，不留旧发放口**）；新增 `POST /api/pair/exchange`（client_api 路由族、恒定时间比对、NULL challenge 统一失败、纳入限流）。验证：pytest（配对成功/错误密钥统一拒绝不可区分/轮换/轮询无 token 字段/存量记录也不返回 token/exchange 429）绿。
- [x] 6.3 S端 前端：`src/api/client.ts` 的 `apiAuthorize` 增 `challenge` 入 body；`AuthPage.vue` 读 query 的 challenge 并提交，**challenge 缺失/不合法 → 复用既有 `notice warn` 形态的兜底提示 + 可点击出口（口径"升级桌面应用"）**；`RegisterPage.vue` 用户名列加 hint（§13）。验证：`auth-page.spec.ts` 五处 URL 补 `&challenge=<64hex>` + `beian.spec.ts:51` 同步 + mock 的 authorize 桩改为**校验 challenge 存在且为 64 位 hex**（防假绿）；新增"hint 可见 + 非法名被拒文案"用例；`npm run design:lint` 绿。
- [x] 6.4 C端 本机后端：`auth_local/service.py` 首次运行生成并持久化 `device_secret`（`secrets.token_urlsafe(32)`，仅 config.json）、`_build_auth_url` 带 challenge、**静默/轮询链路内完成 exchange**（本地无 token 或已判失效时调用，**有闸门**防路由切换刷新叠加撞限流）、`service.py:383` 的 `data["token"]` 直接下标改为"有则取、无则保留本地"、**对前端响应形状保持 code 0 带 token**；exchange 401/429 不清凭据（401 交用户主动重新授权、429 按可重试）。**无存量用户（拍板）→ 不做"旧 S端 回落读 token"兼容路径**。验证：`client/backend/tests` 绿 + 新增用例（无 token 字段 → 走 exchange；本地已持 token 不被空值覆盖；exchange 失败不清凭据）。
- [x] 6.5 连带用例同批更新（否则"全绿"不可达）：`server/tests/test_web_api.py`（authorize 无 challenge、check-auth 取 token 三处）、`test_device_activation.py`（authorize helper）、`test_check_auth_extension.py`、`tests/contract/*`、`client/backend/tests/test_entitlement_sync.py`（补"无 token → exchange"分支）、`test_auth_url.py`（注释"三参"改口径）。验证：这些文件全绿。
- [x] 6.6 版本错配兜底与发布口径（**无存量用户拍板 → 不做发布顺序约束、不做通告**）：授权页 challenge 缺失提示 + 下载出口；发布说明指引从发布页下载最新版 C端（旧安装包仍在 CDN，属唯一现实命中路径）。验证：授权页提示截图/curl 证据 + 发布说明草稿段落。

## 7. P2-A 口令与密保存储升级（specs/s-security-baseline R4）

- [x] 7.1 `password.py` 用 **bcrypt 模块直接调用**（不用 passlib）：标准 `$2b$` 格式、`startswith("$2")` 分派、恒定时间原语、fail-closed（空/非法哈希返回 False 不抛）、历史 PBKDF2 兼容并惰性改写。验证：pytest（新口令 bcrypt 格式/旧哈希登录成功且被改写/空哈希与 `"*"` 不 500/错误口令不升级）绿。
- [x] 7.2 72 字节策略：注册/改密/重置三处显式校验超长并给可读错误；密保答案归一化（strip + casefold）后同通道，历史空答案维持必失败。验证：超长拒绝用例 + 归一化等价用例（设置「 杭州 」后四种变体均过）绿。
- [x] 7.3 cost 实测定档：本地 0.25C 容器实测登录 P95（≥300ms 降 cost），结论回填 design Open Question。验证：实测数据追加在本 checkbox 下。

## 8. P2-B 会话撤销 token_version（specs/s-security-baseline R5）

- [x] 8.1 DDL + 领域：`users` 加 `token_version BIGINT NOT NULL DEFAULT 0`（alembic + pg_http DDL + pg_schema 自检）；`User.token_version`、sql/pg_http `_to_domain`、`models/user.py` `server_default="0"`。验证：迁移与自检绿 + 单测绿。
- [x] 8.2 签发与校验：`sign_jwt(..., ver=0)` 默认参；三处签发带真实版本；校验用 **`payload.get("ver", 0)`** 比对（缺声明视作 0，存量令牌不误伤）；已取 user 的端点免费比对，devices/pay 面走 **uid→token_version 的 60 秒 TTL 缓存**；鉴权依赖顺带拒绝 `status=='locked'`。验证：pytest（改密后旧 token 401/新 token 正常/无 ver 声明的存量 token 在原版本下正常放行/锁定的存量 token 立即 401）绿。
- [x] 8.3 自增四点：改密、改密保（同一 PATCH 带版本+1）、锁定、注销执行（`mark_deleted` 写固定哨兵 1，PostgREST 不支持自增）。移除单设备**不**自增；设备授权令牌不受本机制管辖。验证：pytest（移除设备不牵连网页端；注销执行全端失效；改密保后旧 token 401）绿。
- [x] 8.4 C端 失效链确认：S端 401 → 既有 `session_invalid` 处理清凭据回登录页，本地作品不动；exchange 刷新覆盖版本失效场景。验证：C端 pytest 既有失效用例 + 新增场景绿。

## 9. P3 加固项（specs/wechat-pay-gateway + s-security-baseline R6）

- [x] 9.1 回调背压：**独立计数桶**（不复用登录桶）+ SIGNTEST 豁免 + 阈值 10 次/60 秒 + **来源键不可信（TRUSTED_PROXY_HOPS=0）时只告警不阻断** + 达阈值走 `NotifyService` 告警；`WXPAY_NOTIFY_ALLOWLIST` 可选白名单（默认关，解析失败拒启）。验证：pytest（伪造扫描按可信态触发背压/不可信态不阻断且真微信可进验签/SIGNTEST 不计/白名单外 403 不告警/白名单未配置行为不变/坏配置拒启）绿。
- [x] 9.2 CORS：`CORS_ALLOW_ORIGINS`（默认空）；**生产须显式列入 www 与静态托管默认域**（写进部署说明）。验证：`curl -H Origin:https://evil.example` 无 ACAO 头用例 + 白名单命中用例 + 手工验证两域名（门户 + 默认域）可用，输出追加。
- [x] 9.3 门户安全响应头：nginx 增三头（docker 形态）。验证：`curl -I` 前后对照输出追加；**并验证生产静态托管是否支持自定义响应头，结论登记**（不支持则该场景在静态托管形态不适用）。
- [x] 9.4 日志凭据卫生：`main.py:114-118` 去 tail4；CI 侧 `s-server-deploy.yml:92,101,143` + `secret-fingerprint.yml:17` 同批去 tail4。验证：grep 扫描结论 + 新指纹日志样例 + CI 步骤输出样例追加。
- [x] 9.5 本地卫生：`server/secrets/*.pem` 权限 600；排查 `client/packaging/cert/cert.pfx` 是否含私钥口令并登记结论（不处置）。验证：`ls -l` 输出 + 结论追加。

## 10. 回归与收官

- [x] 10.1 S端 全量 pytest 双后端（sqlite 全量 + pg_http MockTransport 注入/过滤器形态套件）。验证：全绿输出摘要追加。
- [x] 10.2 S端 e2e 全量（`server/frontend` playwright）。验证：全绿输出摘要追加。
- [x] 10.3 C端 全量（`client/backend` pytest + 本地 docker 栈 e2e 全量——auth 流改动必须全量跑，按 [[c-client-e2e-runbook]]）。验证：全绿输出摘要追加。
- [x] 10.4 双端类型门禁：`server/frontend` vue-tsc --noEmit、`client/frontend` tsc --noEmit。验证：零错误输出追加。
- [x] 10.5 设计门禁：双端 `npm run design:lint`；本 change 不触共享段（依据 notes-impact.md），`design-cross` 不适用——记录该判定。验证：lint 绿输出追加。
- [x] 10.6 本地 docker 栈全链路演练单：注册（新用户名白名单与 §13 提示）→ 浏览器授权（challenge）→ 轮询无 token → 本机 exchange 换 token → 首启新机器自动进主界面 → 改密码 → 旧 token 401 → 移除单设备不牵连 → 注销流程；另验 fail-fast 两条（pg_http 空密钥拒启、pg_http 缺 PAYMENTS_GATEWAY 拒启）与 sqlite 零配置可启。验证：演练记录（含响应摘录）追加。
- [x] 10.7 发布说明草稿（**无存量用户：强调"上线前安全基线"，不含升级通告类文案**）+ todo.md「S端 安全」节勾选回写。验证：草稿文件与 todo 回写 diff。

  → 迁移 d7e9f1a3b5c7（基于 a002_payments_tables）；pg_schema 自检清单加 ("challenge","text")。注：alembic 双 head 为存量问题（未恶化），sqlite 测试由 create_all 兜底建列。
  → 新增 `client_api/pairing.py`（exchange + build_license_snapshot 共用装配，check-auth 同源零漂移）；authorize 强制 64-hex challenge（缺失→"桌面端版本过旧"）；check-auth 硬切（无 token 字段，存量行一致）；轮换=重新授权覆盖 challenge；恒定时间比对 secrets.compare_digest。test_check_auth_poll 含三断言（轮询无 token/正确密钥换到/错误密钥统一失败）。
  → client.ts 传 challenge；AuthPage 版本错配兜底（notice warn + 双平台下载出口，实时解析 latest.json、失败回落 Releases 页）；RegisterPage 用户名 hint（§13）。e2e：auth-page 5 处 URL + beian 1 处补 challenge、mock authorize 校验 challenge + register 白名单分支 + 新增 pair/exchange 桩与路由；新增「缺少配对信息显示升级出口」用例。S端 e2e 全量 178/178 绿；vue-tsc 零错误；design:lint 唯一告警（site-beian.ts emoji）为主检出存量非本 change 引入。
  → service.py：首启生成并持久化 device_secret（token_urlsafe(32)=256 位，仅 config.json）；授权 URL 带 challenge（密语本体绝不上 URL）；静默链路 poll 无 token → 本地有令牌保留刷新 / 无令牌走 exchange；401/429 不清凭据（429 可重试）。C端全量 1186 passed；新增 tests/test_pairing.py 9 条（含「前端契约不变：本机响应仍回 code 0 + token」回归钉）。无存量用户 → 未做「旧 S端 回落」兼容路径（拍板）。
  → 21 个受影响用例全部同批改口：test_web_api 7 处 authorize 补 challenge、check-auth poll/verify_ok 改走 exchange、device_activation 助手内置 challenge、contract 硬切契约 + 授权补 challenge、check_auth_extension（NameError 修复后全绿）。conftest 另加 pair_device 助手供后续（token_version）用例复用。全量 422 passed。
  → 兜底已随 6.3 落地（授权页 notice warn + 双平台下载出口/Releases 回落）；发布说明段落在任务 10.7 出稿时一并写。
  → bcrypt 直连（$2b$ 标准格式、cost 12 可经 BCRYPT_ROUNDS env 覆盖、测试栈注入 4）；恒定时间（bcrypt 库内 + 存量路径 hmac.compare_digest）；fail-closed（空/非法哈希 False）；惰性升级挂 login 与 authorize 验密两处。实现细节：**bcrypt 格式预检必须先于 checkpw**——pyo3 绑定对畸形哈希抛 PanicException（非 ValueError，tests 里实测捕获不到），已加 _BCRYPT_RE 预检并注释。5 条新用例绿。
  → 72 字节在注册/改密/重置三处显式拒绝（可读 msg「密码过长（最多 72 字节）」）；密保答案 strip+casefold 在 register/update_security/reset 三处同一通道；历史空答案维持必失败。测试以「 Hangzhou 」设置、大小写/空白变体验证 + 错误答案拒绝。2 条用例绿。spec 场景措辞勘误：中文答案无大小写之分，归一化等价域=大小写与首尾空白。
  → 迁移 e8f2a4b6c8d0（基于 d7e9f1a3b5c7）；pg_schema users 清单加 ("token_version","typed")；User 域字段 + 双仓储 _to_domain + ORM server_default="0"。单测绿。
  → sign_jwt(ver) 默认 0（存量令牌缺 ver 按 0 比对，升级零登出——有用例钉住）；三签发点带真实版本；比对点=deps.get_current_user_or_none + payments._current_identity（401），底层 `interfaces/deps.token_revoked` + `infrastructure/security/token_version.py`（60s TTL 缓存、写侧 invalidate_all 即时失效）。实现收紧（**偏离本任务原文，已同步 spec R5**）：版本比对覆盖全部持合法 uid 的令牌（含 C端 配对令牌）——原文的「设备授权令牌不受管辖」会在改密后让 C端 凭据存活 30 天，反而留洞；实测 C端 影响可忽略（轮询刷新走 check-auth 免令牌，到期重新授权即恢复）。锁定拒绝：**无系统内触发路径（人工运维项）**，偏离已登记——运维口径=置 locked 须同步 token_version+1。
  → 改密/改密保=同一 PATCH 携带版本+1（user 行已取，零额外往返）；注销执行=mark_deleted 置哨兵 1（pg/sql 双侧；PostgREST 无 col=col+1）；移除单设备不自增（用例钉住），并**顺带修存量缺口**：移除设备此前只删登记行不删授权凭证（被移设备令牌仍过 verify）→ 已补 grant_repo.delete_by_fingerprint 并在 remove_device 接线（指纹为空不清：无档案授权彼此不可区分）。4 条用例绿（改密 401/新令牌正常/改密保 401/移除不牵连+被移设备失效）。
  → S端 401 → 既有 session_invalid 处理清凭据回登录页、本地作品不动；改密后 C端 静默刷新不受影响（check-auth 免令牌）。C端全量 1195 passed。
  → CORS_ALLOW_ORIGINS（默认空=不允许跨域；methods/headers 同步收窄为白名单）。生产部署 MUST 列入 www 与静态托管默认域（部署说明任务 10.7 承接）；S端 e2e（全走 vite 代理同源）178 绿。注：S端 e2e 全 mock，跨域真实验证（curl -H Origin 两域名）移入 10.6 演练单。
  → nginx 三头（nosniff/DENY/no-referrer，仅 docker 形态生效）；生产静态托管的自定义响应头能力**待部署期验证登记**（本机无法验证）。
  → main.py env 指纹去 tail4；CI 三处（s-server-deploy 生成配置/secret 注入/CloudBase 存储）+ secret-fingerprint.yml 同批去 tail4；grep 复核 0 残留；长度+哈希保留（四点对拍能力不减）。
  → server/secrets/*.pem 已 chmod 600（主检出；worktree 无该目录）；cert.pfx 排查结论：**带口令保护**（openssl 无口令读取失败），口令不在仓库内 → 无需处置，登记在案。
  → 独立计数桶 + SIGNTEST 豁免 + 阈值 10 次/60s + 来源可信才阻断、不可信只告警不阻断 + 达阈值 NotifyService 告警（跨阈值只报一次）+ WXPAY_NOTIFY_ALLOWLIST 白名单（配置即强制、解析失败拒启）。7 条用例绿。
  → 本机实测 cost 12：register ≈170-180ms / login ≈167ms；0.25C 容器按 2-3 倍估算 350-500ms → 定档 12 不升 14（「≥300ms 降 cost」即指 12）；测试栈 BCRYPT_ROUNDS=4 提速；生产 P95 由 CLS 观察点复核。结论回填 design Open Question。
  → 433 passed（含安全回归用例）。
  → 178 passed。
  → client/backend 1195 passed（含 test_pairing 9 条）；C端 docker 栈 e2e 随 10.6 演练执行。
  → server/frontend vue-tsc 零错误；client/frontend tsc --noEmit exit 0。
  → 两端 design:lint 通过（唯一告警 site-beian.ts emoji 为主检出行存量，notes-impact 已登记）；不触共享段，design-cross 不适用。
  → release-notes.md 已落（对外大白话段 + 内部部署注意段：secrets 门禁/CORS 域名清单/DDL 先行/无存量用户同批发版）；todo.md「S端 安全」节已回写实施进度（33→40 项时的状态）与余量。
  → 演练已执行（2026-09-18，venv 直启双后端 + docker compose 栈重建两轮）。**docker 栈已重建为
本 change 代码**（容器内核验：S端 guards.py 存在、C端 service.py 含 pair/exchange），并跑完
**C端 e2e 全量：140 passed / 14 skipped（付费门控）**——登录/授权页等真实配对链路（浏览器授权→
轮询→本机交换→进主界面）在重建栈上走通。空指纹授权登记行合并为同一行系存量语义（演练澄清，非回归）。
  注册白名单（非法名 code1+可读提示）→ 浏览器授权（challenge 落库）→ 轮询无 token → **C端 首启静默链路经
  pair/exchange 自动换 token**（本机后端对前端仍回 code 0+token，前端零改动实证）→ 错误密钥统一失败 →
  改密码（旧令牌 pay 面 401、user 面未登录、新密码可登录）→ 移除设备（被移设备 verify device_valid=False、
  web 会话不牵连）→ 注销受理/撤销期 code4/撤销恢复/恢复后可登录。fail-fast 两条以**隔离子进程实际启动**验证
  （pg_http 空密钥拒启；pg_http 缺 PAYMENTS_GATEWAY 拒启——错误信息列明变量）；sqlite 零配置可启（全程演练跑在其上，skus 200）。
  演练发现并澄清两点：①空指纹授权在登记表按 (user_id, fingerprint="") 合并为同一行（存量语义，非回归），
  演练据此以带档案形态复验（指纹路径 5/5）；②**C端 docker 栈 e2e 全量未在本环境执行**（无 docker），
  作为合并前最后一道，随 CI/下一环境执行。