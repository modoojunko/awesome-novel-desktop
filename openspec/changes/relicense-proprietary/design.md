# Design: relicense-proprietary

## Context

见 proposal.md「Why」。与实现直接相关的现状事实（含四路评审实勘修正）：

- 根 `LICENSE` 是 2026-05-06 引入的 GPLv3 标准全文（674 行，未改条款），README.md:155-157 与 README.zh.md:145-147 同步声明 GPL。
- 打包链路：PyInstaller `build.spec`（datas 只含前端 dist／backend reference／prompts／release.json／brand.json，**从未打入根 LICENSE**；datas 目标段 `"."` 实际落在 PyInstaller ≥6 的 `_internal/`，不是产物根）→ Inno Setup `installer.iss`（**无 LicenseFile**；`MyAppURL` 指向已私有仓库）→ `.github/workflows/client-package.yml`（已有 `find dist -name release.json` 烘焙断言模式可复制）。
- Inno Setup 事实：CI 走 choco 装 6.x Unicode 版；**6.3 起 LicenseFile 无 BOM 也按 UTF-8 解**，「无 BOM 按 ANSI」仅 ≤6.2 成立——BOM 照写无害（兼容本地旧 iscc），但不该作为 rationale 的依据。`LicenseFile` 是 `[Setup]` 段 directive（非 [Files] 参数）；现有 `[Languages]` 双语言均未设 per-language LicenseFile，全局指令对双语言生效。
- 转私有死链全景（评审实勘）：S端 `client-release.ts` 的 `RELEASES_PAGE_URL` 有**两个消费方**——下载弹窗 DownloadModal.vue:74 与 AuthPage.vue:36/:124（升级出口，恰在拿不到版本时渲染，`releaseNotesUrl(ver)` 对它无法取参）；FooterSection.vue:9 页脚 GitHub 外链；ActivationGuideSection.vue:6 激活指引文案引导去 GitHub Releases。C端 LandingPage.tsx:10 `TUTORIAL_URL` 指仓库 README，`landingPage.test.tsx:78` 断言钉死 `github.com`。S端 e2e 现无 latest.json mock（弹窗在 e2e 里恒走降级态）。
- 降级态结构性缺口：`FALLBACK_VERSION='0.11'`，线上已 v0.23，托管只留最近 2 版——兜底版本必滑出保留窗，降级态连下载直链都已 404（既有债）。流水线实序（转存→latest.json→校验→清理）保证**成功态**的 notes.html 链接永远可达。
- 本地旧构建产物残留 GPLv3 头：`client/packaging/build/dist/`（68M，含旧 reference 模块 GPLv3 头 .py）、`build_py/`（58M）、`client/reference/.mimosa/`（44K）——三者均 gitignored、零 tracked 文件、CI 每轮全量重建，删除安全。
- 依赖审计结论：C端 分发物零 copyleft；仅 certifi（MPL-2.0）与 PyInstaller bootloader（GPLv2＋闭源商用例外）需列明。**Python 侧元数据现状**：主流包已走 PEP 639（`License=None`＋仅 `License-Expression`），aiosqlite 只有 classifier，distro/uvloop/sniffio 为自由文本（'Apache License, Version 2.0'/'MIT License'/'MIT OR Apache-2.0'）——门禁脚本必须三级取值＋归一化。
- 公开期暴露面已核验：仓库 fork=0。
- S端 web 前端部署不随合并自动触发（MCP 直传 dist 通道）。

## Goals / Non-Goals

**Goals:**
- 仓库自身文件（源码/文档/打包配置）零 GPLv3 痕迹与零私有仓库死链；重打包不再外流任何 GPL 头文件
- Windows 安装器呈现 EULA 点击同意页；EULA 与第三方声明随包（Windows `{app}` 根／macOS .app 内＋DMG 根）并官网公示
- CI 挡住未来无意引入的 copyleft 依赖；S端 依赖 AGPL 摸底

**Non-Goals:**
- 不改写 git 历史（fork=0，公开期暴露面约为零；老版本 GPL 权利论已无关紧要）
- 不做 macOS 首启 EULA 弹窗（EULA 官网公示＋随包覆盖；**重估触发条件：首个 macOS 付费用户出现前**）
- 不做应用内「关于页/许可协议」入口（付费软件应有，属独立 C端 UI change，本次不加；同一触发条件）
- 不给 S端 挂常驻许可证门禁（不分发无 copyleft 分发义务；AGPL 以一次性排查摸底，命中再议）
- 不为降级态再造第二层兜底链路（同源 fetch 失败≈站点整体异常）；不为「浏览历史版本」建索引页（CDN 只留 2 版，给不存在的内容建基建）
- 不动 `.worktrees/*/LICENSE`（各并行会话工作区，合并时冲突自然暴露）

## Decisions

