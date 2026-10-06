# Ops：Windows 代码签名（用户装包时的「发布者: 未知」）

> 症状：用户双击 `AwesomeNovel_Setup_v*.exe`，Windows 弹蓝色「Windows 已保护你的电脑 /
> Microsoft Defender SmartScreen 阻止了无法识别的应用启动」，应用信息里写着
> **发行者：发布者未知**。点「更多信息 → 仍要运行」能继续，但第一印象是「这软件有风险」。

## 一、根因：安装包没有 Authenticode 代码签名（不是 bug，也修不了代码）

SmartScreen 对**从网上下载的文件**（带 Mark-of-the-Web 标记）做两件事：查文件信誉、
查签名者信誉。我们的安装包与程序本体从来没做过代码签名（只有 exe 的*版本资源*写了
公司名——那只影响「属性 → 详细信息」页，不是签名），所以 Windows 只能报「发布者未知」。

**没有任何代码改动能去掉这个提示**：它是操作系统对「未签名/无信誉」产物的判定。
唯一的解法是买证书、把安装包签上——签完 Windows 才会显示发行者名称，并逐步放行。
2026-10-06 起签名链路已在仓库落地（本地脚本 + CI + 校验闸门），**加证书＝配两个 secret，零代码改动**。

## 二、证书怎么选（这是采购决策，代码侧都支持）

| 路线 | 效果 | 备注 |
| --- | --- | --- |
| **EV 代码签名证书** | 立即建立信誉，SmartScreen 提示一般直接消失 | 最贵；多数以**硬件 token/HSM** 形式交付，插不进 CI 的构建机，通常要配云签名服务 |
| **OV 代码签名证书** | 签名有效、UAC 与文件属性显示公司名；SmartScreen 信誉**按证书累积**（随下载量增长逐步放行，新证书初期仍可能提示） | 性价比路线；PFX 可直接进 CI（就是本仓库现在支持的形态） |
| **Azure Trusted Signing**（微软自家云签名） | 云 HSM，无需保管 PFX；签名者身份经微软验证 | 订阅制，量级远低于证书年费；**signtool 参数不同**（`/dlib` + `/dmdf`），选它时需给 `sign_win.ps1` 加一个分支（改动很小） |

价格只给量级参考（以官方报价为准）：OV 数百元～千余元/年，EV 数千元/年，Trusted Signing
约每月十美元级。**买之前先确认交付形态**：只有能导出 PFX（或能用云签名服务）的才进得了 CI。

## 三、配好之后长什么样（仓库已支持）

签名入口统一在 `client/packaging/build/sign_win.ps1`，证书从环境变量解析：

```powershell
# 本地打包（build_release.ps1 会自动用它签程序本体 + 安装器 + 卸载器，并校验）
$env:AINOVEL_SIGN_PFX = 'D:\certs\awesomenovel.pfx'
$env:AINOVEL_SIGN_PFX_PASSWORD = '<pfx 密码>'
powershell -ExecutionPolicy Bypass -File client\packaging\build\build_release.ps1

# 证书在本机证书存储里（免密码）
$env:AINOVEL_SIGN_THUMBPRINT = '<证书指纹>'

# 可选：时间戳服务（默认 DigiCert RFC3161）与签名描述
$env:AINOVEL_SIGN_TIMESTAMP_URL = 'http://timestamp.digicert.com'
```

CI（`client-package.yml`）：仓库 Settings → Secrets and variables → Actions 加两条
secret，推 tag 出包时自动生效——

- `WINDOWS_SIGN_PFX`：PFX 的 **base64**（`certutil -encode` 或 PowerShell
  `[Convert]::ToBase64String([IO.File]::ReadAllBytes(...))`，取正文行）
- `WINDOWS_SIGN_PFX_PASSWORD`：PFX 密码

签名覆盖面（缺一处用户就会在某个环节看到「未知发布者」）：

1. `AwesomeNovel.exe`（程序本体，Inno 打包**前**签 —— 打包后签外面这份无效）
2. `AwesomeNovel_Setup_v*.exe`（安装器，经 Inno `SignTool` 指令签）
3. `unins000.exe`（卸载器，同一条指令，`SignedUninstaller=yes`）

**没配证书不会让发版挂**（`sign_win.ps1` 打印警告跳过，安装包照出），但会：
- 本地脚本：步骤 7/8 打警告
- CI：`::warning title=未签名构建::` 一条注解
- 配了证书却签不上（证书过期/时间戳不通/路径错）：**本地与 CI 都硬失败**——校验闸门
  `sign_win.ps1 -Action Verify` 在出包后立刻断言签名存在，绝不让「以为签了」的包发出去。

## 四、内测自验：不买证书也能把链路走通

仓库自带自签证书 `client/packaging/cert/cert.pfx`（CN=Awesome Novel，密码 `ainovel123`）：

```powershell
$env:AINOVEL_SIGN_DEV_CERT = '1'          # 用仓库自签证书签名
powershell -ExecutionPolicy Bypass -File client\packaging\build\build_release.ps1
```

它验证的是**签名链路本身**（signtool 调用、Inno SignTool、卸载器签名、校验闸门都真跑），
以及「导入根证书的机器」上 UAC / 文件属性会显示签署者（`cert\install_cert.bat` 一键导入）。

⚠️ **自签证书不解除 SmartScreen**：SmartScreen 按公共 CA 证书的信誉判定，自签证书
（哪怕根证书已导入本机）仍会被拦。对外发版必须换成第二节里买的证书。

## 五、没有证书之前，内测同学可以这样绕开（这两条不影响我们发版）

- 下载后**解除锁定**：右键安装包 → 属性 → 勾「解除锁定」→ 确定；或 PowerShell
  `Unblock-File .\AwesomeNovel_Setup_v0.27.exe`。去掉 Mark-of-the-Web，SmartScreen 就不再拦。
- **应用内更新**下载的安装包没有 Mark-of-the-Web，也不会触发这个提示（只有浏览器/迅雷
  等下载链路会带标记）。

## 六、相关文件

- `client/packaging/build/sign_win.ps1`：证书解析 + 签名 + 校验（Sign / Verify / IsccArgs / Resolve）
- `client/packaging/build/installer.iss`：`#ifdef SignToolScript` 包裹的 `SignTool` 指令（不传 define 时编译结果与历史一致）
- `client/packaging/build/build_release.ps1`：步骤 7/8 签程序本体、8/8 出包并校验
- `.github/workflows/client-package.yml`：证书准备（secret → PFX）→ 签 exe → iscc（带签名参数）→ 校验闸门
- `client/backend/tests/test_packaging_win_signing.py`：静态门禁（不看证书也要保证链路不被改丢）
