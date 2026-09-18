# device-auth-page Specification

## Purpose
设备授权页入口契约：C端 桌面端发起设备绑定时在宿主浏览器打开的授权页由 S端 前端 `/auth` 唯一承载，后端不再提供手写内联授权页。授权动作（POST /api/authorize）与 C端 轮询（GET /api/check-auth）契约不变。

## Requirements

### Requirement: 授权页由 S端 前端 /auth 唯一承载

C端 桌面端 SHALL 构造授权页地址为 `{web_origin}/auth?pc_hash=<pc_hash>&pc_name=<urlencode(pc_name)>&device_profile=<device_profile>`，其中 `web_origin` 为 public_server_api 剥掉尾部 `/api` 后的源（如 `https://www.awesomenovel.com/api` → `https://www.awesomenovel.com`）；系统 SHALL NOT 提供后端内联授权页（GET /api/auth-page 返回 404）。

#### Scenario: C端 发起设备绑定打开正牌页

- **WHEN** 用户在 C端 登录页点击「浏览器登录」
- **THEN** 宿主浏览器打开 `{web_origin}/auth?pc_hash=...&pc_name=...&device_profile=...`，页面为 S端 前端设计系统授权页（含无效态/注册入口/限频文案/成功态套餐与到期展示）

#### Scenario: 旧内联授权页已删除

- **WHEN** 任意客户端请求 `GET /api/auth-page`
- **THEN** 返回 404，响应体不含任何授权表单 HTML

#### Scenario: device_profile 经 query 传递不失真

- **WHEN** C端 将 URL-safe Base64（无 padding）编码的 device_profile 拼入 query 打开 /auth
- **THEN** 授权页解析到的 device_profile 与 C端 原串逐字符一致，提交 /api/authorize 后设备档案完整入库

### Requirement: 授权页消费 pc_name

授权页 SHALL 读取 query 中的 `pc_name` 并随授权请求提交，使设备在控制台展示用户可见的设备名；`pc_name` 缺省时按空串处理，由后端既有兜底链（device_profile.hostname 优先）承接。

#### Scenario: 设备名随授权落库

- **WHEN** 用户在 /auth 页输入账密提交授权，URL 携带 `pc_name=Work-Mac`
- **THEN** /api/authorize 收到 pc_name="Work-Mac"，生成的设备记录以该名称展示

### Requirement: 授权与一次性配对契约

授权动作 SHALL 仍为 `POST /api/authorize`（username/password/pc_hash/pc_name/device_profile），并新增必填 `challenge`（本机配对密钥的 SHA-256 哈希，64 位小写 hex）。C端 SHALL 在首次运行时生成本机配对密钥（≥256 位密码学安全随机），仅存本地配置、绝不经 URL/日志/轮询响应传输；其哈希（challenge）SHALL 随授权页 URL 提交、经授权请求落库到该设备的授权记录。

C端 轮询 `GET /api/check-auth?pc_hash=...` SHALL NOT 再返回会话令牌：无授权记录返回 code 1「等待授权」（不变）；已有授权记录返回 code 0 携带刷新数据（username/tier/expires_at/entitlement），MUST NOT 携带 token 字段。

换取令牌 SHALL 走 `POST /api/pair/exchange`（pc_hash + 本机配对密钥）：服务端以恒定时间比对配对密钥哈希与授权记录 challenge，匹配 SHALL 返回 token 与套餐数据；不匹配、缺参、无授权记录、或该记录 challenge 为空（存量未升级）SHALL 统一按配对失败拒绝（MUST NOT 区分具体原因）。该端点 SHALL 纳入登录类限流清单；被限流拒绝（429）SHALL 视为可重试，MUST NOT 让客户端清空本地凭据。浏览器重新授权 SHALL 以新 challenge 覆盖旧值（配对密钥轮换）。

