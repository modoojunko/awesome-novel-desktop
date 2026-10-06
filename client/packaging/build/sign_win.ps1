# client/packaging/build/sign_win.ps1
# Awesome Novel — Windows 代码签名统一入口（安装器 / 程序本体 / 产线校验共用一个脚本）
#
# 为什么要有这个脚本：用户双击安装包看到的「Windows 已保护你的电脑 / 发布者: 未知」
# 是 SmartScreen 对**未签名**安装包的提示——不是 bug，也没有任何代码改动能绕过：
# 只有给安装包与程序本体做 Authenticode 代码签名（证书从公共 CA 买 / Azure Trusted
# Signing 签）才会消失。本脚本把「加证书」压缩成两个环境变量，签名链路先行落地，
# 见 docs/ops/client-code-signing.md。
#
# 证书来源（按优先级）：
#   1) AINOVEL_SIGN_DLIB            云签名/天价 HSM 的标准接口：signtool /dlib <厂商 dll>
#                                    （+ AINOVEL_SIGN_DMDF 指向元数据 json）——Azure Trusted
#                                    Signing、各家云签名服务都走这条；**当前公共 CA 的主流形态**
#   2) AINOVEL_SIGN_PFX             PFX 文件路径（+ AINOVEL_SIGN_PFX_PASSWORD）
#                                    —— 内部 PKI / 自签 / 2023-06 前签发的旧证书
#   3) AINOVEL_SIGN_THUMBPRINT      证书指纹（装在当前用户/机器证书存储里）
#                                    —— USB 硬件 token 形态（私钥在 token 里，signtool 会弹 PIN）
#   4) AINOVEL_SIGN_DEV_CERT=1      仓库自签证书 client/packaging/cert/cert.pfx
#                                    —— 仅供内测/自验签名链路，**不解除 SmartScreen**
# 都没有 → 不签名：Sign/Verify 只打印警告（发版不因缺证书挂掉），
#          IsccArgs 不输出任何参数（Inno 侧 SignTool 指令不启用，编译结果与历史一致）。
#
# ⚠️ 2023-06-01 起 CA/B 规则要求代码签名私钥必须由硬件保护（FIPS 140-2 L2 / CC EAL4+）
#    且不可导出——**公共 CA 已不再签发可导出 PFX 的代码签名证书**。所以正经采购拿到的是
#    云签名服务或 USB token，前者进 CI（本脚本 /dlib 分支），后者只能在插着 token 的
#    Windows 上本地发版（/sha1 分支）。详见 docs/ops/client-code-signing.md。
#
# 其他可调项：AINOVEL_SIGN_TIMESTAMP_URL（默认 DigiCert RFC3161）、AINOVEL_SIGN_DESCRIPTION。
#
# 用法：
#   sign_win.ps1 -Action Sign     -Path <file>      # 签一个文件（Inno 的 SignTool 也调这条）
#   sign_win.ps1 -Action Verify   -Path <file>      # 校验签名（未签名即失败）
#   sign_win.ps1 -Action IsccArgs                   # 输出 iscc 需要的 /D 参数（未配置则无输出）
#   sign_win.ps1 -Action Resolve                    # 打印当前解析结果（排障用）

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Sign', 'Verify', 'IsccArgs', 'Resolve')]
    [string]$Action,

    [string]$Path
)

$ErrorActionPreference = 'Stop'

function Get-SignToolPath {
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # Windows SDK 的 signtool 常不在 PATH：按版本号倒序找 x64 那份
    # （两个环境变量都可能缺席——32 位宿主/精简镜像，逐个判而不是直接 Join-Path）
    $roots = @()
    foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if ($base) { $roots += (Join-Path $base 'Windows Kits\10\bin') }
    }
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $hit = Get-ChildItem -Path $root -Filter 'signtool.exe' -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\' } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Get-SignConfig {
    $pfx = $env:AINOVEL_SIGN_PFX
    $password = $env:AINOVEL_SIGN_PFX_PASSWORD
    $thumbprint = $env:AINOVEL_SIGN_THUMBPRINT
    $dlib = $env:AINOVEL_SIGN_DLIB
    $dmdf = $env:AINOVEL_SIGN_DMDF

    if ($env:AINOVEL_SIGN_DEV_CERT -eq '1') {
        # 自签证书：密码写在证书目录的安装脚本里（本就不是秘密），这里同步一份默认值
        $pfx = Join-Path $PSScriptRoot '..\cert\cert.pfx'
        if (-not $password) { $password = 'ainovel123' }
    }

    if (-not $pfx -and -not $thumbprint -and -not $dlib) { return $null }

    $signtool = Get-SignToolPath
    if (-not $signtool) {
        throw 'signtool.exe 未找到（装 Windows SDK，或确保它在 PATH）——签名需要它'
    }
    if ($pfx -and -not (Test-Path $pfx)) {
        throw "AINOVEL_SIGN_PFX 指向的文件不存在：$pfx"
    }
    if ($dlib -and -not (Test-Path $dlib)) {
        throw "AINOVEL_SIGN_DLIB 指向的签名 dll 不存在：$dlib（云签名服务的客户端工具要装好）"
    }
    if ($dmdf -and -not (Test-Path $dmdf)) {
        throw "AINOVEL_SIGN_DMDF 指向的元数据文件不存在：$dmdf"
    }

    $ts = $env:AINOVEL_SIGN_TIMESTAMP_URL
    if (-not $ts) { $ts = 'http://timestamp.digicert.com' }
    $desc = $env:AINOVEL_SIGN_DESCRIPTION
    if (-not $desc) { $desc = 'Awesome Novel' }

    $kind = 'store'
    if ($dlib) { $kind = 'dlib' } elseif ($pfx) { $kind = 'pfx' }

    return [pscustomobject]@{
        SignTool    = $signtool
        Pfx         = $pfx
        Password    = $password
        Thumbprint  = $thumbprint
        Dlib        = $dlib
        Dmdf        = $dmdf
        Timestamp   = $ts
        Description = $desc
        Kind        = $kind
    }
}

