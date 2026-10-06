# client/packaging/build/verify_pack_hardening.ps1
# c-prompt-pack-hardening 真机验收（Windows）：装完包后跑本脚本，机器能判的都判掉，
# 剩下的三步是人工手测（脚本末尾会打印）。
#
# 用法（在装好客户端的机器上，PowerShell 任意窗口）：
#   powershell -ExecutionPolicy Bypass -File verify_pack_hardening.ps1
#   powershell -ExecutionPolicy Bypass -File verify_pack_hardening.ps1 -DataRoot "D:\AwesomeNovel\data"
#
# 判据（对应 spec「本机提取防护强度与不承诺项」与本 change 的 tasks 6.1）：
#   1) 包目录存在且为容器形态（pack.bin）；
#   2) 包目录里**没有任何** .prompt 明文；
#   3) 包目录里所有文件都搜不到模板分层标记（<<system>> / <<user>>）——这两个标记只活在
#      模板文本里，出现即说明明文落盘；
#   4) 钥匙形态符合平台：Windows 上 key.bin 必须是 DPAPI 密文（不可读成 32 字节明文密钥）。

param(
    [string]$DataRoot = ""
)

$ErrorActionPreference = 'Stop'
$fail = 0

function Check([string]$Name, [bool]$Ok, [string]$Detail = "") {
    if ($Ok) { Write-Host "[OK]   $Name" -ForegroundColor Green }
    else { Write-Host "[FAIL] $Name $Detail" -ForegroundColor Red; $script:fail++ }
}

# ── 定位包目录 ──
if (-not $DataRoot) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\AwesomeNovel\data'),
        (Join-Path $env:LOCALAPPDATA 'AwesomeNovel\data'),
        'C:\AwesomeNovel\data'
    )
    $DataRoot = $candidates | Where-Object { Test-Path (Join-Path $_ 'prompt-pack') } | Select-Object -First 1
}
if (-not $DataRoot) {
    Write-Host "找不到数据目录（prompt-pack 不存在）——先装包并登录一次，或用 -DataRoot 指定。" -ForegroundColor Yellow
    exit 2
}
$packRoot = Join-Path $DataRoot 'prompt-pack'
Write-Host "包目录：$packRoot`n"

$vdirs = Get-ChildItem -Path $packRoot -Directory -Filter 'v*' -ErrorAction SilentlyContinue
Check "存在已装版本目录（vN）" ($null -ne $vdirs -and $vdirs.Count -gt 0)

$files = Get-ChildItem -Path $packRoot -Recurse -File -ErrorAction SilentlyContinue
Check "存在容器文件 pack.bin" ([bool]($files | Where-Object Name -eq 'pack.bin'))

$plain = $files | Where-Object { $_.Name -like '*.prompt' }
Check "包目录零 .prompt 明文" (-not $plain) ("命中：" + (($plain | Select-Object -First 3).FullName -join ', '))

# 模板分层标记只存在于模板文本里：任何文件出现即视为明文落盘（含被改名的副本）
$leak = @()
foreach ($f in $files) {
    if ($f.Length -gt 5MB) { continue } # 容器本体也扫，但超大文件跳过以免拖慢
    $hit = Select-String -Path $f.FullName -Pattern '<<system>>|<<user>>' -Encoding utf8 -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($hit) { $leak += $f.FullName }
}
Check "包目录零模板明文（全文件搜分层标记）" ($leak.Count -eq 0) ("命中：" + ($leak -join ', '))

# 钥匙形态：Windows 上必须是 DPAPI 密文（本脚本只做形态判定，不解封）
$keyFile = Join-Path $packRoot 'key.bin'
if (Test-Path $keyFile) {
    $len = (Get-Item $keyFile).Length
    Check "key.bin 为 DPAPI 封装体（非 32 字节明文密钥）" ($len -ne 32) "长度=$len"
} else {
    Check "key.bin 存在（DPAPI 封装体）" $false "文件不存在"
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "自动检查全部通过。以下三步请在真机上人工确认：" -ForegroundColor Cyan
} else {
    Write-Host "有 $fail 项未通过——把上面的输出与 startup.log/uvicorn.log 一起回报。" -ForegroundColor Red
}
@'
人工手测（脚本判不了的）：
  1) 断网后用任意 AI 功能（如章纲起草）：应照常可用（离线自持）。
  2) 把整个 prompt-pack 目录拷到另一台机器（或本机另一个 Windows 用户）后启动客户端：
     应显示「写作能力未就绪」并联网重下，且在那台机器上同样搜不到模板明文。
  3) 升级安装（旧版明文包 → 本版）后首次启动即断网：写作能力应照常可用（就地加密迁移，无需重下）。
'@ | Write-Host
exit $fail
