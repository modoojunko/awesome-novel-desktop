# installer-release Specification

## Purpose
让公网用户能真正下到 C端 客户端：v* 标签推送自动把双平台安装包发布到 GitHub Releases 并提供不随版本号变化的稳定直链，S端 落地页的下载入口指向正确地址且覆盖 Windows 与 macOS 双平台。

## Requirements

### Requirement: v* 标签自动发布双平台安装包

系统 SHALL 在推送 `v*` 标签时自动构建 Windows 安装包与 macOS DMG，并把两者挂载到该标签对应的 GitHub Release 上。每个此类 Release 的资产 MUST 同时具备两种平台的安装包；缺任一平台视同发布失败。非标签触发（如 PR、手动 dispatch）的构建 SHALL 只产出工作流工件（artifact），MUST NOT 创建或修改任何 GitHub Release。

#### Scenario: 推送 v0.1 触发首个公开版
- **WHEN** 向仓库推送标签 `v0.1`
- **THEN** 构建完成后出现同名 GitHub Release，其资产同时包含带版本号的 `AI_Novel_Setup_v0.1.exe` 与 `AI_Novel_mac_0.1.dmg`

#### Scenario: PR 构建不对外发布
- **WHEN** 打包流水线由 PR 或手动 dispatch 触发
- **THEN** 仅生成可下载的 workflow artifact，Releases 页无新增、无改动

### Requirement: 落地页下载入口

S端 落地页 SHALL 提供可达的客户端下载入口：未登录态 Hero 区 MUST 呈现单枚主按钮「免费下载」，点击后打开**下载弹窗**（复用既有浮层组件）。弹窗打开时 SHALL 立即同源获取 `download/latest.json` 解析最新版本，并渲染：版本 pill、两枚平台下载按钮（`下载 Windows 版` primary / `下载 macOS 版` secondary，均动词起句，href 分别指向静态托管的 `download/v<VER>/AI_Novel_Setup_v<VER>.exe` 与 `download/v<VER>/AI_Novel_mac_v<VER>.dmg`，双平台文件名统一带小写 `v` 前缀）、macOS 首开提示、「查看更新说明 →」次级链接（指向本次展示版本的 `download/v<VER>/notes.html`，同源静态托管，随发版流水线必产）与一行许可同意微文案「下载即表示同意《最终用户许可协议》」（链接指向官网 EULA 公示页）。弹窗 MUST 具备三态：加载中（骨架占位）、成功（info 语气版本 pill）、降级（fetch 失败时代码兜底版本照常可下，warn 语气 pill 明示）；**降级态 MUST NOT 渲染「查看更新说明」等版本相关次级链接**（兜底版本不保证仍在托管保留集内，warn pill 已明示非最新），双平台下载按钮保留。弹窗内用户所见版本 MUST 与点击所下文件名的版本一致。页面其余区域 MUST NOT 承诺具体版本号（版本展示收敛到弹窗）。`download/latest.json` 的版本号 MUST 为唯一线上事实源；前端代码内的版本常量 SHALL 仅为请求失败时的兜底。已登录态 SHALL 保持「进入控制台」主操作不变，不渲染下载入口。激活指引第 1 步 MUST 同时写明双平台获取方式。全站 MUST NOT 出现指向已私有仓库的外链或引导用户前往 GitHub Releases 获取安装包的文案（下载获取口径一律为官网静态托管）。

#### Scenario: 未登录访客点击 Windows 下载按钮
- **WHEN** 未登录访客打开下载弹窗并点击「下载 Windows 版」
- **THEN** 浏览器开始下载 `www.awesomenovel.com/download/v<N>/AI_Novel_Setup_v<N>.exe`，其中 `<N>` 与弹窗内展示的版本 pill 一致

#### Scenario: 未登录访客点击 macOS 下载按钮
- **WHEN** 未登录访客打开下载弹窗并点击「下载 macOS 版」
- **THEN** 浏览器开始下载 `www.awesomenovel.com/download/v<N>/AI_Novel_mac_v<N>.dmg`，版本同弹窗所见

#### Scenario: 弹窗打开即取最新版
- **WHEN** 访客在落地页停留期间线上发布了新版本，其后才点击「免费下载」
- **THEN** 弹窗渲染的是 latest.json 里的最新版本，点击下载得到最新版安装包

