# client/packaging/build/build_release.ps1
# Awesome Novel - Windows 发版打包一键脚本（离线复刻 client-package.yml 的 Windows 链）
#
# 用途：GitHub Actions 不可用时的发版打包（2026-10-04 配方，与 CI 步骤逐条对齐）。
# 前置：Git、Node.js 20+、Python 3.12+（pip 在 PATH）、Inno Setup 6+（iscc 在 PATH
#       或默认安装路径；没有就 `choco install innosetup -y`）。
# 用法：
#   powershell -ExecutionPolicy Bypass -File build_release.ps1            # 版本取自最新 v* tag
#   powershell -ExecutionPolicy Bypass -File build_release.ps1 0.26       # 显式指定版本
#   powershell -ExecutionPolicy Bypass -File build_release.ps1 0.27 -DevSign   # 内测自签签名（见下）
# 产物：client/packaging/dist/AwesomeNovel_Setup_<version>.exe
# 注意：须在仓库根的检出内运行（脚本向上定位仓库根）。
#
# 代码签名（2026-10-06 落地，见 docs/ops/client-code-signing.md）：
#   **默认＝仓库自签证书**（用户拍板「自签即可」）：程序本体 + 安装器 + 卸载器全签，
#   出包后校验。效果：**导入过我们根证书的机器**（测试同学先跑
#   client\packaging\cert\install_cert.bat）会显示发布者「Awesome Novel (Dev)」；
#   对外部用户仍显示「发布者: 未知」，SmartScreen 也仍会拦（自签不解除提示）。
#   配了正式证书（AINOVEL_SIGN_DLIB / _PFX / _THUMBPRINT）→ 自动优先用正式证书，零改动；
#   AINOVEL_SIGN_DEV_CERT=0 → 出未签名包；-DevSign → 强制自签（验内测链路用）。

[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Version,
    # 内测自签签名：让导入过根证书的机器（测试同学本机）在 UAC/文件属性/安装弹窗里
    # 看到「Awesome Novel (Dev)」而不是「发布者未知」；对未导入的机器无效果
    [switch]$DevSign
)

$ErrorActionPreference = 'Stop'

# ── 定位目录（脚本在 client/packaging/build/ 下）──
$BuildDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $BuildDir '..\..\..')).Path
$ClientDir = Join-Path $RepoRoot 'client'

if ($DevSign) { $env:AINOVEL_SIGN_DEV_CERT = '1' }
if ($args.Count -gt 0) { Write-Warning "忽略多余参数：$($args -join ' ')（只认版本号位置参数与 -DevSign）" }

# ── 版本号：参数 > git tag（v0.26 -> 0.26，非法字符清洗，与 CI 同源）──
if (-not $Version) {
    $Version = (& git -C $RepoRoot describe --tags --abbrev=0 2>$null)
    if (-not $Version) { Write-Error 'git 仓库无 v* tag 且未显式给版本号'; exit 1 }
}
$Version = $Version.TrimStart('v') -replace '[^A-Za-z0-9._-]', '-'
Write-Host "==== Awesome Novel Windows 发版打包 v$Version ===="

function Step([string]$Name, [scriptblock]$Body) {
    Write-Host "[$Name] ..." -NoNewline
    & $Body
    Write-Host " OK"
}

# ── 1. 前端 ──
Step '1/8 前端构建' {
    Push-Location (Join-Path $ClientDir 'frontend')
    try {
        npm ci 2>$null; if ($LASTEXITCODE -ne 0) { throw 'npm ci 失败' }
        npm run build 2>$null; if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
    } finally { Pop-Location }
}

# ── 2. release.json 烘焙源（S端 端点：缺省=CI fallback 生产值，预置 env 可覆盖）──
Step '2/8 release.json 生成' {
    if (-not $env:RELEASE_SERVER_API_BASE)      { $env:RELEASE_SERVER_API_BASE = 'https://novel-s-server-297265-7-1468883265.sh.run.tcloudbase.com/api' }
    if (-not $env:RELEASE_SERVER_API_FALLBACK)  { $env:RELEASE_SERVER_API_FALLBACK = 'https://novel-s-server-297265-7-1468883265.sh.run.tcloudbase.com/api' }
    if (-not $env:RELEASE_PUBLIC_SERVER_API)    { $env:RELEASE_PUBLIC_SERVER_API = 'https://www.awesomenovel.com/api' }
    if (-not $env:RELEASE_PORTAL_URL)           { $env:RELEASE_PORTAL_URL = 'https://www.awesomenovel.com' }
    if (-not $env:RELEASE_DOWNLOAD_BASE)        { $env:RELEASE_DOWNLOAD_BASE = 'https://www.awesomenovel.com/download' }
    if (-not $env:RELEASE_DOWNLOAD_FALLBACK_BASE) { $env:RELEASE_DOWNLOAD_FALLBACK_BASE = 'https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/download' }
    Push-Location $BuildDir
    try {
        python ..\..\backend\scripts\release_json_generate.py $Version -o release.json
        if ($LASTEXITCODE -ne 0) { throw 'release_json_generate 失败' }
    } finally { Pop-Location }
}

# ── 3. 依赖 ──
Step '3/8 安装依赖（backend + packaging）' {
    python -m pip install -r (Join-Path $ClientDir 'backend\requirements.txt') --quiet
    if ($LASTEXITCODE -ne 0) { throw 'backend deps 安装失败' }
    python -m pip install -r (Join-Path $BuildDir 'requirements.txt') --quiet
    if ($LASTEXITCODE -ne 0) { throw 'packaging deps 安装失败' }
}

