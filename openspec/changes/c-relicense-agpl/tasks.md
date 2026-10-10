# Tasks: c-relicense-agpl

## 1. 许可与声明

- [x] 1.1 根 `LICENSE` → GNU AGPL-3.0 标准全文（661 行／34523 字节，sha256 `0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0`，无 BOM；取自血统仓 awesome-novel-agent 的 LICENSE，与 GNU 官方 agpl-3.0.txt 同文）
- [x] 1.2 `THIRD-PARTY-NOTICES.txt` 首部：自身许可声明改 GNU AGPL-3.0（SPDX: AGPL-3.0-only）＋补源码仓库地址
- [x] 1.3 `README.md`／`README.zh.md`：许可章节改 AGPL-3.0 开源声明（第 13 条网络服务源码义务＋付费范围界定）；血统句补「本仓库同样以 AGPL-3.0 开源」；clone 地址改 https＋修正 `cd` 目录名
- [x] 1.4 `docs/legal/README.md` 索引行：LICENSE 定位／接受时点改开源口径
- [x] 1.5 `client/frontend/package.json` 增 `"license": "AGPL-3.0-only"`

## 2. 打包与安装链路

- [x] 2.1 `client/packaging/build/installer.iss`：删 `[Setup]` 段 `LicenseFile`，注释改为「开源许可无接受门槛，全文走随包＋官网」；`[Files]` 两条随包条目保留（仅改注释）
- [x] 2.2 随包清单注释同步：datas 主清单已随 `c-nuitka-full` 抽到 `client/packaging/build/bundle_manifest.py`（`build.spec` 改为 import）——改该文件 LICENSE 条目注释（条目本身不动）
- [x] 2.3 `.github/workflows/client-package.yml` 两处注释同步（烘焙断言与 DMG 根副本逻辑不动）

## 3. 规格与校验

- [x] 3.1 `installer-release` delta：REMOVED「安装器许可协议页」「EULA 官网公示」＋ADDED「开源许可官网公示」＋MODIFIED「安装包随附许可与第三方声明」「落地页下载入口」（场景只能保名改内容，翻转需求走 REMOVED＋ADDED 先例）
- [x] 3.2 `openspec validate c-relicense-agpl --strict` 通过；`openspec validate --specs --strict` 基线不回归
- [x] 3.3 现行面残留 grep：无「专有软件／EULA v2026.09／点击接受」表述残留（历史归档、docs/marketing 评审稿、docs/archive 除外）
- [x] 3.4 依赖门禁行为不变：`check_py_licenses.py`／`check-npm-licenses.mjs`／两条 CI step 零改动，仍拦截 GPL/AGPL/SSPL 依赖
- [ ] 3.5 联动在途 change `c-nuitka-full`（未归档）：其 installer-release delta 中「EULA/第三方声明随包行为」措辞随本 change 过时，其归档时改为「许可全文/第三方声明」

## 4. 跨仓同批（不随本仓合并生效，发布门禁）

前提口径（2026-10-06 用户明确）：**S端 私有仓为私有专有代码，不适用 AGPL、不改其仓库许可**。以下各项仅涉及「官网作为 C端 下载渠道，公示 C端 开源许可」的文本与文案；该仓根 `LICENSE` 副本是 C端 许可文本的公示用副本（`copy-eula.mjs` 的输入），不是 S端 代码的许可声明。

- [ ] 4.1 S端 私有仓根 `LICENSE` 副本（＝C端 许可公示文本）同步替换为 AGPL-3.0 全文；S端 代码自身的私有专有口径不变
- [ ] 4.2 S端 落地页：`server/frontend/src/components/download/DownloadModal.vue` 删「下载即表示同意《最终用户许可协议》」微文案；`server/frontend/src/components/site/SiteBeianBar.vue` 与页脚法律链接区改「开源许可（AGPL-3.0）」口径
- [ ] 4.3 S端 `server/frontend/scripts/copy-eula.mjs` 与 `public/legal/eula.html`：页面去 `eula` 命名与「EULA v2026.09」标题（如 `/legal/agpl.html`、标题「开源许可（AGPL-3.0）— 爱小说」），生成逻辑保持根 LICENSE 单源；S端 `docker-compose.yml` 注入链注释同步
- [ ] 4.4 S端 `e2e/tests/download-modal.spec.ts`（及相关 landing 断言）去掉同意微文案断言；勿动 `server/frontend/package.json` 的许可口径（S端 仓保持私有）
- [ ] 4.5 S端 改动经既有部署通道发 novel-s-web 上线后，核对线上许可页内容与两仓根 LICENSE 逐字一致、下载弹窗无同意式文案
- [ ] 4.6 联动在途 change `s-web-image-build` 任务 2.2：其断言「`/legal/eula.html` 内容含『软件许可协议（EULA v2026.09）』」须随 S端 批改为 AGPL 口径，勿原样执行

## 5. 发版带出

- [ ] 5.1 下次 `v*` 发版：tag 附注写明「本版本起客户端以 AGPL-3.0 开源，许可见官网」；随包文本与安装器新形态随 CI 烘焙断言带出
