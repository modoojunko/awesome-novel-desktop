# Tasks: relicense-proprietary

## 1. Worktree 与法律文件落库

- [x] 1.1 从主仓绝对路径 `git worktree add` 建隔离分支 `feat/relicense-proprietary`（避开 main 检出的其他会话脏文件）——验证：worktree 检出干净、分支指向当前 main
- [x] 1.2 用《爱小说桌面软件最终用户许可协议 v2026.09》替换根 `LICENSE`（署名星纬（海口）投资有限公司；**两层授权**＝客户端免费使用许可＋增值功能按已购授权；协议位阶/条款变更/静默安装视同接受/争议解决沿用 v2026.08 不约定管辖法院，按 design D1；UTF-8 带 BOM；文件头注「商用前建议法律审校」）——验证：`xxd LICENSE | head -1` 首三字节 `ef bb bf`；正文含「免费」授权段、署名与 support@xingweitouzi.cn
- [x] 1.3 新建根 `THIRD-PARTY-NOTICES.txt`（文件头适用范围行＋certifi 的 MPL-2.0 许可证全文＋PyInstaller bootloader GPLv2 与官方闭源商用例外声明＋运行时依赖宽松许可归属清单，取自审计结论）——验证：grep 到 MPL-2.0 全文标志段与 PyInstaller 例外字样；全文无「本项目以 GPL 授权」类表述
- [x] 1.4 `docs/legal/README.md` 增加一行索引指向根 LICENSE（桌面软件 EULA）——验证：链接可达、不建镜像副本

## 2. 打包链路接入

- [ ] 2.1 `client/packaging/build/installer.iss`：`[Setup]` 段加 `LicenseFile=..\..\..\LICENSE`；`MyAppURL=https://www.awesomenovel.com`；`MyAppPublisher=星纬（海口）投资有限公司`——验证：从 .iss 所在目录 `../../..` 到仓库根 LICENSE 存在；grep 原 GitHub URL 零命中；不加 per-language LicenseFile 覆盖
- [ ] 2.2 `client/packaging/build/build.spec` datas 增 `(LICENSE, ".")` 与 `(THIRD-PARTY-NOTICES.txt, ".")`——验证：本地 pyinstaller 冒烟后 `dist/AI Novel/_internal/` 出现两份文件（注意 PyInstaller ≥6 datas 落 `_internal/` 非产物根）
- [ ] 2.3 `installer.iss` `[Files]` 加两条显式条目：`Source: "..\..\..\LICENSE"` 与 `"..\..\..\THIRD-PARTY-NOTICES.txt"`，均 `DestDir: "{app}"`——验证：Windows 用户安装目录根可见两份文本（`{app}` 根与 `_internal\` 双份属预期冗余）
- [ ] 2.4 `.github/workflows/client-package.yml`：复制 release.json 断言模式，加 `find` 断言两份文本烘进产物；DMG 打包步骤往 staging `cp` 两份文本与 .app 并排；顺手修正「历史版本获取由 GitHub Release 承接」注释——验证：workflow yaml 语法检查通过，断言步骤与既有步骤同风格

## 3. S端 落地页与官网死链修复

- [ ] 3.1 `server/frontend/src/constants/client-release.ts`：`RELEASES_PAGE_URL` 改 `releaseNotesUrl(ver)` 函数（返回 `https://www.awesomenovel.com/download/v<ver>/notes.html`）；**消费方逐个改**：DownloadModal.vue（「查看其他版本 →」→「查看更新说明 →」＋降级态不渲染该链接＋加「下载即表示同意《最终用户许可协议》」微文案链到 /legal/eula.html）、AuthPage.vue:36/:124（降级下载出口改版本无关目标＝官网落地页，函数化后原常量引用必编译红）、FooterSection.vue:9（页脚 GitHub 项删除）——验证：`grep -rn "github.com/modoojunko" server/frontend/src` 零命中
- [ ] 3.2 S端 e2e/单测：**新增**断言（原用例不覆盖这些点，文案改动零现存用例变红）——「查看更新说明 →」文案、href 同源 notes.html 且与 pill 版本一致、降级态无版本链接、同意微文案可见；e2e fixtures 增 `/download/latest.json` mock 覆盖成功/降级两态——验证：相关 spec 本地跑绿
- [ ] 3.3 `ActivationGuideSection.vue` 激活指引「下载安装」文案去「GitHub Releases」化，改官网下载口径；landing.spec.ts 补文案断言——验证：grep `GitHub Releases` 于 server/frontend/src 零命中，e2e 绿
- [ ] 3.4 EULA 官网公示：`/legal/eula.html` 由根 LICENSE 构建期复制生成（构建脚本或 workflow cp，防手工双源；文件含版本号 v2026.09）；`SiteBeianBar.vue` 法律链接区加「软件许可协议」——验证：本地构建后 public/legal/eula.html 存在且内容与 LICENSE 一致，页脚链接可达
- [ ] 3.5 `FALLBACK_VERSION` 0.11 → 当前线上版本——验证：与 latest.json 线上值一致
- [ ] 3.6 `npx vue-tsc --noEmit`（server/frontend）绿＋S端 相关 e2e 全量跑绿