# ── 4. PyInstaller ──
Step '4/8 PyInstaller 打包' {
    $env:APP_VERSION = "v$Version"   # exe 版本资源口径，build.spec 内去 v 清洗
    Push-Location $BuildDir
    try {
        if (Test-Path dist) { Remove-Item -Recurse -Force dist }
        if (Test-Path build_py) { Remove-Item -Recurse -Force build_py }
        python -m PyInstaller build.spec --clean --noconfirm --workpath build_py
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 失败' }
    } finally { Pop-Location }
}

# ── 5. 断言（release.json / LICENSE / THIRD-PARTY-NOTICES 必须真实烘进产物）──
Step '5/8 产物断言' {
    foreach ($name in @('release.json', 'LICENSE', 'THIRD-PARTY-NOTICES.txt')) {
        $hit = Get-ChildItem -Path (Join-Path $BuildDir 'dist') -Recurse -Filter $name | Select-Object -First 1
        if (-not $hit) { throw "$name 未打进安装包——检查 build.spec datas" }
        Write-Host " baked: $($hit.FullName)"
    }
    $rel = Get-ChildItem -Path (Join-Path $BuildDir 'dist') -Recurse -Filter 'release.json' | Select-Object -First 1
    python (Join-Path $RepoRoot 'client\backend\scripts\release_json_assert.py') $rel.FullName
    if ($LASTEXITCODE -ne 0) { throw 'release_json_assert 失败' }
    # 写作能力包（c-prompt-pack-client 5.x）：安装包零模板断言（硬切）
    $tpl = Get-ChildItem -Path (Join-Path $BuildDir 'dist') -Recurse -Filter '*.prompt' | Select-Object -First 1
    if ($tpl) { throw "安装包含提示词模板（$($tpl.FullName)）——硬切要求产物零 .prompt" }
    Write-Host ' 断言通过: 产物零 *.prompt'
}

# ── 6. 冒烟（--smoke 无头，轮询 health + SPA；不跑这步坏包照样绿）──
Step '6/8 冒烟测试' {
    $exe = Join-Path $BuildDir 'dist\AwesomeNovel\AwesomeNovel.exe'
    if (-not (Test-Path $exe)) { throw "找不到产物 $exe" }
    $portJson = Join-Path $env:APPDATA 'AwesomeNovel\port.json'
    $proc = Start-Process -FilePath $exe -ArgumentList '--smoke' -PassThru -RedirectStandardOutput "$env:TEMP\ainovel-smoke.log" -RedirectStandardError "$env:TEMP\ainovel-smoke.err.log"
    try {
        $port = ''
        foreach ($i in 1..60) {
            if (Test-Path $portJson) {
                $m = Select-String -Path $portJson -Pattern '"port"\s*:\s*(\d+)' | Select-Object -First 1
                if ($m) { $port = $m.Matches[0].Groups[1].Value }
            }
            if ($port -and (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 2 -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Seconds 1
        }
        if (-not $port -or -not (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 3 -ErrorAction SilentlyContinue)) {
            throw "SMOKE FAILED - backend not ready（日志：$env:TEMP\ainovel-smoke.log）"
        }
        $idx = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/" -TimeoutSec 3).Content
        if ($idx -notmatch 'id="root"') { throw 'SMOKE FAILED - SPA index.html 未被服务' }
        Write-Host " SMOKE OK - health + SPA on port $port"
    } finally {
        if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    }
}

# ── 7. 程序本体签名（默认自签；必须在 Inno 打包前，否打进安装包的还是未签名件）──
Step '7/8 程序本体签名' {
    $exe = Join-Path $BuildDir 'dist\AwesomeNovel\AwesomeNovel.exe'
    & (Join-Path $BuildDir 'sign_win.ps1') -Action Sign -Path $exe
    if ($LASTEXITCODE -ne 0) { throw '程序本体签名失败' }
}

Step '8/8 Inno Setup 安装包' {
    $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $candidate = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
        if (Test-Path $candidate) { $iscc = $candidate }
    }
    if (-not $iscc) { throw 'iscc 不在 PATH 且默认路径无 Inno Setup 6（choco install innosetup -y）' }
    Push-Location $BuildDir
    try {
        # 有证书时把 /DSignToolScript 传给 Inno：安装器本体 + 卸载器一并签名
        $signArgs = @(& (Join-Path $BuildDir 'sign_win.ps1') -Action IsccArgs)
        & $iscc "/DMyAppVersion=$Version" @signArgs installer.iss
        if ($LASTEXITCODE -ne 0) { throw 'Inno Setup 构建失败' }
        # 没签上＝链路坏了，此处直接失败（显式关闭签名时本步只警告）
        $signed = Get-ChildItem -Path (Join-Path $RepoRoot 'client\packaging\dist') -Filter 'AwesomeNovel_Setup_*.exe' |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        & (Join-Path $BuildDir 'sign_win.ps1') -Action Verify -Path $signed.FullName
        if ($LASTEXITCODE -ne 0) { throw '安装包签名校验失败' }
    } finally { Pop-Location }
}

$out = Get-ChildItem -Path (Join-Path $RepoRoot 'client\packaging\dist') -Filter 'AwesomeNovel_Setup_*.exe' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $out) { Write-Error '未找到 AwesomeNovel_Setup_*.exe 产物'; exit 1 }
Write-Host "==== 完成：$($out.FullName)（$([math]::Round($out.Length/1MB,1)) MB）===="
& (Join-Path $BuildDir 'sign_win.ps1') -Action Resolve
