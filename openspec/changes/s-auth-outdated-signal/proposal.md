# Proposal: s-auth-outdated-signal

## Why

2026-09-19 生产事故：S端 加配对 challenge 门禁后，authorize 对「challenge 缺失」与「密码错误」同返 code=1（仅 msg 不同），C端 无从区分「需要升级」与「鉴权失败」；且 challenge 缺失本质是**模糊信号**（配对密钥缺失≠客户端版本旧），文案却断言「桌面端版本过旧」——当天实际是 S端 前端漏发，全部新客户端被误判为旧。登录链路缺一个可靠的「客户端需更新」信号通道，是本次事故响应慢与文案误导的根因。

## What Changes

- **authorize 错误码分档**：challenge 缺失/不合法 → 独立 code（`client_outdated`），携带 `latest_version` 与 `download_url` 事实；密码/账号错误维持 code=1；模糊信号不得断言客户端版本。
- **outdated 标记落库（非内存）**：authorize 以 client_outdated 拒绝时按 pc_hash 记标记（PG 侧表/KV），TTL 读时比较（≥10min，覆盖 C端 60×2s 轮询窗+重试余量）；多实例/重启不丢（云托管 MinNum=0 缩容冷启动是常态）。
- **check-auth 携带第二信号**：无 grant 且存在有效标记 → 独立 code=3 + `data.client_outdated/latest/download_url`。**独立 code 是硬要求**：若挂 code=1，旧 C端 `auth_local/service.py` 的 code-1 分支会当场清本地凭据（把协议失配误判成会话作废）。
- **pair/exchange 不受染**：`_fail()` 统一形态不携带 outdated 信息（防旁路探测），落契约测试。
- **C端 本地透传**：`/api/auth/check-auth` 响应透传 `client_outdated` 载荷（旧 C端 走「未知 code 按未登录」兜底，天然安全）。

## Capabilities

### New Capabilities
- `s-client-outdated-signal`：S端 「客户端需更新」信号契约——authorize 分档、pc_hash 标记落库与 TTL、check-auth 独立 code、pair/exchange 排除面。

### Modified Capabilities
（无——`devices`/`device-auth-page` 现有需求不因本变更改语义。）

## Impact

- **S端（server/）**：`app/application/devices/authorize_device.py`（分档+写标记）、`app/interfaces/client_api/authorize.py`/`pairing.py`（响应形态，pairing 只加断言不改语义）、check-auth 出口（读标记+code=3）、PG 标记存储（device_grants 侧表或 KV，随 s-server-deploy 部署）；S端 前端 `AuthPage.vue` 升级出口文案对齐两场景分档（「需要更新」vs「暂时无法登录」）。
- **C端（client/backend）**：`auth_local/service.py` check-auth 透传 data（新增字段向后兼容）。
- **测试**：S端 pytest（分档/TTL/多实例语义/排除面契约测试）；C端 pytest 透传断言。
- **部署**：S端 独立部署即时生效（本 change 是三件中唯一能立刻缩小事故面的）；零客户端发版依赖——新 C端 消费该信号属 c-loginless-data-exit。

## Design Impact

- 受影响端：S端 为主（后端+AuthPage 文案）＋ C端 后端一行透传。不触两端共享段。
- 受影响屏/弹层：S端 `/auth` 授权页（错误提示两场景文案）；C端 无界面改动（本 change 只建信号通道）。
- 对象状态：新增 pill warn「需要更新」/「暂时无法登录」两档文案（design-language §5 warn 档；红色 err 不用于此——登录受阻无不可逆后果）；无新组件词汇。
- 原型先行：S端 授权页文案两场景变更属用户可见——`device-auth-page` 原型（server 无独立原型基线，按 S端 惯例附截图对照于 change 目录）；实现侧自查。