## 4. C端 与 README 清理

- [ ] 4.1 C端 `LandingPage.tsx` `TUTORIAL_URL` 改官网地址＋`__tests__/landingPage.test.tsx` 断言同步——验证：`grep -rn "github.com/modoojunko" client/frontend/src` 零命中，该单测绿
- [ ] 4.2 `README.md` 与 `README.zh.md`：「许可证」章节改专有声明（指向 LICENSE 与 THIRD-PARTY-NOTICES.txt）；快速开始 clone 命令改内部开发者口径（私有 remote `git@github.com:modoojunko/awesome-novel-desktop.git`）——验证：两个 README grep `GPLv3|GNU` 零命中
- [x] 4.3 删旧构建产物（删前 `git status` 逐一确认 untracked/ignored，已实勘三处均 gitignored 零 tracked）：`client/packaging/build/dist/`（68M，含 GPLv3 头旧 reference .py）、`client/packaging/build/build_py/`、`client/reference/.mimosa/`——验证：三目录不存在、git status 无新差异
- [x] 4.4 全库 GPL 复核：`grep -rn "GNU GENERAL PUBLIC\|GNU General Public\|GPLv3\|gpl-3"` 排除 `.venv`/`node_modules`/`.git`/`.worktrees`/`.wxpay-deploy-staging` 与已知误报（`.gnum` CSS 类、genre-signup 文件名、base64 哈希）后零命中；确认 `.venv`/`node_modules` 内第三方自带 LICENSE 文件原样保留

## 5. CI 依赖许可证门禁

- [x] 5.1 `client/frontend/scripts/check-npm-licenses.mjs`：零依赖读 package-lock.json；**跳过键为空串的根条目**；许可证串逐 token（` AND `/` OR ` 大小写不敏感＋逗号）全部命中白名单才绿，OR 任一不在白名单即红；白名单＝MIT/MIT-0/ISC/Apache-2.0/BSD-2-Clause/BSD-3-Clause/BlueOak-1.0.0/CC0-1.0/CC-BY-4.0/MPL-2.0/PSF-2.0（与后端立场统一）；UNLICENSED/UNKNOWN 红；注释写明「首个误红请补白名单而非改脚本」——验证：对当前 lockfile 退出码 0（实勘 9 种 license 值全在白名单）；对注入 GPL-3.0 条目的临时副本非零；新脚本不在 tsc 编译面
- [x] 5.2 `client-frontend-ci.yml` 增门禁 step——验证：step 写法与既有 steps 同风格
- [x] 5.3 `client/backend/scripts/check_py_licenses.py`：importlib.metadata 扫 venv，**三级取值（License-Expression → License → classifier）＋别名归一化＋token 化同前端**（主流包 PEP 639 只有 License-Expression、aiosqlite 只有 classifier、distro='Apache License, Version 2.0' 等自由文本）；白名单同 5.1；fixture 覆盖 PEP639-only/classifier-only/'MIT License'/'MIT OR Apache-2.0'/'Apache-2.0 OR BSD-3-Clause'/GPL stub；脚本过 `ruff check .`；docstring 注明本地全量 venv 跑必红属预期、严禁复用到 client-package.yml——验证：在只装 `client/backend/requirements.txt` 的 venv 退出码 0；各 fixture 按预期红绿
- [x] 5.4 `client-backend-ci.yml` 门禁 step 插在 `pip install -r requirements.txt` 与 dev 工具（ruff/pytest）安装**之间**——验证：step 顺序正确
- [x] 5.5 S端 依赖一次性 AGPL 排查（server/requirements.txt 全包＋server/frontend package-lock；AGPL 由网络使用触发，S端 免常驻门禁但需摸底）——验证：产出排查结论记入本 change 目录，命中即报不阻塞

## 6. 验证与交付

- [x] 6.1 C端 前端回归：`npx tsc --noEmit`＋`npx vitest run`（client/frontend，含 landingPage.test 新断言）绿
- [x] 6.2 C端 后端回归：`python -m pytest tests/ -q`（client/backend）绿
- [ ] 6.3 worktree 内提交、推 `feat/relicense-proprietary`、`gh pr create`（PR 描述注明：S端 落地页改动合并后需 MCP 部署 novel-s-web 才上线；硬门槛＝首个付费用户前完成 EULA 法律审校）——验证：PR CI 全绿后停合并审批口
- [ ] 6.4 发版窗口核验（合并后下一次 `v*` tag，双平台拆两条）：Windows＝许可页中文无乱码、未点「我接受」不可继续、安装目录根两份文本；macOS＝挂载 DMG、根目录两份文本与 .app 并排——验证：截图留档到 change 目录
- [ ] 6.5 发版纪律：tag 附注含一行「本版本起软件采用专有许可，协议见官网」（经既有 notes 管线自动进 latest.json 与 notes.html）——验证：latest.json notes 含该行
