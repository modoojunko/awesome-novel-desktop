; client/packaging/build/installer.iss
; Awesome Novel — Inno Setup 安装脚本
; 需要先安装 Inno Setup: https://jrsoftware.org/isdl.php
;
; 构建安装包:
;   1. 先运行 build.bat（生成 onedir 输出到 dist/AwesomeNovel/）
;   2. 用 Inno Setup 打开本文件，点 Build → Compile
;   3. 或者命令行: iscc installer.iss

#define MyAppName "Awesome Novel"
; 安装目录名（与产品显示名解耦）：纯 ASCII、无空格（用户拍板 2026-10-05）。
; 目录名会进外部脚本/命令行/备份路径，空格与中文是常见坑；显示名（AppName/
; 开始菜单/快捷方式/窗口标题）仍走 MyAppName，两者互不影响。
#define MyAppDirName "AwesomeNovel"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
; 发布者（= 版权人/经营主体）：与品牌单源 brand/brand.json 的 company 键同值——
; Inno 读不了 JSON，此处是全仓唯一的手写字面量副本，改主体名必须与 json 同批改。
; 编码约束：本文件 UTF-8 无 BOM（Inno ≥6.3 起官方推荐；中文主体名靠此正确解码，
; 保存时勿改成 ANSI/带 BOM——ANSI 会乱码，≥7.0.2 遇非法字节直接编译失败）。
#define MyAppPublisher "星纬（海口）投资有限公司"
#define MyAppURL "https://www.awesomenovel.com"
#define MyAppExeName "AwesomeNovel.exe"

