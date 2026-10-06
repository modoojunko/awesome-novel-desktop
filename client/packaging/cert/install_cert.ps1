# Awesome Novel 内测自签证书安装脚本 (PowerShell)
# 右键 → "以 PowerShell 运行" → 输入 Y 确认管理员权限
#
# 作用：把 client/packaging/cert/cert.pfx 装进「受信任的根证书颁发机构」，
# 使内测自签构建（$env:AINOVEL_SIGN_DEV_CERT='1' 打出来的包）在本机能验签通过、
# UAC 与文件属性显示签署者「Awesome Novel (Dev)」。
#
# ⚠️ 它**不解除** SmartScreen「Windows 已保护你的电脑 / 发布者: 未知」——
# 那个提示由公共 CA 证书的信誉决定，自签证书无论是否导入根都无法解除。
# 内测想避开提示：右键安装包 → 属性 → 勾「解除锁定」（或 PowerShell Unblock-File）。
# 详见 docs/ops/client-code-signing.md。

$pwd = ConvertTo-SecureString "ainovel123" -Force -AsPlainText
$certPath = Join-Path $PSScriptRoot "cert.pfx"

try {
    Import-PfxCertificate -FilePath $certPath -CertStoreLocation Cert:\LocalMachine\Root -Password $pwd -ErrorAction Stop
    Write-Host "证书安装成功：内测签名包在本机可验签、UAC 会显示签署者。" -ForegroundColor Green
    Write-Host "注意：SmartScreen 提示不受影响——内测请用「解除锁定」(Unblock-File) 绕开。" -ForegroundColor Yellow
} catch {
    Write-Host "安装失败，请手动操作：双击 cert.pfx → 选择'本地计算机'→ 密码: ainovel123" -ForegroundColor Yellow
}

pause
