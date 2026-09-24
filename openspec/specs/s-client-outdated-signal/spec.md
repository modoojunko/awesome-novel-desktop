## Purpose

S端 登录链路的「客户端需更新」信号契约：authorize 拒绝分档、pc_hash 维度的 outdated 标记落库与 TTL 读取、check-auth 以独立 code 携带第二信号、pair/exchange 排除面——使 C端 能可靠区分「需要升级」与「鉴权失败/服务异常」，且模糊信号不得断言客户端版本。

## Requirements

### Requirement: authorize 分档拒绝

- `POST /api/web/devices/authorize` 对「challenge 缺失或不合法」SHALL 返回独立错误档（code=3，`reason="client_outdated"`），并携带 `latest_version` 与 `download_url`（解析失败时省略 download_url，不得编造）；用户名/密码错误 SHALL 维持 code=1。
- challenge 缺失属模糊信号（配对密钥缺失≠版本旧）：错误 msg SHALL 表述为「需要更新后重试」类动作导向，SHALL NOT 断言「桌面端版本过旧」。
- authorize 拒绝为 client_outdated 档时 SHALL 按 pc_hash 记录 outdated 标记（持久化存储，非进程内存），字段含 `pc_hash`、`rejected_at`。
- 标记读取 SHALL 按 TTL 比较（≥10 分钟），过期即视同不存在；不依赖清理任务。

#### Scenario: challenge 缺失返回分档与标记

- **WHEN** authorize 请求 challenge 为空且用户名密码正确
- **THEN** 返回 code=3 + reason=client_outdated + latest_version；按 pc_hash 落标记；不发放令牌

#### Scenario: 密码错误不落标记

- **WHEN** challenge 合法但密码错误
- **THEN** 返回 code=1「用户名或密码错误」；不写 outdated 标记

#### Scenario: 服务重启标记不丢

- **WHEN** authorize 落标记后 S端 实例重启（云托管缩容冷启动）
- **THEN** TTL 窗口内同 pc_hash 的 check-auth 仍可读到标记

### Requirement: check-auth 携带客户端需更新信号

- `GET /api/check-auth` 在「该 pc_hash 无有效 grant 且存在 TTL 内 outdated 标记」时 SHALL 返回独立 code=3，data 携带 `client_outdated: true`、`latest_version`、`download_url`（有则带）；SHALL NOT 挂在 code=1 下（旧 C端 code-1 分支会清本地凭据，属事故级副作用）。
- 无标记或标记过期时 SHALL 维持既有响应形态不变。
- C端 本地 `GET /api/auth/check-auth` SHALL 透传该 data 字段（旧 C端 对未知 code 按未登录兜底，天然兼容）。

#### Scenario: 被拒客户端轮询命中信号

- **WHEN** authorize 以 client_outdated 拒绝后，C端 2 秒轮询 check-auth（窗口 120s）
- **THEN** 每轮均返回 code=3 + client_outdated 载荷（TTL ≥ 轮询窗 + 重试余量）

#### Scenario: 旧 C端 不误清凭据

- **WHEN** 旧版 C端（无此契约感知）收到 code=3
- **THEN** 其按未知 code 走未登录兜底；本地 token 不被清除

### Requirement: pair/exchange 排除面

- `pair/exchange` 的失败响应 SHALL NOT 携带 outdated 信号（统一 `_fail()` 形态不变）——信号只经 authorize/check-auth 两端点承载。
- SHALL 以契约测试固化（pairing 全错误分支响应形状断言）。

#### Scenario: pair 失败不泄漏信号语义

- **WHEN** pair/exchange 因密钥不符失败
- **THEN** 响应形态与现状一致，不含 client_outdated/latest_version 字段