#### Scenario: 弹窗获取失败降级
- **WHEN** 弹窗内 latest.json 请求失败或超时
- **THEN** 弹窗以代码兜底版本渲染并可正常下载，版本 pill 使用 warn 语气明示"未能获取最新版"，不阻塞下载

#### Scenario: 版本号单一事实源
- **WHEN** 需要更新落地页所指客户端版本
- **THEN** 仅更新 `download/latest.json` 一处即全站生效，无需前端发版；代码常量仅作请求失败兜底

#### Scenario: 访客从落地页进入下载
- **WHEN** 访客点击弹窗内「查看更新说明 →」次级链接
- **THEN** 新开同源 `https://www.awesomenovel.com/download/v<N>/notes.html`（`<N>` 与弹窗版本 pill 一致），页面存在（非 404），正文含该版本更新内容与双平台安装包直链

#### Scenario: 降级态不渲染版本相关次级链接
- **WHEN** latest.json 请求失败，弹窗以代码兜底版本渲染
- **THEN** 弹窗不出现「查看更新说明」链接，版本 pill 以 warn 语气明示非最新，双平台下载按钮与许可同意微文案保留

#### Scenario: 副行双平台口径
- **WHEN** 访客阅读 Hero 下载区副行文案
- **THEN** 文案同时提及 Windows 与 macOS，且不出现具体版本号字样（版本展示收敛到弹窗）

#### Scenario: 已登录访客的 Hero 主操作
- **WHEN** 已登录用户打开落地页
- **THEN** Hero 主操作为「进入控制台」，不出现下载入口

#### Scenario: 激活指引双平台口径
- **WHEN** 访客阅读激活指引「下载安装」步骤
- **THEN** 文案同时覆盖 Windows 安装包与 macOS DMG 的获取说明，未遗留"仅 Windows"表述，且不出现引导前往 GitHub Releases 的字样

### Requirement: 安装包国内分发

系统 SHALL 在 `v*` 标签发版时把双平台安装包转存到静态托管（CloudBase Hosting）的 `/download/v<VER>/` 目录，文件名与 GitHub Release 资产 1:1（`AI_Novel_Setup_v<VER>.exe` / `AI_Novel_mac_v<VER>.dmg`）。转存完成后系统 SHALL 更新 `download/latest.json`，该文件 MUST 是落地页下载弹窗与 C端 更新检测共同的唯一线上事实源；更新它 MUST NOT 依赖任何前端重新发版。latest.json 载荷契约：`version` MUST 必写；`notes`（一句话更新摘要，取 tag 附注首行自动写入，无附注时可省略）与 `min_version`（强更门槛，本期仅预留字段、客户端不实现强更逻辑）为可选键，缺省 MUST 可省略。所有 latest.json 消费方（落地页下载弹窗、C端 更新检测）MUST 同时兼容"仅 version"的最小载荷与含可选键的完整载荷。转存或 latest.json 更新失败 MUST 使发版流水线失败，不得静默。已发布的版本目录 MUST 只增不改（版本化路径永不覆盖，使长缓存安全）。

#### Scenario: 发版后国内直链可下载
- **WHEN** 任意 `v*` 标签发版流水线成功结束
- **THEN** `https://www.awesomenovel.com/download/v<VER>/AI_Novel_Setup_v<VER>.exe` 返回 200，且字节数与 GitHub Release 同名资产一致（dmg 同理）

#### Scenario: latest.json 即时生效
- **WHEN** `download/latest.json` 的版本号被更新（CI 自动或人工）
- **THEN** 落地页下载弹窗与已安装 C端 的下一次检测解析到的版本随之变化，无需任何前端重新发版

#### Scenario: 最小载荷向后兼容

- **WHEN** latest.json 仅含 `{"version": "0.13"}`（无 notes/min_version）
- **THEN** 落地页下载弹窗与 C端 更新检测均正常工作，不因缺失可选键报错

#### Scenario: 转存失败不静默
- **WHEN** 转存上传或 latest.json 写入的校验未通过
- **THEN** 发版流水线以失败结束并给出明确错误，GitHub Release 可能已建但流水线状态不得为绿

### Requirement: release.json 烘焙版本与检测地址

