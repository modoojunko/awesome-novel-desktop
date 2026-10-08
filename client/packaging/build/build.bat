@echo off
REM client/packaging/build/build.bat
REM Awesome Novel — Build Script
REM
REM Usage:
REM   build.bat             → 构建 onedir + 安装包
REM   build.bat quick       → 构建单 exe（测试用）
REM   build.bat v1.2.3      → 指定版本号
REM
REM 前置: Node.js 20+, Python 3.12+, Inno Setup 6+

setlocal enabledelayedexpansion
set BUILD_DIR=%~dp0
set ROOT_DIR=%BUILD_DIR%..\..\
set CLIENT_DIR=%ROOT_DIR%client\

REM 获取版本号：参数 > git tag > 默认
if not "%1"=="" if not "%1"=="quick" set APP_VERSION=%1
if "%APP_VERSION%"=="" (
  for /f %%v in ('git describe --tags --always --dirty 2^>nul') do set APP_VERSION=%%v
)
if "%APP_VERSION%"=="" set APP_VERSION=0.0.0
echo Version: %APP_VERSION%

echo ===== Awesome Novel Build v%APP_VERSION% =====

REM 1. Build frontend
echo [1/4] Building frontend...
cd /d "%CLIENT_DIR%frontend"
call npm ci >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] npm ci failed & exit /b 1 )
call npm run build >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Frontend build failed & exit /b 1 )
echo [OK] Frontend built

REM 2. Install backend dependencies
echo [2/4] Installing backend dependencies...
cd /d "%CLIENT_DIR%backend"
pip install -r requirements.txt >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Backend deps install failed & exit /b 1 )
echo [OK] Backend deps installed

REM 3. Build with engine (BUILD_ENGINE=nuitka|pyinstaller，默认 pyinstaller——c-nuitka-full)
cd /d "%BUILD_DIR%"
if "%1"=="quick" (
  echo [3/4] Building single EXE (onefile)...
  rmdir /S /Q dist build_py 2>nul
  pyinstaller build.spec --clean --noconfirm -- --onefile
  if %errorlevel% neq 0 ( echo [ERROR] PyInstaller failed & exit /b 1 )
  echo [OK] Output: dist\AwesomeNovel.exe
) else if /I "%BUILD_ENGINE%"=="nuitka" (
  echo [3/4] Building onedir via Nuitka...
  rmdir /S /Q dist-nuitka 2>nul
  python build_nuitka.py
  if errorlevel 1 ( echo [ERROR] Nuitka build failed & exit /b 1 )
  echo [OK] Output: dist-nuitka\AwesomeNovel\
) else (
  echo [3/4] Building onedir (for installer)...
  rmdir /S /Q dist build_py 2>nul
  pyinstaller build.spec --clean --noconfirm
  if %errorlevel% neq 0 ( echo [ERROR] PyInstaller failed & exit /b 1 )
  echo [OK] Output: dist\AwesomeNovel\
)

REM 4. Build installer (if Inno Setup available)
if "%1"=="quick" goto :end
echo [4/4] Building installer (v%APP_VERSION%)...
where iscc >nul 2>&1
if %errorlevel% equ 0 (
  cd /d "%BUILD_DIR%"
  iscc installer.iss /DMyAppVersion=%APP_VERSION% >nul 2>&1
  if %errorlevel% equ 0 (
    echo [OK] Installer done
  ) else ( echo [WARN] Inno Setup build failed )
) else (
  echo [SKIP] Inno Setup not installed
)

:end
echo.
echo ===== Build Complete =====
