# Awesome Novel 证书安装脚本 (PowerShell)
# 右键 → "以 PowerShell 运行" → 输入 Y 确认管理员权限

$pwd = ConvertTo-SecureString "ainovel123" -Force -AsPlainText
$certPath = Join-Path $PSScriptRoot "cert.pfx"

try {
    Import-PfxCertificate -FilePath $certPath -CertStoreLocation Cert:\LocalMachine\Root -Password $pwd -ErrorAction Stop
    Write-Host "证书安装成功！可以双击安装包了" -ForegroundColor Green
} catch {
    Write-Host "安装失败，请手动操作：双击 cert.pfx → 选择'本地计算机'→ 密码: ainovel123" -ForegroundColor Yellow
}

pause