打包工作流在生成 release.json 时 SHALL 额外烘入八个键：既有四键 `client_version`（`v*` 标签构建写去前缀的真实版本号；PR/手动构建写 `dev`）、`client_update_url`（主检测地址，取仓库 Variable `CLIENT_DOWNLOAD_BASE` 拼接 `latest.json`，未配置时默认 `https://www.awesomenovel.com/download/latest.json`）、`client_update_url_fallback`（兜底检测地址，取仓库 Variable `CLIENT_DOWNLOAD_BASE_FALLBACK` 拼接 `latest.json`，未配置时默认云托管静态托管直连域 `https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/download/latest.json`）与 `components`（组件清单对象，至少含 `db_filename`＝该版本运行时会打开的库文件名、`backup_format_version`＝备份包格式契约版本；两者 MUST 由构建期从后端单源读取——如 `client/backend/backup/format.py` 的 `FORMAT_VERSION` 与库文件名单源派生——SHALL NOT 在流水线脚本内手抄取值），以及本次补齐的 S端 公开地址族四键 `server_api_base`（C端 后端连 S端 API 的基址，默认云托管直连域 `https://novel-s-server-297265-7-1468883265.sh.run.tcloudbase.com/api`）、`server_api_fallback`（S端 兜底基址，默认与主基址一致）、`public_server_api`（宿主浏览器可访问的 S端 地址——授权页 URL 与前端公开跳转的取值源，MUST 指向同时承载 S端 web 授权页与 `/api` 反代的源，默认 `https://www.awesomenovel.com/api`，取仓库 Variable `CLIENT_PUBLIC_SERVER_API` 可覆盖）与 `portal_url`（会员页/客服页等公开跳转的门户源，默认 `https://www.awesomenovel.com`，取仓库 Variable `CLIENT_PORTAL_URL` 可覆盖）。S端 公开地址族四键的取值 MUST 由构建期 env 注入，SHALL NOT 在流水线脚本内手抄；各键随既有 datas 通道分发，打包冒烟断言 MUST 覆盖全部键真实烘进产物、`components` 与后端单源逐字一致、地址族四键为 `https://` 形态。换任一域名 MUST 只改仓库 Variable（或对应构建 env），不需要改任何代码；新增地址族键 MUST NOT 改变既有键的语义与消费方契约。打包端运行时 SHALL 以 release.json 烘入值为准把用户 `config.json` 的 `server_api` 与 `portal_url` 对齐落盘（env 显式设置即对齐，治旧版本包写入的存量残值）；本地开发与容器 demo 无 release.json，MUST 保持既有行为不变。

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
- **THEN** 产物内 release.json 含 `public_server_api`（默认 `https://www.awesomenovel.com/api`）、`portal_url`（默认 `https://www.awesomenovel.com`）、`server_api_base` 与 `server_api_fallback`（默认云托管直连域）四键，均为 `https://` 形态；冒烟断言在任一键缺失或非 https 时使构建失败

#### Scenario: 打包端授权页落在 S端 web 源

- **WHEN** 全新安装的打包端在登录页点「登录」
- **THEN** 打开的授权页地址为 `public_server_api` 剥掉尾部 `/api` 后的 web 源上的 `/auth`（如 `https://www.awesomenovel.com/auth?…`），落在承载授权页的 S端 web 源上，MUST NOT 落在仅承载 API 的云托管直连源（该源 `/auth` 为 404）

#### Scenario: portal_url 存量残值对齐

- **WHEN** 打包端启动且 release.json 烘有 `portal_url`，而用户 config.json 中残留旧包写入的 portal 地址
- **THEN** 配置加载时 portal_url 被对齐为烘入值并落盘，会员页/客服页跳转指向烘入门户源；dev/本地开发与容器 demo 无 release.json，portal_url 保持既有默认与手工值不变

### Requirement: 版本更新说明页

发版流水线 SHALL 为每个 `v*` 版本生成并转存更新说明页 `download/v<VER>/notes.html` 到静态托管（与安装包同目录，遵循版本化只增不改）。页面 MUST 含版本号、更新内容与双平台安装包下载直链。更新内容来源 MUST 按优先级取：tag 附注消息（annotated tag message）→ 上一版本以来的提交摘要 → 通用兜底文案；无 tag 附注 MUST NOT 使发版失败（回退生成）。页面 MUST 无需任何前端发版即可直接访问。

