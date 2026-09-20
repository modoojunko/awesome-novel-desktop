# installer-release Delta: relicense-proprietary

## MODIFIED Requirements

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

## ADDED Requirements

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
