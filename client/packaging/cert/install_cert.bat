@echo off
REM Awesome Novel 内测自签证书安装脚本
REM 右键 → "以管理员身份运行"
REM
REM 作用：把 cert.pfx 装进「受信任的根证书颁发机构」，使内测自签构建在本机能验签通过、
REM UAC 与文件属性显示签署者「Awesome Novel (Dev)」。
REM 注意：它**不解除** SmartScreen 提示（那个由公共 CA 证书的信誉决定）——
REM 内测想避开提示请右键安装包 → 属性 → 勾「解除锁定」。见 docs/ops/client-code-signing.md。

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 需要管理员权限！请右键 → "以管理员身份运行"
    pause
    exit /b 1
)

echo 正在安装 Awesome Novel 内测自签证书...

powershell -ExecutionPolicy Bypass -Command "& { $pwd = ConvertTo-SecureString 'ainovel123' -Force -AsPlainText; Import-PfxCertificate -FilePath '%~dp0cert.pfx' -CertStoreLocation Cert:\LocalMachine\Root -Password $pwd }" >nul 2>&1

if %errorlevel% equ 0 (
    echo [完成] 证书安装成功：内测签名包可验签，UAC 显示签署者
    echo [注意] SmartScreen 提示不受影响，内测请用「解除锁定」(Unblock-File) 绕开
) else (
    echo [提示] 请手动安装：双击 cert.pfx → 选择"本地计算机"→ 下一步
    echo 证书密码: ainovel123
)

echo.
pause