#### Scenario: 带 tag 附注发版生成说明页

- **WHEN** 发版 tag 为附注标签且附注含更新说明
- **THEN** `https://www.awesomenovel.com/download/v<VER>/notes.html` 返回 200，正文为附注内容并含双平台安装包直链

#### Scenario: 轻量 tag 回退不阻断

- **WHEN** 发版 tag 无附注消息
- **THEN** 说明页以提交摘要或通用兜底文案生成，发版流水线不因此失败

### Requirement: 托管旧版本自动清理

发版流水线 SHALL 在「发布到静态托管且校验全绿」之后自动清理静态托管上的历史版本目录：对全部 `v*` 标签按版本语义排序，保留最近 2 个版本的 `download/v<VER>/` 目录，将其余更老版本目录连同其内全部文件（安装包与 notes.html）一并删除。清理 MUST NOT 触碰 `download/latest.json` 与保留集内的任何版本目录；刚发布的版本 MUST 始终落在保留集内。执行真删前 MUST 先产出删除预览日志。删除目标不存在时（从未上过托管的标签）SHALL 容错跳过。清理环节任何失败 SHALL 降级为流水线告警（warning），MUST NOT 使发版流水线失败——发布此时已成功，历史目录回收可由下个版本自动重试。发布转存或校验失败的场合 MUST NOT 执行清理（旧版本是当时唯一可下载来源，不得先删后建）。本条与「已发布的版本目录 MUST 只增不改」并存：该条款约束发布写入永不覆盖，本条款约束无人引用的历史目录按保留策略回收。

#### Scenario: 发版成功后清理超保留数旧版
- **WHEN** `v0.14` 发版流水线发布与校验全部成功
- **THEN** 托管保留 `download/v0.14/` 与 `download/v0.13/`，更老的 `download/v0.12/` 及之前版本目录被删除，`download/latest.json` 完好且仍指 `0.14`

#### Scenario: 从未上托管的标签容错
- **WHEN** 待删集合中出现从未上传过托管的标签（如本地遗留的 v0.4）
- **THEN** 清理步骤对其仅记录告警并跳过，不失败、不中断其余版本的清理

#### Scenario: 清理失败不阻塞发版
- **WHEN** 清理环节的托管删除请求失败
- **THEN** 发版流水线整体仍为成功，日志中出现明确告警，下个版本发版时自动重试清理

#### Scenario: 发布失败不执行清理
- **WHEN** 发版流水线在转存上传或发布校验环节失败
- **THEN** 清理步骤不执行，既有旧版本目录原样保留

#### Scenario: 真删前有预览
- **WHEN** 清理步骤执行
- **THEN** 日志中先出现本次待删版本目录的预览清单，再出现实际删除结果

### Requirement: Windows 发布者元数据署名经营主体

Windows 分发物的发布者展示面 SHALL 署名经营主体（取值与 `brand/brand.json` 的 `company` 键同源）：① 桌面 exe 的 Windows 版本资源——文件属性「详细信息」的公司/版权字段与任务管理器「发布者」列显示主体名，`ProductName`/`FileDescription` 取品牌源（`name`/`name`+`nameEn`），文件版本与同次构建的安装包版本同源（tag 去 `v` 前缀）；② Inno 安装器 `AppPublisher`——「设置 → 应用」与控制面板卸载列表的发布者列、安装器自身版本资源显示主体名。打包流程在品牌源缺少 `company` 键时 MUST 显式失败并给出可定位的报错，MUST NOT 静默产出「发布者: 未知」的安装包。版本资源文件为构建期生成产物，MUST NOT 提交仓库。边界：UAC 提升与首次运行 SmartScreen 弹窗展示的发布者由 Authenticode 证书主体决定，不在本 Requirement 范围内。

#### Scenario: exe 属性页署名主体

- **WHEN** 用户在 Windows 右键安装后的 exe 查看属性「详细信息」，或在任务管理器「详细信息」页查看发布者列
- **THEN** 公司/发布者显示「星纬（海口）投资有限公司」，产品名称为「爱小说」，文件版本与该包 tag 版本一致

#### Scenario: 卸载列表署名主体

- **WHEN** 用户安装后在「设置 → 应用」列表查看该应用
- **THEN** 发布者显示「星纬（海口）投资有限公司」

