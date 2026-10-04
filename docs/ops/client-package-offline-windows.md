# Ops：C端 Windows 安装包离线打包（Actions 不可用时）

> 背景：2026-10-03 起 GitHub Actions 账户级熔断（所有 workflow 启动期秒挂，存储删除后的
> 重算窗口过了仍不解封＝计费侧 enforcement，只有账号主人能处理）。PyInstaller 不能交叉
> 编译——exe 必须在真 Windows（x64）上构建；Apple Silicon 虚拟机的 Windows ARM64 打出的
> ARM 包 x64 用户装不了，此路不通。本单＝在任意一台 x64 Windows 机器上复刻 CI 的
> Windows 链，产物与 CI 同等效力（Windows 安装包 CI 本来就不签名）。

## 前置（一次性）

- Git、Node.js 20+、Python 3.12+（pip 在 PATH）
- Inno Setup 6+：装完确认 `iscc` 在 PATH，或在默认路径 `C:\Program Files (x86)\Inno Setup 6\`（没有就 `choco install innosetup -y`）
- 仓库检出 **main 最新**（`git clone … ` 后不动，或已有检出 `git pull`）。
  ⚠️ 别 checkout `v*` tag——打包脚本 `build_release.ps1` 合入在 v0.26 tag **之后**，
  tag 检出里没有它，回落老 `build.bat` 会打出缺 release.json 的错包（打的是老配方）。
  版本号不用担心：脚本从检出的最新 `v*` tag 自动取（main 在 v0.26 后未发新 tag → 自动 0.26；
  发版内容以客户端代码为准，打包脚本本身不进产物）。

## 打包（一条命令）

```powershell
cd client\packaging\build
powershell -ExecutionPolicy Bypass -File build_release.ps1          # 版本取自检出内最新 v* tag
# powershell -ExecutionPolicy Bypass -File build_release.ps1 0.26   # 或显式指定
```

脚本七步与 CI 逐条对齐：前端构建 → release.json 生成（S端 端点已内置生产缺省值，
预置 `RELEASE_*` env 可覆盖）→ 依赖安装 → PyInstaller（APP_VERSION 注入 exe 版本资源）
→ 三件断言（release.json/LICENSE/THIRD-PARTY-NOTICES 必须真实烘进产物＋release_json_assert）
→ 冒烟（`--smoke` 无头，轮询 `%APPDATA%\AI Novel\port.json` 探 health＋断言 SPA 在服务）
→ Inno Setup 出包。

**产物**：`client\packaging\dist\AI_Novel_Setup_<version>.exe`。
SmartScreen 首次运行提示「未知发布者」属预期（CI 包同款不签名），点「仍要运行」。

## 出包后的发布末公里（在 Mac 上做即可，不需要 Windows）

GitHub Release ＋ CDN 的正式发布链在 `client-package.yml` 的 release job。离线包先冒烟安装
验证，待 Actions 解封后 `gh run rerun 37130854581` 走官方链（双包＋Release＋latest.json 上
CDN 一条龙）即可归位；若解封遥遥无期再手工补：`gh release create v0.26 <exe> <dmg>`＋
tcb 静态托管上传 latest.json（配方在 release job 步骤内）。

## 判例

- `release.json` 生成对版本形态有校验（须 `0.x(.y)` 可带后缀），`--help` 都会报 AssertionError——传参别带杂字符。
- Git Bash 跑 iscc 会被 MSYS2 路径转换坑（`/DMyAppVersion=` 被转成路径）——CI 用 `MSYS2_ARG_CONV_EXCL=*`；本脚本走 PowerShell 原生无此坑。
- Apple Silicon 本机的 mac 包（`build_mac.sh`，ad-hoc 签名）随时可打，用户拍板先解决 Windows。
