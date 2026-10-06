# C端 后端 — Awesome Novel 本地后端服务

FastAPI 应用，作为单用户桌面应用的本地后端，提供 AI 写作、项目管理、Token 计费等核心功能。

## 技术栈

| 项 | 选型 |
|----|------|
| 框架 | FastAPI (Python) |
| 数据库 | SQLite (SQLAlchemy) |
| 认证 | JWT |
| 客户端 | httpx (AI API 调用) |
| 测试 | pytest |

## 开发

```bash
cd client/backend

# 安装依赖
pip install -r requirements.txt

# 启动（必须先启动 S端 本地模拟器）
python local_server.py          # 终端 1: S端 模拟器 (端口 19000)
DATA_ROOT=./data uvicorn main:app --reload --port 8000  # 终端 2: C端 后端
```

### 库文件与升级（c-db-per-version）

库文件名 = **C端 版本派生**（`novel-v{版本}.db`）：每个版本首启新建自己的库，
旧库只读留存、靠「带回」把作品搬过来（不再对既有库执行任何 DDL）。开发时注意：

- **不设 `CLIENT_VERSION` 用哨兵名** `novel-dev.db`（PR/手动构建同此）；要按版本名跑就
  `CLIENT_VERSION=0.24 uvicorn main:app ...`。
- **改 schema 会被分流**：同名库指纹不符 → 可读时改名为 `novel-v{X}.db.mismatch-<stamp>`
  （仍可作候选带回）、不可读时 `.corrupt-<stamp>` 隔离。想保住本地开发数据，把
  `DATA_ROOT` 指到独立目录（e2e/docker 栈本来就这么做）。
- **新增列/表**：不需要登记任何补列清单（旧的 `ADDITIVE_COLUMNS` 机制已退役）——
  新库由 `create_all` 全量建出，老库经「带回」按列交集搬运。

## 测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行单个测试
python -m pytest tests/ -k "test_name"
```

## 目录结构

```
client/backend/
├── main.py              FastAPI 入口
├── config.py            配置
├── db.py                SQLAlchemy + SQLite
├── ai_client.py         AI API 客户端
├── models/              ORM 模型
├── auth_local/          License 验证模块
├── projects/            项目 CRUD
├── settings/            设定管理
├── chapters/            卷章 CRUD
├── workflow/            阶段门控机
├── prompt/              提示词组装
├── write/               SSE 流式写作
├── archive/             归档
├── filesystem/          本地文件存储
├── genres/              全局题材库（预置 seed + CRUD + 写作链路注入）
├── story/               剧情推演
├── api_configs/         API Key 多配置管理
├── billing/             Token 计费
└── tests/               测试
```

## 关键设计

- **六阶段工作流**：init → settings → outline → prompt → write → archive
- **全局题材库**：题材定义存 SQLite `genres` 表（24 预置只读 + 自定义增删改，全局共享），写作时注入分段/整章两条路径。与 `GENRE_CORPUS_NAMES`（`novels/router.py` 死代码）、`reference/genre-corpus/`、`story.yaml.genre`、`writing-style.yaml.genre_profile`（旧独立体系，未接入）不混用。
- **文件系统存储**：小说内容（卷章/设定/正文/版本快照）存本地文件系统 YAML/MD，SQLite 存元数据（用户/项目/计费）
- **SSE 流式传输**：写作阶段每段一个 SSE 连接，支持并行流
- **Token 计费**：每次 AI 调用记录到 token_log，按模型单价扣除
