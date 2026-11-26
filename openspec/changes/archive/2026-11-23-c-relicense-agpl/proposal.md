# Proposal: c-relicense-agpl

## Why

本仓已定走开源路线（仓库现为 public），但根 `LICENSE` 仍是 #498（relicense-proprietary）换上的专有《最终用户许可协议 v2026.09》：协议明文禁止复制、再分发与反向工程，与「开源」在字面上直接冲突，GitHub 亦只能把本仓识别为 "Other"。同时本仓血统即开源项目 awesome-novel-agent（AGPL-3.0），公开路线下许可口径与血统一致才是自洽终态。

本次为 #498 的反向 relicense：专有 EULA → GNU AGPL-3.0。审计前提已由 #498 建立（全 git 历史唯一版权人、无第三方贡献、C端 分发物零 copyleft 依赖、S端 一次性 AGPL 摸底零命中），两仓同一版权人，换回开源无版权障碍；AGPL 为授权扩展，不缩减存量用户已取得的任何权利。

## What Changes

- **BREAKING**（授权模式）：根 `LICENSE` 由中文专有 EULA 全文替换为 GNU AGPL-3.0 标准全文（661 行／34523 字节，ASCII 无 BOM；取自血统仓 awesome-novel-agent 的 LICENSE，与 GNU 官方 agpl-3.0.txt 同文）。版权行＝星纬（海口）投资有限公司；SPDX 口径 **AGPL-3.0-only**（不把未来版本条款自动引入）。
- README 双语「许可证」章节改为 AGPL-3.0 开源声明：自由使用/修改/分发＋网络服务对应源码义务（第 13 条）＋源码仓库入口；账号、在线服务与增值功能仍由《用户服务协议》《付费须知》等规范（付费体系不动）。
- Windows 安装器删除许可接受页（`[Setup]` 段 `LicenseFile`）：AGPL 是授权声明而非接受式合同，安装期「我接受」门槛随 EULA 一并退役；许可全文继续随包（Windows `{app}` 根；macOS .app 内＋DMG 根），官网公示保留。
- `THIRD-PARTY-NOTICES.txt` 首部自身许可声明改 AGPL-3.0 口径并补源码地址（分发物的源码可得性）。
- `docs/legal/README.md` 索引行同步（LICENSE 定位＝开源许可；接受时点＝无点击接受）。
- 前端 `client/frontend/package.json` 增 `"license": "AGPL-3.0-only"` 元数据。
- 依赖许可证门禁（前后端白名单制）**行为不变**，零改动：AGPL 允许 AGPL 兼容的 copyleft 依赖，但白名单制是更严的主动收敛（保留再许可自由、不引入额外源码义务面），照旧拦截 GPL/AGPL/SSPL 依赖。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `installer-release`:
  - REMOVED「安装器许可协议页」：点击同意页随 EULA 退役（无替代需求；许可随包义务由「安装包随附许可与第三方声明」承担）
  - REMOVED「EULA 官网公示」＋ADDED「开源许可官网公示」（整体翻转，照 c-api-config-vendor-defaults 先例）：官网公示 AGPL-3.0 全文与源码入口，页面去 `eula` 命名；下载弹窗删「下载即表示同意」类微文案
  - MODIFIED「安装包随附许可与第三方声明」：随包文本改「许可全文（GNU AGPL-3.0，与根 LICENSE 同源）」；第三方声明须声明本项目自身以 AGPL-3.0 授权＋源码地址，不得再描述为专有
  - MODIFIED「落地页下载入口」：删许可同意微文案一句；全站口径改为「不引导 GitHub Releases 获取安装包」＋源码仓库入口按「开源许可官网公示」提供

## Design Impact

- 受影响端：C端（Windows 安装向导少一页许可接受页——安装链路，非应用界面；无视觉体系改动）。S端 落地页/官网许可页为**跨仓同批**改动（S端 源码在独立私有仓，见 tasks 第 4 节未完成项），本 change 不在此仓做 S端 前端实现。
- 不触碰两端共享段（base.css 令牌/基础类/组件词汇）；无原型先行需求（安装器许可页为 Inno 内置向导页，不在像素 parity 基线内）。
- 设计工件：无（本次零视觉决策）。

## Impact

- 法律文件：根 `LICENSE`（AGPL-3.0 单一事实源）；`THIRD-PARTY-NOTICES.txt`；`docs/legal/README.md` 索引行
- 打包链路：`client/packaging/build/installer.iss`（删 `LicenseFile`＋注释；`[Files]` 随包两条保留）、`client/packaging/build/bundle_manifest.py`（datas 单源，仅注释）、`.github/workflows/client-package.yml`（仅注释；烘焙断言与 DMG 副本逻辑不变）
- 仓库文案：`README.md`、`README.zh.md`（许可章节、血统句、clone 地址与 `cd` 目录名）
- 前端元数据：`client/frontend/package.json`（license 字段）
- 跨仓待办（不随本仓合并生效）：S端 私有仓（**私有专有，代码与仓库许可口径不变、不适用 AGPL**）侧的「C端 许可公示链」同批更新——其根 `LICENSE` 副本（＝C端 许可公示文本，`copy-eula.mjs` 的输入，非 S端 代码许可声明）＋落地页 5 件（`DownloadModal.vue`／`SiteBeianBar.vue`／`scripts/copy-eula.mjs`／`public/legal/eula.html`／e2e `download-modal.spec.ts`）；S端 改动需经部署通道发布后才上线
- 边界：付费/套餐体系、`docs/legal` 四件套协议内容、S端 代码许可口径均不变；`docs/reference/天父*.md` 第三方小说文本严禁打入分发包（原样保留）；#498 的「首个付费用户产生前完成 EULA 法律审校」硬门槛随 EULA 退役而消失，待审面转移为 AI 生成代码权属说明与 v2026.10 协议批次的真人终审（另线）
