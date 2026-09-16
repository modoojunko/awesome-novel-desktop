# AI Novel · 爱小说

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
- **S端** — License 授权与设备管理服务（FastAPI 2.0 重构版），部署在腾讯云 CloudBase
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
git clone https://github.com/modoojunko/ai-novel.git
cd ai-novel

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

打包后，数据目录就在 `AI Novel.exe` 同级的 `data/` 下，整个文件夹可随意移动。

## 项目结构

```
ai-novel/
├── client/                    # C端 — 用户本地桌面应用
│   ├── backend/              FastAPI 后端
│   │   ├── main.py           入口 + 路由注册
│   │   ├── config.py         配置 (DATA_ROOT, JWT_SECRET, SERVER_API_BASE)
│   │   ├── db.py             SQLAlchemy + SQLite
│   │   ├── ai_client.py      AI 客户端（动态 API Key）
│   │   ├── api_configs/      API Key 多配置管理
│   │   ├── models/           ORM: User, Project, TokenLog, NovelFile
│   │   ├── auth_local/       License 验证 + JWT
│   │   ├── projects/         项目 CRUD
│   │   ├── settings/         设定管理 + AI 生成
│   │   ├── chapters/         卷章 CRUD + 版本管理
│   │   ├── workflow/         阶段机 + 验证门
│   │   ├── prompt/           提示词组装
│   │   ├── write/            SSE 流式写作 + 辅助写作
│   │   ├── archive/          归档
│   │   ├── filesystem/       双后端存储抽象
│   │   └── story/            剧情推演引擎
│   ├── frontend/             React 19 SPA (Vite + daisyUI)
│   └── packaging/            PyInstaller + pywebview 打包
├── server/                    # S端 — License 授权与设备管理服务
│   ├── app/                   新系统核心代码（分层架构）
│   │   ├── config.py          配置管理
│   │   ├── main.py            FastAPI 应用入口
│   │   ├── models/            SQLAlchemy ORM（40 表）
│   │   ├── domain/            领域层（纯 Python 业务规则）
│   │   ├── infrastructure/    仓储 + 安全工具
│   │   ├── application/       编排用例（11 个）
│   │   └── interfaces/        API 接口层（17 端点）
│   ├── frontend/              (Phase 3) 管理门户 Vue SPA
│   ├── alembic/               数据库迁移
│   ├── tests/                 契约测试 + 单元测试
│   └── server/README.md       S端 详细文档
├── docs/                     文档
├── reference/                项目模板 (YAML/MD templates)
└── CLAUDE.md                 Claude Code 项目指南
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

## 许可证

GNU GPLv3。详见 [LICENSE](LICENSE)。

## 联系方式

商务咨询：**support@xingweitouzi.cn**
