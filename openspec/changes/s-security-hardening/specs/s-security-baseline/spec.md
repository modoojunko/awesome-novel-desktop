# s-security-baseline Specification

## Purpose

S端 服务加固基线：生产密钥强度门禁（配置不对拒绝启动）、支付 mock 网关显式开关、API 文档端点默认关闭、口令与密保答案存储策略、会话撤销（凭据版本）、CORS 白名单与安全响应头、诊断日志凭据卫生。目标=任何"配置缺失/误删"都 fail-closed，凭据一旦泄露可即时作废。

## ADDED Requirements

### Requirement: 生产密钥强度门禁

`DB_BACKEND=pg_http`（生产形态）下进程启动时 SHALL 校验 JWT_SECRET 与 ADMIN_TOKEN：为空、为出厂默认值、或长度低于下限（JWT_SECRET ≥ 32 字符、ADMIN_TOKEN ≥ 16 字符）即 MUST 拒绝启动，并在错误信息中逐项列明不合格变量（MUST NOT 回显密钥本体）。sqlite 本地开发形态 SHALL 维持现状可用（仅告警），MUST NOT 因弱默认值拒绝启动。

#### Scenario: 空密钥拒绝启动

- **WHEN** 生产形态下 JWT_SECRET 环境变量存在但为空串（如部署配置里 secret 缺失被注入空值）
- **THEN** 进程拒绝启动，错误信息指明 JWT_SECRET 不合格；MUST NOT 以空密钥或默认密钥对外服务

#### Scenario: 出厂默认值拒绝启动

- **WHEN** 生产形态下 ADMIN_TOKEN 为 `admin123` 或长度不足 16
- **THEN** 进程拒绝启动并列明原因

#### Scenario: 合法配置正常启动

- **WHEN** 生产形态下两个密钥均为足够长度的强随机值
- **THEN** 进程正常启动，行为与加固前一致

#### Scenario: 本地开发形态不受强制

- **WHEN** sqlite 本地栈未设置任何密钥环境变量
- **THEN** 进程正常启动（保留既有告警日志），本地开发与测试零改动

### Requirement: mock 网关显式开关

网关选择 SHALL 按后端形态分级：`DB_BACKEND=pg_http`（生产）下 `PAYMENTS_GATEWAY` 缺省或为空串时
进程 MUST 拒绝启动（MUST NOT 静默回落 mock），mock 仅在显式 `PAYMENTS_GATEWAY=mock` 且
`PAYMENTS_ALLOW_MOCK=1` 时可用；sqlite 本地形态（本地开发、docker 测试栈、pytest、dev-up）
SHALL 保持既有行为：缺省即 mock、零配置可启动——分级是刻意设计，一律强制会打死本地栈与 CI。
dev 注入端点（`/api/dev/pay/*`）SHALL 仅在 mock 网关生效时注册；`ADMIN_TOKEN` 为空时这些端点
MUST 对一切请求（含不带头/空头）返回未授权（不得出现空令牌即放行）。

#### Scenario: 生产未显式配置拒绝启动

- **WHEN** `DB_BACKEND=pg_http` 且部署配置未注入 `PAYMENTS_GATEWAY`（或注入空串）
- **THEN** 进程拒绝启动并提示必须显式选择 mock/wxpay，MUST NOT 以 mock 网关处理任何订单

#### Scenario: 生产显式允许才可 mock

- **WHEN** `DB_BACKEND=pg_http` 且 `PAYMENTS_GATEWAY=mock` 但未设 `PAYMENTS_ALLOW_MOCK=1`
- **THEN** 进程拒绝启动
- **WHEN** 两者齐备（演练部署）
- **THEN** mock 网关与 dev 注入端点按既有行为可用

#### Scenario: 本地形态零配置可用

- **WHEN** sqlite 形态未设置任何 `PAYMENTS_*` 环境变量（本地开发、docker 栈、pytest）
- **THEN** 进程正常启动并装配 mock 网关，既有测试与本地流程零改动

#### Scenario: 管理令牌为空时注入端点必须拒绝

- **WHEN** mock 网关生效且 ADMIN_TOKEN 为空串
- **THEN** `/api/dev/pay/*` 对一切请求（含不带头/空头）返回未授权，MUST NOT 出现空令牌即放行

### Requirement: API 文档端点默认关闭

生产构建默认 SHALL NOT 注册 `/docs`、`/redoc`、`/openapi.json`；仅当显式设置本地调试开关（如 `ENABLE_API_DOCS=1`）时注册。关闭时三者均返回 404，MUST NOT 泄露路由清单。

#### Scenario: 生产文档端点不可达

- **WHEN** 未设置调试开关的部署收到 `GET /docs`、`GET /redoc`、`GET /openapi.json`
- **THEN** 一律 404，响应不含任何接口定义

#### Scenario: 本地调试可显式打开

- **WHEN** 本地设置 `ENABLE_API_DOCS=1` 启动
- **THEN** 文档端点按 FastAPI 默认行为可用

### Requirement: 口令与密保答案存储策略

口令哈希 SHALL 使用自带随机盐的自适应哈希（bcrypt，标准 `$2b$` 格式，MUST NOT 自造格式），
校验 SHALL 使用恒定时间原语；历史 PBKDF2（全局固定盐）哈希 SHALL 继续可验证（兼容读），
且在该用户下次验证成功时 MUST 改写为新算法哈希（无感升级，用户零感知）。校验 SHALL fail-closed：
哈希为空、格式非法或算法库抛错时一律返回验证失败（MUST NOT 冒泡 500）。口令长度上限 SHALL
显式定义并校验（bcrypt 语义上限 72 字节，超长 MUST 在注册/改密/重置处明确拒绝，MUST NOT 静默截断）。
密保答案 SHALL 在哈希前归一化（去首尾空白、转小写），与口令相互独立（各自随机盐）；
历史空答案维持"未设置 = 验证必失败"语义。