#### Scenario: 缺主体名拒绝构建

- **WHEN** 品牌源缺失 `company` 键或其为空白串时执行打包
- **THEN** 打包流程以明确报错终止（指出缺失字段与补救方式），不产出任何安装包产物

### Requirement: 安装器许可协议页

Windows 安装器 SHALL 在交互式安装向导中先展示《最终用户许可协议》（EULA）全文，用户 MUST 点击「我接受」后方可继续安装；未接受时 MUST NOT 进入安装步骤。许可页展示的文本 MUST 与仓库根 `LICENSE` 保持单一事实源（打包链路直接引用该文件，MUST NOT 维护第二份副本），且 MUST 以 UTF-8 带 BOM 编码保证中文无乱码。静默/命令行安装（/SILENT、/VERYSILENT）跳过许可页的行为 MUST 在 EULA 文本中以「静默安装视同接受」条款覆盖。macOS 分发渠道无安装期点击页（平台惯例），EULA 以官网公示与随包文本方式覆盖（见「EULA 官网公示」「安装包随附许可与第三方声明」）。

#### Scenario: 未接受协议无法安装
- **WHEN** 用户运行 Windows 安装器进入许可协议页，未选择「我接受」
- **THEN** 安装向导不提供继续途径，安装未开始

#### Scenario: 许可页内容与 LICENSE 一致且中文可读
- **WHEN** 用户在安装器许可协议页阅读协议文本
- **THEN** 显示的是根 `LICENSE` 的 EULA 全文，署名为星纬（海口）投资有限公司，中文无乱码

#### Scenario: 静默安装视同接受
- **WHEN** 用户以 /SILENT 参数运行 Windows 安装器
- **THEN** 安装直接完成不弹出许可页，该次安装按 EULA「静默安装视同接受」条款处理

### Requirement: 安装包随附许可与第三方声明

每个对外分发的安装包 SHALL 随附两份文本：EULA（与根 `LICENSE` 同源）与《第三方开源声明》。Windows 安装后两份文件 MUST 位于安装目录根（用户可直接打开）；macOS 分发包 MUST 在 .app 包内资源目录随附两份文件，且 DMG 根目录（与 .app 并排）MUST 有一份可直读的副本。第三方开源声明 MUST 至少包含：certifi 的 MPL-2.0 许可证全文（未修改分发的合规要求）、PyInstaller bootloader「GPLv2＋允许闭源商用分发的官方例外」声明、其余随包第三方组件的宽松许可（MIT/BSD/Apache 等）归属清单。第三方声明 MUST NOT 声明本项目自身以 GPL 或任何开源许可证授权。

#### Scenario: Windows 安装目录根含两份文本
- **WHEN** 用户在 Windows 完成安装并打开安装目录
- **THEN** 安装目录根存在 EULA 文本与《第三方开源声明》两份文件，内容可读

#### Scenario: macOS DMG 根含两份文本副本
- **WHEN** 用户挂载 macOS DMG
- **THEN** DMG 根目录（与 .app 并排）存在两份文本文件，.app 包内资源目录亦有随附副本

#### Scenario: 第三方声明满足 MPL-2.0 合规
- **WHEN** 审阅第三方开源声明内容
- **THEN** certifi 的 MPL-2.0 许可证全文在列，且无任何将本项目自身描述为 GPL/开源授权的表述

### Requirement: EULA 官网公示

官网法律信息区 SHALL 公示《最终用户许可协议》全文：发布页路径挂于既有法律文件目录（`/legal/`）并在页脚法律链接区可达；页面内容 MUST 为仓库根 `LICENSE` 的构建期原样复制（MUST NOT 手工维护第二份内容源）。下载弹窗 MUST 含「下载即表示同意《最终用户许可协议》」微文案并以链接指向该公示页。

#### Scenario: 官网 EULA 页可达且与 LICENSE 同源
- **WHEN** 访客从官网页脚法律链接区打开 EULA 页
- **THEN** 页面展示 EULA 全文（署名星纬（海口）投资有限公司），内容与仓库根 `LICENSE` 一致

#### Scenario: 下载弹窗含同意微文案
- **WHEN** 访客打开下载弹窗
- **THEN** 弹窗内可见「下载即表示同意《最终用户许可协议》」及指向官网 EULA 公示页的链接