**C端 本机契约（硬约束）**：C端 本机后端对 C端 前端的 check-auth 响应形状 MUST 保持既有形态（code 0 时 `data` 携带 token 与 username）——本机后端 SHALL 在轮询链路内完成 exchange 并把 token 注入响应；C端 前端 MUST NOT 因本契约变化而需要改动。本地已持有效 token 时，本机后端 MUST NOT 用刷新的空值覆盖它。

仅知道 pc_hash（硬件序列号派生、可推导）MUST NOT 能取得会话令牌——令牌的取得 MUST 以持有本机配对密钥为前提。

**存量记录（challenge 为空）策略=硬切**：轮询对这类记录 MUST NOT 返回 token（与其余记录一致，
不得为兼容保留旧发放口）；**产品当前无用户，该分支实质只为契约完备性存在**——若未来出现此类记录
（如旧安装包被换上使用），其持有者需经一次浏览器重新授权补 challenge 完成升级。

**版本错配兜底**：授权请求缺失 challenge（典型=用户从发布页/CDN 装到旧版桌面端）时，授权页 SHALL
展示可读的升级提示与下载出口，MUST NOT 只显示无法理解的校验失败。

#### Scenario: 轮询不再返回令牌

- **WHEN** 已完成浏览器授权的设备以 `GET /api/check-auth?pc_hash=...` 轮询
- **THEN** 返回 code 0 携带 username/tier/expires_at/entitlement，响应体不存在 token 字段

#### Scenario: 授权全链路走通

- **WHEN** 用户在 /auth 页提交正确账密（授权请求携带 challenge）
- **THEN** 页面展示授权成功（含套餐 tier 与到期日），C端 本机后端在轮询链路内以 `POST /api/pair/exchange` 换到 token 并落盘，对 C端 前端仍以既有形状回 token，用户自动进入主界面

#### Scenario: 首次授权的新机器不需要人工干预

- **WHEN** 全新安装的 C端（本地无 token、无历史凭据）完成浏览器授权
- **THEN** 轮询窗口内自动完成 exchange 并进入主界面，MUST NOT 出现"授权超时"（本机后端必须回带 token）

#### Scenario: 持本机配对密钥换到令牌

- **WHEN** C端 以 pc_hash + 本机配对密钥请求 `POST /api/pair/exchange`，且该设备授权记录的 challenge 与密钥哈希一致
- **THEN** 返回该账号的有效 token 与套餐数据

#### Scenario: 仅知 pc_hash 拿不到令牌

- **WHEN** 攻击者仅凭推导出的 pc_hash 轮询 check-auth 并尝试 `POST /api/pair/exchange`（不持有本机配对密钥或持错误值）
- **THEN** 轮询仅得刷新数据（无 token），exchange 一律拒绝，且无法从响应区分失败原因

#### Scenario: 配对失败不改写本地凭据

- **WHEN** exchange 因密钥不匹配（401）或被限流（429）失败
- **THEN** C端 保留本地既有凭据并给出可重试信号，MUST NOT 清空登录态或把用户踢回登录页（401 场景由用户主动重新授权解决）

#### Scenario: 配对密钥轮换

- **WHEN** 用户在同一设备重新走浏览器授权
- **THEN** 授权记录的 challenge 被新值覆盖，旧配对密钥换不到令牌

#### Scenario: 存量记录硬切不保留旧发放口

- **WHEN** 任何 challenge 为空的授权记录（契约完备性分支；当前无用户，实际不应出现）被轮询
- **THEN** 一律不返回 token 字段；该记录持有者经一次浏览器重新授权（补 challenge）后恢复正常

#### Scenario: 版本错配时授权页给出升级出口

- **WHEN** 页面收到缺失 challenge 的授权入口（典型=旧版桌面端，或用户装到发布页上的旧安装包）
- **THEN** 展示"请升级桌面应用"的可读提示与下载出口（MUST NOT 只显示无法理解的校验失败）

#### Scenario: exchange 受限流保护

- **WHEN** 同一 IP 60 秒内对 `/api/pair/exchange` 提交超过阈值次数
- **THEN** 后续请求收到 429，合法客户端按正常节奏重试可成功

