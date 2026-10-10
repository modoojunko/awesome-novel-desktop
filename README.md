# 爱小说 · Awesome Novel

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue?style=flat-square)](LICENSE)

> awesome-novel-agent 第 5 代 —— 源自开源项目 <https://github.com/modoojunko/awesome-novel-agent>（AGPL-3.0）；本仓库同样以 AGPL-3.0 开源。

AI 辅助长篇小说创作平台 —— 单用户桌面应用，数据跟着你走。

通过结构化的六阶段工作流，将故事从构思推进到归档——世界构建、大纲、提示词工程、流式内容生成和归档。

面向中文小说作家，AI 作为创作伙伴而非代笔。每一个故事决策都由你掌控。

## 架构

```
┌─────────────────────────────────────────────────┐
│  C端 — 本地桌面应用 (client/)                     │
│                                                   │
│  ┌──────────┐    ┌──────────────┐    ┌─────────┐ │
│  │ pywebview │───>│  React SPA   │───>│ FastAPI │ │
│  │ 窗口      │    │  (localhost)  │    │ uvicorn │ │
│  └──────────┘    └──────────────┘    └────┬────┘ │
│                                           │      │
│                                  ┌────────▼────┐ │
│                                  │  SQLite      │ │
│                                  │  + 本地文件   │ │
│                                  └─────────────┘ │
│                                           │      │
│                                           ▼      │
│                                   ┌────────────┐ │
│                                   │ S端       │ │
│                                   │ (License   │ │
│                                   │  验证/登录) │ │
│                                   └────────────┘ │
└─────────────────────────────────────────────────┘
```

- **C端** — 你电脑上跑的一切：FastAPI + SQLite + React SPA，装在 pywebview 窗口里
- **S端** — License 授权与设备管理服务（FastAPI 2.0 重构版），部署在腾讯云 CloudBase；独立私有组件，源码不在本仓
- **数据** — SQLite 存元数据，YAML/MD 文件存小说内容，全在安装目录的 `data/` 下，可以随意备份和搬家

## 六阶段工作流

```
init → settings → outline → prompt → write → archive
```

| 阶段 | 说明 |
|------|------|
| **1. Init** | 创建项目，选择目录，AI 辅助填写故事梗概 |
| **2. Settings** | 世界设定、角色、文风、Anti-AI 模式、线索钩子（支持 AI 一键生成） |
| **3. Outline** | 卷结构、章节大纲、情感节拍、视角引导，全部确认后才能推进 |
| **4. Prompt** | 段落拆分、视角转换、逐段提示词组装 |
| **5. Write** | SSE 流式生成 + 质量检查，支持续写/润色/扩写，实时暂停/取消 |
| **6. Archive** | 归档定稿，更新角色状态、线索和钩子 |

每个阶段切换都要通过验证门——缺少前置条件无法跳级。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.14, FastAPI, SQLAlchemy 2.0 (async), SQLite |
| 前端 | React 19 + Vite, TypeScript, daisyUI, Tailwind CSS |
| 桌面壳 | pywebview (Edge WebView2) |
| AI | Anthropic / OpenAI 兼容 API（动态 Key 切换） |
| 流式 | SSE (Server-Sent Events) |
| 打包 | PyInstaller |

## 快速开始（开发模式）

```bash
# 克隆
git clone https://github.com/modoojunko/awesome-novel-desktop.git
cd awesome-novel-desktop

# 启动后端（无需 License）
cd client/backend && mkdir -p data
DEV_MODE=1 DATA_ROOT=./data uvicorn main:app --reload --host 127.0.0.1 --port 8000

# 新开终端，启动前端（需要后端先跑起来）
cd client/frontend && npm install && npm run dev
```

浏览器打开 `http://localhost:5173` 即可使用。

## 打包桌面应用

```bash
cd client/packaging/build
# 参考 build.spec 配置 PyInstaller
pyinstaller build.spec
```

打包后，数据目录就在 `AwesomeNovel.exe` 同级的 `data/` 下，整个文件夹可随意移动。

## 项目结构

```
awesome-novel-desktop/
├── client/                    # C端 — 用户本地桌面应用（本仓产品代码）
│   ├── backend/              FastAPI 后端：六阶段工作流 / AI 生成 / 本地文件存储
│   ├── frontend/             React 19 SPA (Vite + daisyUI)
│   └── packaging/            PyInstaller · Nuitka · Inno Setup 打包链
├── brand/                    品牌单源（brand.json：名称 / 主体 / 图标）
├── openspec/                 规格（specs/）与在途变更（changes/）
├── docs/                     文档（ux 标准 / 法律 / 设计资产 …）
├── scripts/                  仓库级脚本
├── .github/workflows/        CI：前后端测试 / 打包发版 / 演练
├── docker-compose*.yml       本地多服务栈（C端 + S端 sibling 私有仓）
└── CLAUDE.md                 项目指南
```

## 存储后端

C端默认使用本地文件存储，所有数据在 `data/` 目录下：

```
{install_dir}/data/{project_slug}/
├── story.yaml
├── author-intent.md
├── settings/
│   ├── world-setting.yaml
│   ├── writing-style.yaml
│   └── character-setting/
├── chapters/
├── volumes/
├── prompts/
└── archives/
```

也可通过 `STORAGE_BACKEND=database` 切换到数据库存储（将内容写入 `novel_files` 表）。

## 许可证（License）

本软件以 **GNU Affero General Public License v3.0（AGPL-3.0-only）** 开源发布，版权所有 © 2026 **星纬（海口）投资有限公司**。完整许可全文见仓库根 [LICENSE](LICENSE)；随分发附带的第三方开源组件按其自身许可提供，归属与声明见 [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt)。

- 你可以自由使用、修改、分发本软件；分发本软件或其衍生作品时，须同样以 AGPL-3.0 授权并提供完整对应源码。
- 若将本软件（含修改版）作为网络服务提供给用户，须按 AGPL 第 13 条向这些用户提供对应源码。
- 源码仓库：<https://github.com/modoojunko/awesome-novel-desktop>。
- 账号、在线服务与增值功能（套餐、激活码等）不属于本许可的授予范围，适用《用户服务协议》《付费须知》等文件，见官网 <https://www.awesomenovel.com>。
- 本仓库开源范围为桌面客户端（C端）；S端 在线服务为独立的私有专有组件，不在本许可范围内。

## 联系方式

商务咨询：**support@xingweitouzi.cn**
