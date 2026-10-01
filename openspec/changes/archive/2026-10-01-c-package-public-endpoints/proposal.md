## Why

正式安装包（v0.23/v0.24/v0.25 实测）里 `release.json` 从未烘入 `public_server_api`，打包端授权页 URL 回落到 API 基址（云托管直连域），剥掉 `/api` 开 `/auth` 后落在只跑后端 API 的源上＝**404**（2026-10-01 实测；授权页自 #330 起由 S端 web 唯一承载）。新装用户点「登录」→ 浏览器打开 404 → 首次登录死路；已配对设备因静默自愈（check-auth＋pair/exchange）不经过授权页而无感。附带：包内 `portal_url` 默认值是代码常量里的 test 环境 webapps 域名，会员页/客服页跳转落到错误环境。demo/本地开发因显式 env 注入不受影响，故问题只在打包链。

## What Changes

- `release.json` 烘焙键族补齐 S端 公开地址族：新增 `public_server_api`（宿主可访问 S端 地址，授权页 URL 的取值源）与 `portal_url`（会员/客服页跳转源）两个键；同批把已烘未立规的 `server_api_base`／`server_api_fallback` 一并写入 Requirement 文本（行为不变，补 spec 同步）。
- 打包工作流 Generate release.json 步骤注入对应 env（`RELEASE_PUBLIC_SERVER_API`／`RELEASE_PORTAL_URL`，仓库 Variable 可覆盖、带生产默认值），与既有 `RELEASE_SERVER_API_BASE` 同模式。
- 打包端运行时注入：`pywebview_app` 从 release.json 读 `portal_url` 注入 env `PORTAL_URL`（`public_server_api` 的注入链已存在，无需改）；`load_or_create_config` 对 `portal_url` 增加与 `server_api` 同款「env 显式设置即对齐落盘」语义——治老包（v0.23–v0.25）已把 test 域名写进用户 config.json 的存量残值。
- 打包冒烟断言（`release_json_assert.py`）覆盖两个新键：存在、`https://` 形态。
- 非目标：不改授权页构造契约（`device-auth-page` 已钉死 `{web_origin}/auth`）；不动 demo/本地开发的 env 注入拓扑；不处理 S端 侧任何行为。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `installer-release`: 「release.json 烘焙版本与检测地址」Requirement 扩展为「烘焙版本、检测地址与 S端 公开地址族」——新增 `public_server_api`／`portal_url` 烘焙义务、`server_api_base`／`server_api_fallback` 补立规、冒烟断言范围扩大、换域名零代码口径延伸到新键。

## Impact

- `client/backend/scripts/release_json_generate.py`（generate() 两键＋https 断言）
- `client/backend/scripts/release_json_assert.py`（冒烟断言两键）
- `client/backend/config.py`（`RELEASE_OVERRIDE_KEYS` 白名单补 `portal_url`）
- `client/packaging/build/pywebview_app.py`（`PORTAL_URL` 注入一行）
- `client/backend/auth_local/service.py`（`load_or_create_config` portal 对齐）
- `.github/workflows/client-package.yml`（两个新 env）
- 测试：`tests/test_release_json_generate.py`、`tests/test_release_json_ci_assert.py`、config/auth_local 相关单测补 portal 对齐用例
- 发布面：修复随下个 tag 版本（v0.25.1）出包生效；已发布的 v0.25 需在 Release 页标注已知问题