**D1 — EULA 单一事实源＝仓库根 `LICENSE`，文本为两层授权框架。**
署名星纬（海口）投资有限公司（与 ICP 备案、docs/legal 全套文件经营者一致）。**授权分两层：客户端软件本身向任何用户授予免费的、非独占的、不可转让的使用许可（与「免费下载」模式自洽——否则免费用户接受的是空授权）；增值功能/服务按已购授权与账号提供，细则引《付费须知》不重复条款。**另含：协议位阶（EULA 管软件本体，用户服务协议管账号与服务，付费场景冲突时以后者为准）、条款变更（官网公布生效＋重大变更提前公告）、静默安装视同接受、禁止行为（再分发/出租/反向工程/去版权标识）、第三方组件（指向 THIRD-PARTY-NOTICES）、知识产权、免责与责任限制、终止、争议解决沿用 v2026.08 口径（**不约定管辖法院**——勿推翻已拍板决策）、联系 support@xingweitouzi.cn。文件头注「商用前建议法律审校」；`docs/legal/README.md` 只加索引行不建副本（备选「docs/legal 做事实源」弃——双源必漂移）。

**D2 — LICENSE 写盘带 UTF-8 BOM，定位为兼容措施而非正确性依赖。**
Inno ≥6.3 无 BOM 也按 UTF-8 解，BOM 保留是为兼容本地旧 iscc；若异常，回退＝打包工作流内一行脚本从 LICENSE 生成带 BOM 副本再引用（不改事实源）。`LicenseFile` 写在 `[Setup]` 段；不要加 per-language 覆盖。

**D3 — 「查看更新说明 →」指向 `download/v<VER>/notes.html`；「永不 404」的成立域写清。**
成立域＝**链接版本 ∈ 托管保留集**：流水线实序（转存→latest.json→清理）保证成功态成立；降级态（兜底版本）与跨两次发版仍开着的旧弹窗不受保护——降级态按 spec 不渲染版本相关链接（warn pill 已明示），不为它造第二层兜底。`RELEASES_PAGE_URL` 常量改 `releaseNotesUrl(ver)` 函数，**消费方逐个过**：DownloadModal（有版本，改函数调用）与 AuthPage 降级出口（无版本，**换目标类型**——改指官网落地页 `https://www.awesomenovel.com`，版本无关）语义不同。`FALLBACK_VERSION` 0.11→当前线上版本，本 change 人工刷一次（根治＝发版流水线自动 bump，留作可选后续项）。文案「查看其他版本 →」→「查看更新说明 →」。S端 e2e 现无 latest.json mock——补 fixtures 覆盖成功/降级两态，新增断言（原文案改不动任何现存用例，「同步断言」的前提不成立，是**新增**）。

**D4 — 第三方声明文件与进包通道（注意 PyInstaller ≥6 布局）。**
新建根 `THIRD-PARTY-NOTICES.txt`：文件头适用范围行「本清单适用于《爱小说》桌面客户端分发包」＋ certifi MPL-2.0 全文＋ PyInstaller bootloader「GPLv2＋允许闭源商用分发的官方例外」声明＋运行时直接依赖宽松许可归属清单（取自审计）。`build.spec` datas 增两条（落 `_internal/`，macOS 唯一通道）；**installer.iss 另加两条显式 `[Files]`（`Source: "..\..\..\LICENSE"` / `"..\..\..\THIRD-PARTY-NOTICES.txt"`，`DestDir: "{app}"`）保证 Windows 用户在安装目录根可见**——`{app}` 根与 `_internal\` 双份属无害冗余，单一事实源不受影响。macOS DMG 根副本由 client-package.yml 打包步骤往既有 dmg staging `cp` 一行达成。client-package.yml 增 `find` 烘焙断言（复制 release.json 断言模式），把发版窗口人工核验前移为永久回归门禁；顺手修正该文件「历史版本获取由 GitHub Release 承接」注释（随本 change 成假命题）。

**D5 — installer.iss 四处。**
`[Setup]` 段 `LicenseFile=..\..\..\LICENSE`；`MyAppURL=https://www.awesomenovel.com`；`MyAppPublisher=星纬（海口）投资有限公司`；`[Files]` 两条 `{app}` 根（见 D4）。

**D6 — CI 许可证门禁＝白名单制、零依赖、宁红勿漏；Python 侧必须三级取值。**
- 前端 `client/frontend/scripts/check-npm-licenses.mjs`：读 package-lock.json（v3），**跳过键为空串的根条目**（无 license 字段，不跳首跑即红）；许可证串逐 token 解析（` AND `/` OR ` 大小写不敏感＋逗号），token 全部命中白名单才绿（OR 任一不在白名单即红，保守方向正确）；白名单＝MIT/MIT-0/ISC/Apache-2.0/BSD-2-Clause/BSD-3-Clause/BlueOak-1.0.0/CC0-1.0/CC-BY-4.0/**MPL-2.0**/PSF-2.0（**两端立场统一放行 MPL-2.0**——与 certifi 处理一致，不留「npm 超严、Python 放行」的意外政策）；UNLICENSED/UNKNOWN/无法识别一律红。实勘现存 9 种 license 值全部 ⊆ 白名单，首跑即绿。脚本不进 tsc 编译面（tsconfig include 仅 src）。
- 后端 `client/backend/scripts/check_py_licenses.py`：importlib.metadata 扫当前 venv，**三级取值：`License-Expression`（PEP 639，主流包现状）→ `License` → classifier（`License :: OSI Approved :: X` 行，aiosqlite 仅此）**；别名归一化（'MIT License'→MIT、'Apache License, Version 2.0'→Apache-2.0 等）；token 化同前端；白名单同前端（含 MPL-2.0、PSF-2.0——typing_extensions 实际是 PSF-2.0）。fixture 覆盖：PEP639-only／classifier-only／'MIT License'／'MIT OR Apache-2.0'／'Apache-2.0 OR BSD-3-Clause'／GPL stub。**门禁 step 插在 `pip install -r requirements.txt` 与 dev 工具安装之间**（dev 工具不进扫描面；若放最后需白名单全覆盖，取前者语义最净）。脚本须过 `ruff check .`；docstring 注明：本地全量 venv（含 pyinstaller/pywebview 全文 blob）跑必红属预期，**严禁复用到 client-package.yml**（该工作流把 pyinstaller 装进同一 venv）。
- 不新建 workflow；首跑遇白名单外的宽松许可＝一次「补白名单」评审，这是治理点不是 bug（脚本注释写明「首个误红请补白名单而非改脚本」）。

