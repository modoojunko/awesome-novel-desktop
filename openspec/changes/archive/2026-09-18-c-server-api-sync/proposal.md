## Why

C端 后端的 S端 地址解析链是 `config.json.server_api` → env `SERVER_API_BASE` → 默认，而 `load_or_create_config` 里的同步逻辑是「**仅当 config.server_api 为空时**才把 env 写入 config」（`auth_local/service.py::load_or_create_config` 的同步块）——**写入一次后永不再更新**。后果（2026-09-18 本地实锤）：本地栈把 `.env` 的 `SERVER_API_BASE` 从本地 S端 切到生产后，config 里残留的旧地址（指向已停的本地 S端 容器）依旧赢得解析，登录授权页能开、但凭证回传/校验全部打向死地址，用户卡死在登录页进不了主页。打包端同构风险：若某版本 release.json 变更 S端 域名，老用户升级后 config 残值同样遮蔽新域名（域名迁移路径自动失效）。

## What Changes

- **同步规则改为「env 为部署真值」**：`SERVER_API_BASE` 显式设置且与 `config.server_api` 不一致时，启动对齐 config 到 env 并持久化（幂等）；env 未设置时 config 原样保留（不覆盖手工配置）。
- `public_server_api` / `server_api_fallback` 不动（现无 config 写入方，读链本就 env 兜底）。
- 无界面改动；行为变化仅「部署配置变更能被运行时跟随」，无外部契约面。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——本地配置解析的健壮性修复，不涉及任何 spec 既有 Requirement 的行为语义；`.openspec.yaml` 已声明 skip_specs，先例 `2026-09-05-c-novel-backup-import-f821-fix`。）

## Impact

- 代码：`client/backend/auth_local/service.py::load_or_create_config` 单处同步块（约 4 行）。
- 测试：新增 `test_server_api_sync.py`（隔离 CONFIG_FILE 的行为用例，先红后绿）。
- 兼容性：packaged 端 release.json 驱动 env 恒定 → config 恒等 → 零变化；域名迁移场景由「手工修 config」变为自动对齐（改进）。本机数据面已修（config.json 实改＋容器重启），本 change 防复发。