#### Scenario: 新口令用新算法

- **WHEN** 新用户注册或既有用户修改/重置密码
- **THEN** 存储的口令哈希为 `$2b$` 前缀的标准 bcrypt 格式，同一明文两次哈希结果不同

#### Scenario: 历史哈希兼容并升级

- **WHEN** 仍持有旧 PBKDF2 哈希的用户以正确密码登录
- **THEN** 登录成功，且该用户口令哈希被改写为 bcrypt 格式（下次登录走新算法校验）

#### Scenario: 非法/空哈希 fail-closed

- **WHEN** 库中口令哈希为空串或非预期格式（注销置空行、历史脏数据）
- **THEN** 验证返回失败，接口返回业务错误（MUST NOT 抛异常变 500）

#### Scenario: 超长口令明确拒绝

- **WHEN** 注册/改密/重置的明文口令超过 72 字节
- **THEN** 明确拒绝并给出可读原因，MUST NOT 静默按 72 字节截断后存哈希

#### Scenario: 密保答案归一化

- **WHEN** 用户设置密保答案为「 杭州 」，之后以「杭州」「杭州 」「HANGZHOU」等大小写/空白变体验证
- **THEN** 均视为同一答案（设置与验证走同一归一化）

### Requirement: 会话凭据版本化撤销

每个账号 SHALL 持有单调递增的凭据版本号；签发的会话令牌 SHALL 携带签发时版本，鉴权时 MUST 比对；
**版本比对 SHALL 把"令牌无版本声明"视作版本 0**（与列默认值一致）——存量令牌 MUST NOT 因缺少
该声明被判定无效（否则等于一次全站强制登出）。修改密码、修改密保答案、账号锁定、注销到期执行
SHALL 使版本自增——上述任一事件发生后，该账号全部存量令牌 MUST 立即失效。
移除单个设备 MUST NOT 自增版本（该设备授权随既有解绑逻辑单独失效，不波及其他已登录端）。
设备授权令牌（C端 配对所得）SHALL NOT 受版本比对管辖——其失效由授权记录删除/覆盖承担
（注销执行、移除设备、重新授权三条路径已覆盖）。

#### Scenario: 改密码后旧令牌作废

- **WHEN** 用户修改密码成功后，持修改前签发的令牌访问任意受管端点
- **THEN** 收到 401，需重新登录

#### Scenario: 存量无版本令牌不被误伤

- **WHEN** 持"无版本声明"的存量令牌（版本比对按 0）访问，且该账号版本仍为 0
- **THEN** 正常放行，MUST NOT 出现升级即全员登出

#### Scenario: 新令牌不受影响

- **WHEN** 用户修改密码后用新令牌访问
- **THEN** 正常放行

#### Scenario: 锁定账号即时失效

- **WHEN** 账号被置为锁定态
- **THEN** 其存量令牌失效，且鉴权时对锁定态账号一律拒绝（不依赖是否有人记得自增版本）

#### Scenario: 注销执行即全端失效

- **WHEN** 注销到期执行完成
- **THEN** 该账号全部存量令牌失效，与既有注销门禁双保险

#### Scenario: 移除单设备不牵连其他端

- **WHEN** 用户在控制台移除某一台设备
- **THEN** 该设备的授权失效；用户网页端与其他已授权设备会话保持有效

### Requirement: 出口收敛与凭据日志卫生

CORS SHALL 从全通配收敛为显式白名单（环境变量配置允许的源）；未配置时默认不允许浏览器跨域调用，
且部署 MUST 显式列入门户实际访问域名（统一域名与静态托管默认域），否则经默认域直访门户会整体不可用。
S端 门户 SHALL 输出 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、
`Referrer-Policy: no-referrer` 响应头——**交付形态分档**：docker 形态由门户 nginx 提供；
生产静态托管形态以托管平台能力为限，验证平台是否支持自定义响应头并记录结论（不支持时该场景
在静态托管形态下不适用，不属于回归）。运行日志、审计事件与告警 MUST NOT 包含密钥、令牌、口令、
密保答案的任何片段（含尾 4 位明文；哈希摘要形态的诊断指纹除外）。

#### Scenario: 默认拒绝跨域

- **WHEN** 未配置 CORS 白名单时，任意外部站点发起跨域 API 调用
- **THEN** 响应不携带允许该源的 CORS 头，浏览器侧不可读响应

#### Scenario: 门户域名可用

- **WHEN** 白名单已列入门户域名，用户经该域名访问门户并发起同源 API 调用
- **THEN** 登录、注册、下单等全流程可用（含静态托管默认域直访场景）

#### Scenario: 安全响应头存在（docker 形态）

- **WHEN** 经本地 docker 栈访问 S端 门户
- **THEN** 响应携带上述三个安全响应头

#### Scenario: 日志无凭据片段

- **WHEN** 检查启动指纹、访问日志与异常堆栈日志（运行期）与 CI 指纹步骤输出
- **THEN** 找不到密钥/令牌/答案的明文或尾片段（哈希摘要形态的诊断指纹除外）