function Write-NotConfiguredWarning {
    # 拼接一律把 + 放在行尾：命令参数位（Write-Warning (...)）里的换行会让解析器
    # 在行末就收束语句，行首的 + 变成语法错误（2026-10-06 被 pwsh 解析门禁抓到过）
    $message = '未配置 Windows 代码签名证书（AINOVEL_SIGN_PFX / AINOVEL_SIGN_THUMBPRINT）' +
        '——产物不签名，用户安装时会看到 SmartScreen「已保护你的电脑 / 发布者: 未知」。' +
        '取证书与配置步骤见 docs/ops/client-code-signing.md'
    Write-Warning $message
}

function Invoke-SignFile {
    param([string]$FilePath, $Config)

    if (-not (Test-Path $FilePath)) { throw "待签名文件不存在：$FilePath" }
    $arguments = @('sign', '/fd', 'sha256', '/td', 'sha256', '/tr', $Config.Timestamp)
    if ($Config.Dlib) {
        # 云签名/HSM：私钥在厂商侧，signtool 只负责调 dlib（+ 元数据），不需要 /f /p /sha1
        $arguments += @('/dlib', $Config.Dlib)
        if ($Config.Dmdf) { $arguments += @('/dmdf', $Config.Dmdf) }
    } elseif ($Config.Pfx) {
        $arguments += @('/f', $Config.Pfx)
        if ($Config.Password) { $arguments += @('/p', $Config.Password) }
    } else {
        $arguments += @('/sha1', $Config.Thumbprint)
    }
    if ($Config.Description) { $arguments += @('/d', $Config.Description) }
    $arguments += $FilePath

    Write-Host "签名（$($Config.Kind)）：$FilePath"
    & $Config.SignTool @arguments
    if ($LASTEXITCODE -ne 0) { throw "signtool 退出码 $LASTEXITCODE：$FilePath" }
    Write-Host "  OK -> $FilePath"
}

function Assert-SignaturePresent {
    param([string]$FilePath)

    if (-not (Test-Path $FilePath)) { throw "待校验文件不存在：$FilePath" }
    $signature = Get-AuthenticodeSignature -FilePath $FilePath
    if ($signature.Status -eq 'NotSigned') {
        throw "文件没有数字签名：$FilePath（配了证书却没签上＝签名链路坏了，直接失败）"
    }
    Write-Host "签名状态：$($signature.Status)  签署者：$($signature.SignerCertificate.Subject)"
    if ($signature.Status -ne 'Valid') {
        # 自签证书在未导入根证书的机器上就是 UnknownError/UntrustedRoot，属预期
        $message = "签名存在但链校验为 $($signature.Status)：" +
            '若用的是自签证书（含内测 cert.pfx）属预期——正式证书链完整时此处应为 Valid'
        Write-Warning $message
    }
}

$config = Get-SignConfig

switch ($Action) {
    'Resolve' {
        if (-not $config) {
            Write-Host '签名：未配置（产物不会签名，SmartScreen 会提示发布者未知）'
            break
        }
        Write-Host "签名：已配置 kind=$($config.Kind) signtool=$($config.SignTool) timestamp=$($config.Timestamp)"
    }
    'Sign' {
        if (-not $config) { Write-NotConfiguredWarning; break }
        Invoke-SignFile -FilePath $Path -Config $config
    }
    'Verify' {
        if (-not $config) { Write-NotConfiguredWarning; break }
        Assert-SignaturePresent -FilePath $Path
    }
    'IsccArgs' {
        if (-not $config) { break }
        # 交给 Inno：SignTool 指令覆盖安装器本体与卸载器（SignedUninstaller）
        $scriptPath = (Resolve-Path $PSCommandPath).Path
        Write-Output "/DSignToolScript=$scriptPath"
    }
}
