; client/packaging/build/installer.iss
; AI Novel — Inno Setup 安装脚本
; 需要先安装 Inno Setup: https://jrsoftware.org/isdl.php
;
; 构建安装包:
;   1. 先运行 build.bat（生成 onedir 输出到 dist/AI Novel/）
;   2. 用 Inno Setup 打开本文件，点 Build → Compile
;   3. 或者命令行: iscc installer.iss

#define MyAppName "AI Novel"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
; 发布者（= 版权人/经营主体）：与品牌单源 brand/brand.json 的 company 键同值——
; Inno 读不了 JSON，此处是全仓唯一的手写字面量副本，改主体名必须与 json 同批改。
; 编码约束：本文件 UTF-8 无 BOM（Inno ≥6.3 起官方推荐；中文主体名靠此正确解码，
; 保存时勿改成 ANSI/带 BOM——ANSI 会乱码，≥7.0.2 遇非法字节直接编译失败）。
#define MyAppPublisher "星纬（海口）投资有限公司"
#define MyAppURL "https://github.com/modoojunko/ai-novel"
#define MyAppExeName "AI Novel.exe"

[Setup]
; 基础设置
AppId={{B8F1A2D3-4E5F-6A7B-8C9D-0E1F2A3B4C5D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 输出
OutputDir=..\dist
OutputBaseFilename=AI_Novel_Setup_v{#MyAppVersion}
; 图标
SetupIconFile=icon.ico

; 压缩
Compression=lzma2/ultra
SolidCompression=yes
; Windows 版本要求
MinVersion=10.0.0
; 管理员权限（写入 Program Files）
PrivilegesRequired=admin
; 卸载
Uninstallable=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
; ChineseSimplified.isl 为 Inno Setup 非官方语言包，Inno Setup 安装器默认不提供 →
; 仓库 vendor（languages/ChineseSimplified.isl，源自 jrsoftware/issrc），相对路径引用
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Files]
; PyInstaller onedir 输出的所有文件
Source: "dist\AI Novel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 重命名卸载程序为 uninstall.exe
Filename: "{cmd}"; Parameters: "/C rename ""{app}\unins000.exe"" ""uninstall.exe"" 2>nul"; Flags: runhidden
; 安装完成后是否立即运行
Filename: "{app}\{#MyAppExeName}"; Description: "运行 {#MyAppName}"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; 卸载时清理用户数据
Filename: "{cmd}"; Parameters: "/C rmdir /S /Q ""{userappdata}\AI Novel"""; Flags: runhidden
