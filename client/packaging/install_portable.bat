@echo off
REM client/packaging/install_portable.bat
REM Awesome Novel — 便携安装脚本（免 Inno Setup）
REM 用法: 双击即可——默认装到当前用户目录 %LOCALAPPDATA%\Programs\AwesomeNovel，无需管理员
REM 也可以直接解压到任意目录，双击 AwesomeNovel.exe 运行

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set SOURCE_DIR=%SCRIPT_DIR%dist\AwesomeNovel
set APP_NAME=AwesomeNovel

echo ===== Awesome Novel 安装 =====
echo.

REM 检查源文件
if not exist "%SOURCE_DIR%\%APP_NAME%.exe" (
    echo [错误] 找不到 %SOURCE_DIR%\%APP_NAME%.exe
    echo 请先运行 build.bat 构建
    pause
    exit /b 1
)

REM 询问安装路径
set INSTALL_DIR=%LOCALAPPDATA%\Programs\AwesomeNovel
echo 安装目录: %INSTALL_DIR%
echo 按 Enter 使用默认路径，或输入新路径:
set /p USER_DIR=
if not "%USER_DIR%"=="" set INSTALL_DIR=%USER_DIR%
echo.

REM 复制文件
echo [1/2] 复制文件到 %INSTALL_DIR%...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
xcopy /E /I /Y /Q "%SOURCE_DIR%\*" "%INSTALL_DIR%" >nul
if %errorlevel% neq 0 (
    echo [错误] 复制失败——目标目录不可写或被占用，换个目录、或关掉占用它的程序再试
    pause
    exit /b 1
)
echo [OK] 文件复制完成

REM 创建快捷方式
echo [2/2] 创建桌面快捷方式...
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%USERPROFILE%\Desktop\%APP_NAME%.lnk'); $SC.TargetPath = '%INSTALL_DIR%\%APP_NAME%.exe'; $SC.WorkingDirectory = '%INSTALL_DIR%'; $SC.Save()" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] 桌面快捷方式已创建
) else (
    echo [OK] 可手动创建快捷方式
)

echo.
echo ===== 安装完成 =====
echo 启动: 双击桌面 "AwesomeNovel" 快捷方式
echo 卸载: 删除 %INSTALL_DIR% 目录 + 桌面快捷方式
echo 书稿数据: %INSTALL_DIR%\data\
echo 日志与调参: 日志在 %INSTALL_DIR%\logs\（startup.log / app.log / llm.log / pywebview.log）；调参文件 shell.json 在 %INSTALL_DIR%\
pause
