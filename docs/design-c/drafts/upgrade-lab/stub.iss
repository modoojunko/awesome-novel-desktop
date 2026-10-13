; upgrade-lab/stub.iss — 「零 UAC 承重柱」真机仿真实验包
; 只模拟三件被测点，不碰真实应用：
;   1) PrivilegesRequired=admin ＋ Override=commandline（免 UAC 静默链的改动本体）
;   2) /AUTOLAUNCH=1 → [Code] Log 参数值 ＋ 装后拉起 notepad（窗口可见性）
;   3) data\marker.txt 模拟书稿：安装器写版本文案但绝不动 marker（数据不变式）
; 编译（mac docker 配方，或 Windows 装 Inno 后同命令）：
;   iscc /DVER=1.0.0 stub.iss   → out/Setup_Lab_1.0.0.exe（旧版 A）
;   iscc /DVER=1.0.1 stub.iss   → out/Setup_Lab_1.0.1.exe（新版 B）
; ⚠️ AppId 与真实产品无关（独立 GUID），随便装不污染真机已装的「爱小说」。

#define MyAppName "AwesomeNovelLab"
; 版本号取环境变量 LABVER（docker 编译配方里该镜像的 /D 传参与入口冲突，判例 10-13）
#define VER GetEnv("LABVER")
#if VER == ""
  #define VER "1.0.0"
#endif

[Setup]
AppId={{A1B2C3D4-LAB0-4000-8000-000000000001}
AppName={#MyAppName}
AppVersion={#VER}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=no
UsePreviousAppDir=yes
PrivilegesRequired=admin
; ── 被测点 1：允许命令行覆盖权限级别（生产 iss 要加的就是这一行）──
PrivilegesRequiredOverridesAllowed=commandline
; 仿真包不配中文语言包，英文即可（避免把生产 vendored isl 卷进来）
LanguageDetectionMethod=none
UsedUserAreasWarning=no
OutputDir=out
OutputBaseFilename=Setup_Lab_{#VER}
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; ── 被测点（V-2）：per-user 静默时公用桌面图标可写性 ──
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "pkg.dat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{sys}\notepad.exe"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{sys}\notepad.exe"; Tasks: desktopicon

[Run]
; 现状形态（对照）：静默安装时因 skipifsilent 被跳过——生产同款老行
Filename: "{sys}\notepad.exe"; Description: "Run {#MyAppName}"; Flags: postinstall nowait skipifsilent
; ── 被测点 2：新自拉起行——不带 skipifsilent、不带 runhidden，Check 判 /AUTOLAUNCH=1 ──
Filename: "{sys}\notepad.exe"; Check: AutoLaunchRequested; Flags: postinstall nowait

[Code]
function AutoLaunchRequested: Boolean;
begin
  Result := ExpandConstant('{param:AUTOLAUNCH|}') = '1';
end;

procedure InitializeWizard();
begin
  // V-3 判据：三种参数形态（缺省 / 裸 /AUTOLAUNCH / /AUTOLAUNCH=1）在 /LOG 里的实际取值
  Log('LAB param[AUTOLAUNCH]=''' + ExpandConstant('{param:AUTOLAUNCH|}') + '''');
  Log('LAB param[CURRENTUSER given]=''' + ExpandConstant('{param:CURRENTUSER|none}') + '''');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Marker: String;
begin
  if CurStep = ssPostInstall then
  begin
    // 版本文案＝B 包顶上来的程序件指纹
    SaveStringToFile(ExpandConstant('{app}\version.txt'), 'installed=' + '{#VER}' + #13#10, False);
    // ── 被测点 3：模拟书稿——首装生成，升级必须原封不动 ──
    Marker := ExpandConstant('{app}\data\marker.txt');
    if not FileExists(Marker) then
    begin
      ForceDirectories(ExpandConstant('{app}\data'));
      SaveStringToFile(Marker, 'BOOKDATA first-install, do-not-touch' + #13#10, False);
      Log('LAB created marker at ' + Marker);
    end
    else
      Log('LAB marker already present, untouched: ' + Marker);
  end;
end;
