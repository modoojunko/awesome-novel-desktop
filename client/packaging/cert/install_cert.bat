@echo off
REM Awesome Novel 证书安装脚本
REM 右键 → "以管理员身份运行"
REM 安装后安装包被系统信任，不再弹 SmartScreen

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 需要管理员权限！请右键 → "以管理员身份运行"
    pause
    exit /b 1
)

echo 正在安装 Awesome Novel 证书...

powershell -ExecutionPolicy Bypass -Command "& { $pwd = ConvertTo-SecureString 'ainovel123' -Force -AsPlainText; Import-PfxCertificate -FilePath '%~dp0cert.pfx' -CertStoreLocation Cert:\LocalMachine\Root -Password $pwd }" >nul 2>&1

if %errorlevel% equ 0 (
    echo [完成] 证书安装成功！可以双击安装包了
) else (
    echo [提示] 请手动安装：双击 cert.pfx → 选择"本地计算机"→ 下一步
    echo 证书密码: ainovel123
)

echo.
pause
