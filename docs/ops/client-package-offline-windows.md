# Ops：C端 Windows 安装包离线打包（Actions 不可用时）

> 背景：2026-10-03 起 GitHub Actions 账户级熔断（所有 workflow 启动期秒挂，存储删除后的
> 重算窗口过了仍不解封＝计费侧 enforcement，只有账号主人能处理）。PyInstaller 不能交叉
> 编译——exe 必须在真 Windows（x64）上构建；Apple Silicon 虚拟机的 Windows ARM64 打出的
> ARM 包 x64 用户装不了，此路不通。本单＝在任意一台 x64 Windows 机器上复刻 CI 的
> Windows 链，产物与 CI 同等效力（含代码签名：两边默认都用仓库自签证书签，配了正式证书两边都自动改用正式证书）。

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

脚本八步与 CI 逐条对齐：前端构建 → release.json 生成（S端 端点已内置生产缺省值，
预置 `RELEASE_*` env 可覆盖）→ 依赖安装 → PyInstaller（APP_VERSION 注入 exe 版本资源）
→ 三件断言（release.json/LICENSE/THIRD-PARTY-NOTICES 必须真实烘进产物＋release_json_assert）
→ 冒烟（`--smoke` 无头，轮询 `%APPDATA%\AwesomeNovel\port.json` 探 health＋断言 SPA 在服务）
→ 程序本体签名（默认自签）→ Inno Setup 出包（连卸载器一起签，并校验）。

**产物**：`client\packaging\dist\AwesomeNovel_Setup_<version>.exe`。

**代码签名**：**默认用仓库自签证书**出包（用户 2026-10-06 拍板「自签即可」）——导入过我们根
证书的机器（测试同学先跑 `client\packaging\cert\install_cert.bat`）会显示发布者
「Awesome Novel (Dev)」；对外部用户仍显示「发布者: 未知」，SmartScreen 也仍会拦。
配了正式证书（云签名 / USB token）自动改用它；`$env:AINOVEL_SIGN_DEV_CERT='0'` 可出未签名包。
细节与采购选项见 [`client-code-signing.md`](./client-code-signing.md)。

## 出包后的发布末公里（在 Mac 上做即可，不需要 Windows）

⚠️ **改过安装包文件名的版本（如 2026-10 品牌更名 AwesomeNovel）**：顺序固定——先跑 C端 发版（新名产物进 `download/v<VER>/`、`latest.json` 指到该版），**随后同一窗口**部署 S端 落地页（awesome-novel-server：安装包直链按新名拼接）。顺序不能反：落地页先切，`latest.json` 仍指向的上一版目录里找不到新名实物，用户点下载拿到的是托管兜底页（200 的 HTML）。


GitHub Release ＋ CDN 的正式发布链在 `client-package.yml` 的 release job。离线包先冒烟安装
验证，待 Actions 解封后 `gh run rerun 37130854581` 走官方链（双包＋Release＋latest.json 上
CDN 一条龙）即可归位；若解封遥遥无期再手工补：`gh release create v0.26 <exe> <dmg>`＋
tcb 静态托管上传 latest.json（配方在 release job 步骤内）。

## 判例

- `release.json` 生成对版本形态有校验（须 `0.x(.y)` 可带后缀），`--help` 都会报 AssertionError——传参别带杂字符。
- Git Bash 跑 iscc 会被 MSYS2 路径转换坑（`/DMyAppVersion=` 被转成路径）——CI 用 `MSYS2_ARG_CONV_EXCL=*`；本脚本走 PowerShell 原生无此坑。
- Apple Silicon 本机的 mac 包（`build_mac.sh`，ad-hoc 签名）随时可打，用户拍板先解决 Windows。
