## MODIFIED Requirements

### Requirement: release.json 烘焙版本与检测地址

打包工作流在生成 release.json 时 SHALL 额外烘入八个键：既有四键 `client_version`（`v*` 标签构建写去前缀的真实版本号；PR/手动构建写 `dev`）、`client_update_url`（主检测地址，取仓库 Variable `CLIENT_DOWNLOAD_BASE` 拼接 `latest.json`，未配置时默认 `https://www.awesomenovel.com/download/latest.json`）、`client_update_url_fallback`（兜底检测地址，取仓库 Variable `CLIENT_DOWNLOAD_BASE_FALLBACK` 拼接 `latest.json`，未配置时默认云托管静态托管直连域 `https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/download/latest.json`）与 `components`（组件清单对象，至少含 `db_filename`＝该版本运行时会打开的库文件名、`backup_format_version`＝备份包格式契约版本；两者 MUST 由构建期从后端单源读取——如 `client/backend/backup/format.py` 的 `FORMAT_VERSION` 与库文件名单源派生——SHALL NOT 在流水线脚本内手抄取值），以及 S端 公开地址族四键 `server_api_base`（C端 后端连 S端 API 的基址，默认自定义域名 `https://www.awesomenovel.com/api`，取仓库 Variable `CLIENT_SERVER_API_BASE` 可覆盖）、`server_api_fallback`（S端 兜底基址——自定义域名解析抖动时运行时自动切换的直连通道，默认云托管直连域 `https://novel-s-server-297265-7-1468883265.sh.run.tcloudbase.com/api`，取仓库 Variable `CLIENT_SERVER_API_FALLBACK` 可覆盖，SHALL 与主基址归一化后不同址）、`public_server_api`（宿主浏览器可访问的 S端 地址——授权页 URL 与前端公开跳转的取值源，MUST 指向同时承载 S端 web 授权页与 `/api` 反代的源，默认 `https://www.awesomenovel.com/api`，取仓库 Variable `CLIENT_PUBLIC_SERVER_API` 可覆盖）与 `portal_url`（会员页/客服页等公开跳转的门户源，默认 `https://www.awesomenovel.com`，取仓库 Variable `CLIENT_PORTAL_URL` 可覆盖）。S端 公开地址族四键的取值 MUST 由构建期 env 注入，SHALL NOT 在流水线脚本内手抄；各键随既有 datas 通道分发，打包冒烟断言 MUST 覆盖全部键真实烘进产物、`components` 与后端单源逐字一致、地址族四键为 `https://` 形态、`server_api_base` 与 `server_api_fallback` **归一化后不同址**——主/兜底同址＝运行时 `call_server_api` 去重后无兜底，MUST 在生成期（`release_json_generate`）与产物冒烟（`release_json_assert`）双闸判红（归一化＝尾斜杠 rstrip＋裸域名补 `/api`、自定义子路径不动，与运行时去重口径同语义，生成/产物/测试共用同一零依赖单源）。换任一域名 MUST 只改仓库 Variable（或对应构建 env），不需要改任何代码；新增地址族键 MUST NOT 改变既有键的语义与消费方契约。打包端运行时 SHALL 以 release.json 烘入值为准把用户 `config.json` 的 `server_api` 与 `portal_url` 对齐落盘（env 显式设置即对齐，治旧版本包写入的存量残值）；本地开发与容器 demo 无 release.json，MUST 保持既有行为不变。

#### Scenario: tag 构建烘入真实版本

- **WHEN** `v0.13` 标签触发出包
- **THEN** 产物内 release.json 含 `"client_version": "0.13"`、指向主下载域 latest.json 的 `client_update_url` 与指向云托管直连域的 `client_update_url_fallback`

#### Scenario: PR 构建写 dev

- **WHEN** PR 触发打包验证（非 tag）
- **THEN** 产物内 release.json 的 `client_version` 为 `dev`，安装该包的应用跳过更新检测

#### Scenario: 换域名零代码

- **WHEN** 仓库 Variable `CLIENT_DOWNLOAD_BASE` 或 `CLIENT_DOWNLOAD_BASE_FALLBACK` 变更
- **THEN** 此后构建的安装包检测地址指向新值，仓库代码无改动

#### Scenario: 组件清单随版本烘入

- **WHEN** 任一版本出包
- **THEN** 产物内 `release.json.components` 的 `db_filename` 等于该版本运行时会打开的库文件名（`v*` 构建为 `novel-v{client_version}.db`），`backup_format_version` 等于后端单源当前值；冒烟断言在任一键缺失或与单源不一致时使构建失败

#### Scenario: S端 公开地址族随包烘入

- **WHEN** 任一版本出包（tag 与 PR 构建同口径）
- **THEN** 产物内 release.json 含 `public_server_api`（默认 `https://www.awesomenovel.com/api`）、`portal_url`（默认 `https://www.awesomenovel.com`）、`server_api_base`（默认 `https://www.awesomenovel.com/api`）与 `server_api_fallback`（默认云托管直连域）四键，均为 `https://` 形态；冒烟断言在任一键缺失或非 https 时使构建失败

#### Scenario: 主/兜底同址判红（生成/产物双闸）

- **WHEN** 构建期注入的 `server_api_base` 与 `server_api_fallback` 归一化后同值（含完全相同、仅差尾斜杠、一方为裸域名等变体）
- **THEN** 生成步（`release_json_generate`）即失败转红并点名归一化后同址，产物冒烟断言（`release_json_assert`）以同一归一化单源复判同址同样转红；构建不产出可发布安装包

#### Scenario: 打包端授权页落在 S端 web 源

- **WHEN** 全新安装的打包端在登录页点「登录」
- **THEN** 打开的授权页地址为 `public_server_api` 剥掉尾部 `/api` 后的 web 源上的 `/auth`（如 `https://www.awesomenovel.com/auth?…`），落在承载授权页的 S端 web 源上，MUST NOT 落在仅承载 API 的云托管直连源（该源 `/auth` 为 404）

#### Scenario: portal_url 存量残值对齐

- **WHEN** 打包端启动且 release.json 烘有 `portal_url`，而用户 config.json 中残留旧包写入的 portal 地址
- **THEN** 配置加载时 portal_url 被对齐为烘入值并落盘，会员页/客服页跳转指向烘入门户源；dev/本地开发与容器 demo 无 release.json，portal_url 保持既有默认与手工值不变
