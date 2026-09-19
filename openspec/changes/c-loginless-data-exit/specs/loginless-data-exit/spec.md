## Purpose

C端 免登录数据出口：登录被拒（服务端协议升级/服务异常/账号问题）任何形态下，用户都能把本地全部作品打包带走；登录页就地升级引导让「需要更新」的用户一步拿到新版本。登录墙保护生成服务，不保护用户硬盘上的文件。

## ADDED Requirements

### Requirement: 免登导出（资产包）

- `POST /api/backup/export/start` 与 `GET /api/backup/export/status` SHALL 免登录可用，kind 限 `backup`/`single`；免登态 `include_config` SHALL 由服务端强制为 false（请求体取值丢弃）。
- 免登态导出 SHALL 为**整库无主化口径**：不按 user_id 过滤、不要求 User 行存在（免登导出在没有本地用户行的机器上 SHALL 成功，而非 500）；配置段（api_configs/users）不导。
- 配置包导出（含 api_key 明文）、`import/*` 全家、`config/preview` SHALL 维持登录墙（永不免登）。
- 免登与登录态导出 SHALL 共用 job_runner 单飞（跨 kind 互斥，409 语义复用）。

#### Scenario: 未登录整机导出

- **WHEN** 无任何会话的客户端调用 export/start {kind:"backup", target_dir:"~/out"}
- **THEN** 导出全部书籍（无视归属）；包内无配置段；status 轮询至完成

#### Scenario: 免登态请求配置包被拒

- **WHEN** 免登调用 export/start 且请求体 include_config=true
- **THEN** 服务端强制 false 继续资产包导出（或 422 明示不含配置——实现取一，spec 以「永不导出」为准）

#### Scenario: import 永不免登

- **WHEN** 免登调用 import/parse 或 import/persist
- **THEN** 401

### Requirement: 免登面三层防护

- 免登端点 SHALL 限回环来源（client.host ∈ 127.0.0.1/::1）；非回环请求 SHALL 拒绝。
- CORS SHALL 收窄：生产同源（SPA 由本进程伺服）＋开发态白名单；`allow_origins=["*"]` SHALL NOT 保留。
- 导出目标路径（`target_dir` 与 `target_file` 整路径）SHALL 拒绝落在 DATA_ROOT 内。

#### Scenario: 浏览器 drive-by 不可达

- **WHEN** 恶意网页从浏览器向 localhost 发 JSON POST（触发 CORS 预检）
- **THEN** 预检不批、响应不可读——读写两端封死

#### Scenario: 目标路径守卫

- **WHEN** export 请求 target_dir 或 single 的 target_file 落在 DATA_ROOT 内
- **THEN** 拒绝并明示换目录（登录态同样生效）

### Requirement: 登录页升级引导（UpgradeGate）

- 登录页在收到 check-auth 的 client_outdated 载荷（s-client-outdated-signal 契约）SHALL 就地以升级卡替换主按钮区：首答句「你的作品都在这台电脑上」＋本地库可核对计数（N 本书 · M 字）；主按钮「去下载新版」（真实锚点新窗）；次按钮「先备份作品」打开免登导出弹窗。
- 升级卡触发 SHALL 为双信号 OR：①check-auth client_outdated；②本地 `/api/update-check` 报 has_update 且当前处于登录受阻态。S端 不可达（code=-1）SHALL NOT 渲染升级卡。
- 下载地址 SHALL 经三级回落单源（S端 hint → 本地 update-check 缓存 → 官网常量），「复制下载地址」常备。
- 登录页 SHALL 常驻免登导出入口（未受阻态可见：「不登录也能备份作品」文字链）。
- 升级卡文案两场景分档：确需更新（出示版本事实对照「当前 vX · 需更新至 vY 起」）／服务异常（「现在连不上登录服务…不是你的操作有问题」，不出示版本对照）；无法证实的信号一律归服务异常档。

#### Scenario: 协议失配就地引导

- **WHEN** 轮询 check-auth 返回 code=3 + client_outdated
- **THEN** 登录页主按钮区替换为升级卡；轮询停止；「先备份作品」可用

#### Scenario: 服务不可达不误闸

- **WHEN** check-auth 返回 code=-1（S端 不可达）
- **THEN** 维持常规登录态与重试文案，不渲染升级卡

#### Scenario: 未点登录也能发现更新

- **WHEN** 用户停在登录页未点登录，本地 update-check 报 has_update
- **THEN** 登录页呈现升级引导入口（第二信号兜底，不依赖 authorize 拒绝先发生）
