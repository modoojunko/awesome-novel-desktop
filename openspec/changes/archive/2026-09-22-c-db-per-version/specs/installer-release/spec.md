## MODIFIED Requirements

### Requirement: release.json 烘焙版本与检测地址

打包工作流在生成 release.json 时 SHALL 额外烘入四个键：`client_version`（`v*` 标签构建写去前缀的真实版本号；PR/手动构建写 `dev`）、`client_update_url`（主检测地址，取仓库 Variable `CLIENT_DOWNLOAD_BASE` 拼接 `latest.json`，未配置时默认 `https://www.awesomenovel.com/download/latest.json`）、`client_update_url_fallback`（兜底检测地址，取 Variable `CLIENT_DOWNLOAD_BASE_FALLBACK` 拼接 `latest.json`，未配置时默认云托管静态托管直连域 `https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/download/latest.json`）与 `components`（组件清单对象，至少含 `db_filename`＝该版本运行时会打开的库文件名、`backup_format_version`＝备份包格式契约版本；两者 MUST 由构建期从后端单源读取——如 `client/backend/backup/format.py` 的 `FORMAT_VERSION` 与库文件名单源派生——SHALL NOT 在流水线脚本内手抄取值）。各键随既有 datas 通道分发，打包冒烟断言 MUST 覆盖这些键真实烘进产物且 `components` 与后端单源逐字一致。换任一域名 MUST 只改仓库 Variable，不需要改任何代码；新增 `components` MUST NOT 改变既有键的语义与消费方契约。

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