[Setup]
; 基础设置
; 许可协议页：展示仓库根 LICENSE（EULA v2026.09），未点「我接受」不能继续；
; 静默安装（/SILENT）按 EULA 条款视同接受。路径相对本文件：..\..\..\ = 仓库根。
; 全局 directive 对双语言生效（现有 [Languages] 均无 per-language LicenseFile 覆盖）。
LicenseFile=..\..\..\LICENSE
AppId={{B8F1A2D3-4E5F-6A7B-8C9D-0E1F2A3B4C5D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
; 默认安装位置＝用户可写目录（Windows 标准 per-user 程序目录），**不给 Program Files**：
; 数据目录跟随程序目录（便携式，data\ 在安装目录下），装到 Program Files 后标准
; 用户无权写库——应用以普通身份启动时后端直接死，界面只剩「正在启动…」页。
; 位置由用户定：安装位置页恒显示（含升级），可改到 D:\AwesomeNovel 等任意目录。
DefaultDirName={localappdata}\Programs\{#MyAppDirName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; ⚠️ 恒显示「选择安装位置」页（Inno 默认 auto＝升级时静默沿用旧目录、用户无从确认）。
; 数据跟着程序目录走，安装位置即用户数据落点：升级时用户要把老目录里的 data\
; 一并考虑（换位置＝看不到旧作品，找回入口见空书架态）。
DisableDirPage=no
; 升级时（同 AppId 已装）预填「上一次的安装目录」而不是本文件的默认值——用户直接
; 下一步＝原地升级、data\ 不动；想换位置也能在这一页改。缺了它，升级页预填的是新
; 默认值，老用户随手下一步就把数据落到新目录、看起来像「书没了」。默认即 yes，显式钉住。
UsePreviousAppDir=yes
; 输出
OutputDir=..\dist
; 安装包文件名（品牌更名 2026-10-05 用户拍板：直接改名，不留旧名过渡产物）。
OutputBaseFilename=AwesomeNovel_Setup_v{#MyAppVersion}
; 图标
SetupIconFile=icon.ico

; ── 代码签名（可选）：安装器由构建脚本在 iscc **之后**用 signtool 直接签 ────────
; 判例（2026-10-06 CI 演练实锤）：[Setup] SignTool 的值必须是「**已定义过的工具名**」
; （要用 iscc 的 -s/--signtool 先定义该工具），直接写内联命令会被判
; 「Value of [Setup] section directive "SignTool" is invalid」。
; 故本文件不再声明 SignTool；安装器签名走构建脚本（build_release.ps1 / client-package.yml
; 的「iscc → sign → verify」三步，见 docs/ops/client-code-signing.md）。
; 已知缺口：Inno 的 SignedUninstaller 只能靠 SignTool 机制，本路径下**卸载器不含签名**
; （卸装时 UAC 显示未知发布者）；将来若需要，改回「命令行定义工具名」形态即可。

; 压缩
Compression=lzma2/ultra
SolidCompression=yes
; Windows 版本要求
MinVersion=10.0.0
; 管理员权限：HKLM 卸载登记项、公用桌面快捷方式，以及下面 [Dirs] 给数据目录
; 授「标准用户可写」ACL 都需要提权（安装目录本身默认在用户可写位置）。
; 注：Inno 会对「admin 模式 + {localappdata}」给一条 UsedUserAreas 提示——这里是
; 有意取舍：安装者与使用者是同一账户时路径即本人目录（提权不换用户），而提权换来
; 的 ACL 能力正是「用户自选受限目录也能写库」的兜底；换纯 per-user 安装
; （PrivilegesRequired=lowest）则 {commondesktop} 与 Permissions 都不可用，
; 需同批改按用户桌面/去 ACL，另立 change 再谈。
PrivilegesRequired=admin
; 卸载
Uninstallable=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
; ChineseSimplified.isl 为 Inno Setup 非官方语言包，Inno Setup 安装器默认不提供 →
; 仓库 vendor（languages/ChineseSimplified.isl，源自 jrsoftware/issrc），相对路径引用
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; 安装位置页提示（评审整改 2026-10-06）：位置页现恒显示（含升级），而安装目录就是
; 书稿数据落点（data\ 在安装目录下）——改目录＝看不到旧作品，必须在这一页讲明。
; 标准句原文保留（中文取自 vendored ChineseSimplified.isl，英文取自 Inno Default.isl）。
chinesesimplified.SelectDirLabel3=安装程序将安装 [name] 到下面的文件夹中。%n%n注意：你的书稿保存在这个目录下的 data 文件夹里。升级请沿用原目录；换了目录会看不到已有的书（需要把旧 data 文件夹拷过来）。
english.SelectDirLabel3=Setup will install [name] into the following folder.%n%nNote: your books are stored in the "data" subfolder of this location. When upgrading, keep the existing location — choosing a different one hides your existing books.

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Files]
; PyInstaller onedir 输出的所有文件
Source: "dist\AwesomeNovel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; EULA 与第三方声明落安装目录根（与 _internal\ 内 PyInstaller datas 双份属预期冗余）
Source: "..\..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\..\THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; 清理 ≤v0.26 安装包留下的残缺改名件：旧版在 [Run] 里把卸载器改名为 uninstall.exe
; （配套 .dat 没跟着改名，注册表卸载项也没同步）→ 用户双击必报「uninstall.dat 不存在」。
; 新版不再改名，这里顺带删掉这对残件，免得升级后的用户继续点到它；卸载器本体由 Inno
; 以原名 unins000.exe 重建，见下方 [Run] 段说明。
Type: files; Name: "{app}\uninstall.exe"
; ≤v0.27 的程序本体名为 AI Novel.exe：升级时删掉残留，免得新旧两个 exe 并存
; （桌面/开始菜单快捷方式由同一 AppId 的 Inno 记录接管，只留新的）。
Type: files; Name: "{app}\AI Novel.exe"
Type: files; Name: "{app}\uninstall.dat"

[Dirs]
; 数据目录（便携式：库/备份都在 {app}\data）必须对标准用户可写——应用是普通
; 身份启动的，写不进去就是「后端静默死、只剩正在启动页」。默认位置已可写，
; 这里显式授 ACL 兜住用户自选受限目录（如仍装到 Program Files）的情形。
Name: "{app}\data"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; ⚠️ 勿再重命名 unins000.exe（v0.26 卸载事故成因）：Inno 卸载器按「自身文件名」推导
; 数据文件（uninstall.exe 会去找 uninstall.dat），且安装期写死的注册表卸载项
; UninstallString 固定指向 unins000.exe——只改 exe 会让「设置 → 应用」与安装目录内
; 双击两条卸载路径同时失效，报「uninstall.dat 不存在，无法卸载」。Inno 未提供卸载器
; 改名机制，卸载器必须保持 unins000.exe + unins000.dat 成对原始名。
; 安装完成后是否立即运行
Filename: "{app}\{#MyAppExeName}"; Description: "运行 {#MyAppName}"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; 卸载时清理运行时目录（日志/端口文件/"启动失败"页）。两个名字都清：AwesomeNovel
; 为现名，AI Novel 是 ≤v0.27 旧名（Windows 侧日志目录不搬迁，留着历史日志）。
; 注意 Windows 的**书稿数据**不在这个目录——它在 {app}\data（便携式），随 [Files] 一并移除。
Filename: "{cmd}"; Parameters: "/C rmdir /S /Q ""{userappdata}\AwesomeNovel"""; Flags: runhidden; RunOnceId: "CleanRuntimeDir"
Filename: "{cmd}"; Parameters: "/C rmdir /S /Q ""{userappdata}\AI Novel"""; Flags: runhidden; RunOnceId: "CleanLegacyRuntimeDir"
