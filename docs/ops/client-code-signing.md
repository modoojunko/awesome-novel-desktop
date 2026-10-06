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

## 二、证书怎么选（采购决策；代码侧三种形态都已支持）

**先讲一条 2023 年后的硬规则**：行业规则（CA/B Forum Code Signing BR）自 **2023-06-01** 起要求
代码签名证书的**私钥由硬件保护且不可导出**（FIPS 140-2 Level 2 / Common Criteria EAL4+）。
所以今天从公共 CA 买到的代码签名证书**没有「导出 PFX 丢进 CI」这种形态**了，只有：

| 交付形态 | 能否进 CI | 我们这边怎么接 |
| --- | --- | --- |
| **云签名服务**（Azure Trusted Signing / DigiCert KeyLocker / SSL.com eSigner / Sectigo 等） | ✅ 能 | signtool 的 `/dlib` 接口：配 `AINOVEL_SIGN_DLIB`(+`AINOVEL_SIGN_DMDF`) 即可（已实现）；只给厂商自家 CLI 的，把 CLI 包进签名命令 |
| **USB 硬件 token**（CA 寄一个 U 盘/令牌过来） | ❌ 不能（私钥在 token 里，必须插在签名的那台机器上） | 在插着 token 的 Windows 上本地发版：`AINOVEL_SIGN_THUMBPRINT=<证书指纹>`（signtool 会弹 PIN） |
| **自家 HSM / 企业内网 PKI / 自签** | 视形态 | 能出 PFX 就用 `AINOVEL_SIGN_PFX`（开发期就是这样）；HSM 走 `/dlib` |

按**验证强度**分两档（决定提示多久消失）：

| 档位 | SmartScreen 效果 | 备注 |
| --- | --- | --- |
| **OV**（组织验证） | 签名有效、UAC 与文件属性显示公司名；**信誉按证书累积**——下载量上来才逐步放行，新证书头几天仍可能提示 | 千元级/年；需营业执照等材料 |
| **EV**（扩展验证） | **立即**建立信誉，提示一般直接消失 | 数千元/年；验证更严（常含电话回访） |
| **Azure Trusted Signing**（微软自家云签名） | 云 HSM、订阅制（每月十美元级）；签名者身份由微软验证；signtool `/dlib` 直接可用 | **最省事、最便宜的 CI 方案**；需 Azure 订阅 + 主体资质审核；支持地区/主体类型以微软当前政策为准（中国大陆主体能否通过要先确认） |

主体信息建议直接用经营主体（**星纬（海口）投资有限公司**）——UAC 与 SmartScreen 显示的就是证书
里的主体名，与 `brand/brand.json` 的 `company` 同源。别忘了时间成本：**审核几天到几周**（EV 更久）。

> 暂时不买证书时的唯一做法：下载页/安装说明里写清「点『更多信息 → 仍要运行』」，内测同学自己
> 「解除锁定」（见第五节）。这不是产品级解法——对普通用户，第一次装就被安全软件拦下＝流失。

## 三、配好之后长什么样（仓库已支持）

签名入口统一在 `client/packaging/build/sign_win.ps1`，证书从环境变量解析：

```powershell
# 本地打包（build_release.ps1 会自动用它签程序本体 + 安装器 + 卸载器，并校验）
#
# ① 云签名服务（推荐给 CI；dll 与元数据由厂商客户端工具装好）
$env:AINOVEL_SIGN_DLIB = 'C:\Program Files\Azure Trusted Signing\...\Azure.CodeSigning.Dlib.dll'
$env:AINOVEL_SIGN_DMDF = 'D:\certs\metadata.json'
#
# ② USB token（插着 token 的机器上本地发版；signtool 会弹 PIN）
$env:AINOVEL_SIGN_THUMBPRINT = '<证书指纹>'
#
# ③ 能导出的证书（企业内网 PKI / 开发期自签）
$env:AINOVEL_SIGN_PFX = 'D:\certs\awesomenovel.pfx'
$env:AINOVEL_SIGN_PFX_PASSWORD = '<pfx 密码>'
#
# 可选：时间戳服务（默认 DigiCert RFC3161）与签名描述
$env:AINOVEL_SIGN_TIMESTAMP_URL = 'http://timestamp.digicert.com'

powershell -ExecutionPolicy Bypass -File client\packaging\build\build_release.ps1
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
