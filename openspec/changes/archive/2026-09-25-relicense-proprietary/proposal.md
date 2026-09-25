# Proposal: relicense-proprietary

## Why

项目已转闭源商用（仓库已私有化），但根 LICENSE 仍是 2026-05-06 引入的 GPLv3 标准全文，README 双语章节同步声明 GPL——授权模式与商业现实相反。同时仓库转私有后，落地页下载弹窗「查看其他版本 →」仍指向公开 GitHub Releases（已 404），直接违反 installer-release 既有「非 404」条款。换闭源前已完成两项审计：全 git 历史唯一版权人（单作者邮箱，无第三方贡献/子模块/外部版权头）、C端 分发物零 copyleft 依赖（第三方依赖全为宽松许可），因此换协议无法律障碍、不存在被第三方强制开源的路径。

## What Changes

- **BREAKING**（授权模式）：根 `LICENSE` 由 GPLv3 全文替换为星纬（海口）投资有限公司署名的《爱小说桌面软件最终用户许可协议（EULA）v2026.09》完整中文文本（UTF-8 带 BOM）。**两层授权**：客户端软件本身向任何用户授予免费使用许可（与「免费下载」模式自洽），增值功能/服务按已购授权与账号提供（细则引《付费须知》不重复）；另含协议位阶（EULA 管软件本体、冲突时付费场景以用户服务协议为准）、条款变更（官网公布生效）、静默安装视同接受、争议解决沿用 v2026.08 口径（不约定管辖法院）
- EULA 官网公示：构建期由根 LICENSE 原样复制生成官网法律页（`/legal/eula.html`，挂页脚法律链接区），下载弹窗加「下载即表示同意」微文案——macOS 用户安装前唯一可达的协议告知通道
- Windows 安装器新增许可协议点击同意页（installer.iss `[Setup]` 段 `LicenseFile`），交互式安装未点「我接受」不能继续；静默安装（/SILENT）按 EULA 条款视同接受
- 安装包随包分发 EULA 与《第三方开源声明》`THIRD-PARTY-NOTICES.txt`（certifi MPL-2.0 全文、PyInstaller bootloader GPLv2＋官方闭源商用例外声明、宽松许可归属清单）——Windows 落安装目录根（`{app}`），macOS 落 .app 内 `_internal/`＋DMG 根副本；CI 增烘焙断言
- 修复转私有遗留死链（实勘全量）：S端 下载弹窗「查看其他版本 →」改「查看更新说明 →」指 `notes.html`、AuthPage 降级下载出口改官网落地页、页脚 GitHub 链接删除、激活指引文案去「GitHub Releases」化；C端 新手教程卡 `TUTORIAL_URL` 改官网＋单测同步；`FALLBACK_VERSION` 0.11→当前线上版本（兜底版本已滑出 CDN 保留窗，降级态下载链接本身 404）；README 快速开始 clone 地址改内部口径；installer.iss `MyAppURL` 改官网、`MyAppPublisher` 改备案公司
- README 双语「许可证」章节改为专有声明（指向 LICENSE 与 THIRD-PARTY-NOTICES）
- C端 前后端 CI 新增依赖许可证门禁：license 字段命中 GPL/AGPL/LGPL/SSPL 即红（certifi MPL-2.0 白名单放行，两端立场统一），防止未来无意引入 copyleft 依赖；另对 S端 依赖做一次性 AGPL 排查（AGPL 由网络使用触发，S端 免门禁的理由对它不成立，本次先摸底）
- 清理本地旧构建产物中带 GPLv3 文件头的残留（`client/packaging/build/dist/`、`build_py/`、`client/reference/.mimosa/`，均为 gitignored 产物，防重打包外流）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `installer-release`:
  - MODIFIED「落地页下载入口」：「查看其他版本 →」链接目标由公开 GitHub Releases 改为官网版本更新说明页（仓库已私有，原链接 404，既有「非 404」条款自转私有起即被违反）；降级态不渲染版本相关次级链接；新增下载同意微文案；激活指引/全站去 GitHub Releases 引导
  - ADDED「安装器许可协议页」：Windows 安装器展示 EULA 并要求点击接受（交互式安装；静默安装视同接受）
  - ADDED「安装包随附许可与第三方声明」：THIRD-PARTY-NOTICES 与 EULA 文本进入安装包（Windows `{app}` 根；macOS .app 内＋DMG 根）
  - ADDED「EULA 官网公示」：官网法律区由根 LICENSE 构建期复制生成 EULA 页，页脚可达，下载弹窗含同意微文案

## Design Impact

- 受影响端：S端（下载弹窗「查看更新说明 →」链接与同意微文案、AuthPage 降级出口、页脚删 GitHub 项、激活指引文案、新增 /legal/eula.html 法律页——均为链接/文案级，无视觉体系改动）；C端 仅一处（新手教程卡链接改官网，无界面结构改动；EULA 呈现在 Windows 安装器向导，属安装链路而非应用界面；macOS 无安装期点击，行业常态，EULA 随包＋官网公示）
- 不触碰两端共享段（base.css 令牌/基础类/组件词汇）；无需原型先行（零视觉改动）；设计工件由实现侧自查

## Impact

- 法律文件：根 `LICENSE`（EULA 单一事实源）；`docs/legal/README.md` 加索引行；S端 `public/legal/eula.html`（构建期生成）
- 打包链路：`client/packaging/build/installer.iss`（LicenseFile／MyAppURL／MyAppPublisher／`{app}` 根两条 [Files]）、`client/packaging/build/build.spec`（datas 增 LICENSE 与 THIRD-PARTY-NOTICES.txt）、`.github/workflows/client-package.yml`（烘焙断言＋DMG 根副本＋注释修正）
- S端 前端：`server/frontend/src/constants/client-release.ts`（RELEASES_PAGE_URL→releaseNotesUrl、FALLBACK_VERSION 刷新）及消费方（DownloadModal/AuthPage/FooterSection/ActivationGuideSection）、相关 e2e 断言
- C端 前端：`client/frontend/src/pages/LandingPage.tsx`（TUTORIAL_URL）＋对应单测
- CI：`client-frontend-ci.yml`、`client-backend-ci.yml` 增许可证门禁步骤（新增零依赖检查脚本）
- 仓库文案：`README.md`、`README.zh.md`
- 本地清理：`client/packaging/build/{dist,build_py}/`、`client/reference/.mimosa/`（gitignored 构建产物/缓存）
- 合并后 S端 落地页改动需经既有 MCP 部署通道发 novel-s-web 才上线（合并不自动部署）；对外打包效果随下一次 `v*` 发版自然带出
- **硬门槛：首个付费用户产生前必须完成 EULA 法律审校**（工程模板先行不阻塞，但带触发条件的门槛取代悬空待办）
- 明确边界：git 历史中旧 GPLv3 版本已被公开期获得者取得的 GPL 权利不可追回——已核验仓库 fork=0、无 star 群体，公开期暴露面约为零；16 个 Claude co-authored 提交的 AI 生成代码版权状态与 EULA 一起列入法律审校清单；`docs/reference/天父*.md` 为第三方受版权保护小说文本，严禁打入任何分发包