**D7 — 死链全清与文案。**
S端：DownloadModal（链接改 notes.html＋同意微文案）、AuthPage（降级出口改官网落地页）、FooterSection（页脚 GitHub 项删除——页脚已有 ICP/支持入口）、ActivationGuideSection（文案改官网下载口径）。C端：LandingPage `TUTORIAL_URL` 改官网（新手教程内容后续单独落官网页，本次先指官网域名）＋ `landingPage.test.tsx` 断言同步。`FALLBACK_VERSION` 刷新（见 D3）。README 双语：「许可证」章节改专有声明（指向 LICENSE 与 THIRD-PARTY-NOTICES.txt）；快速开始 clone 命令改内部开发者口径（私有 remote `git@github.com:modoojunko/awesome-novel-desktop.git`）。全库 grep `github.com/modoojunko` 于两端 src＋打包配置清零（`.venv`/`node_modules` 内第三方自带 LICENSE 文件必须保留——那是依赖自身的许可义务；`client/frontend/src/.mimosa/` 为本地缓存不入库，不处理）。

**D8 — EULA 官网公示＝构建期复制，非手工第二份。**
官网法律页机制现成（`server/frontend/public/legal/*.html`＋SiteBeianBar 页脚法律链接区）。`/legal/eula.html` 由根 LICENSE 构建期原样复制生成（构建脚本或 workflow 一行 cp——改 LICENSE 后重新构建即同步，无双源漂移；文件内含版本号 v2026.09 可探测漂移）；SiteBeianBar 法律链接区加「软件许可协议」一项；下载弹窗加同意微文案（见 spec）。这一并解决：macOS 用户安装前唯一可达告知、格式条款提示义务、存量版本「追溯覆盖」从论据变事实。

**D9 — 隔离与交付；部署时点写明。**
main 检出存在其他会话脏文件，全部在独立 worktree 分支 `feat/relicense-proprietary` 上做，单 PR 进 main。合并不自动部署：S端 落地页改动需经既有 MCP 通道发 novel-s-web 才上线（PR 描述注明）；打包效果随下一次 `v*` tag 带出；发版纪律＝tag 附注含一行「本版本起软件采用专有许可，协议见官网」（零成本，经既有 notes 管线自动进 latest.json 与 notes.html）。回滚 runbook：未发版 revert 即净回滚；**已发版后 revert 须同时暂停 v* tag 推送**（否则下一版会把 GPL LICENSE 打进闭源包并撤掉许可页，版本/许可 skew），已分发版本的 EULA 授予不因 revert 撤回。

## Risks / Trade-offs

- [EULA 为工程模板、未经法务终审] → 文件头标注；**硬门槛＝首个付费用户前完成法律审校**（与 16 个 Claude co-authored 提交一并列入审校清单）
- [门禁白名单遇新许可证形态误红] → 有意为之（宁红勿漏）；补白名单即解，脚本注释写明处置方式
- [macOS 侧 EULA 链路无法本地核验] → client-package.yml 烘焙断言（D4）＋发版窗口 DMG 挂载截图留档双闸
- [旧构建产物误删风险] → 三处已实勘 gitignored＋零 tracked，删前 git status 复核
- [S端 依赖 AGPL 未审计] → 本次一次性摸底任务兜住（5.5）；命中再立项
- [FALLBACK_VERSION 随发版再次滞后] → 本 change 人工刷一次＋spec 已把降级态版本链接摘除；根治（发版自动 bump）留可选后续项

## Migration Plan

单 PR 合并后：仓库与打包配置即时生效；S端 落地页经 MCP 部署 novel-s-web 上线；对外打包效果随下一次 `v*` 发版自然带出（EULA 安装页＋随附文本＋官网公示页）。已发布的 v0.23 安装包无 EULA 页属预期（官网公示＋零用户背景下无需追发）。回滚 runbook 见 D9。

## Open Questions

- EULA 法律审校的法务资源与时间点——已转为硬门槛（首个付费用户前），不再悬空；文本后续可改，结构与 spec 行为不受影响
