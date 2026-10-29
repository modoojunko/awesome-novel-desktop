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
├── filesystem/          设定存储门面：KV 键位路由（paths.py）＋ DatabaseFileBackend（无文件读写）
├── genres/              全局题材库（预置 seed + CRUD + 写作链路注入）
├── story/               剧情推演
├── api_configs/         API Key 多配置管理
├── billing/             Token 计费
└── tests/               测试
```

## 关键设计

- **六阶段工作流**：init → settings → outline → prompt → write → archive
- **全局题材库**：题材定义存 SQLite `genres` 表（24 预置只读 + 自定义增删改，全局共享），写作时注入分段/整章两条路径。与 `GENRE_CORPUS_NAMES`（`novels/router.py` 死代码）、`project_settings` KV `story` 键的 `genre` 字段（每书题材目录标签）、KV `style` 键的 `genre_profile`（旧独立体系：建书写入、无消费方）不混用。
- **存储总口径**（ADR-001/002/003）：创作内容**全部在 SQLite**（每版本一库 `novel-v{版本}.db`）。
  - 设定走 `project_settings` KV（`story`＝简介/题材标签/主线，`world`、`style`、`character:*`、`threads`、
    `style-quant`、`book-prefs` 等键；键位路由见 `filesystem/paths.py`）。路径形 `.yaml` 字符串是文件时代
    遗留的**路由键名、永不落盘**——判定「某设定存在哪」看 paths.py 映射，勿信调用点字面量。
  - 卷章/正文/版本快照为真表（`volumes` / `chapters` / `chapter_contents` / `chapter_versions`）；
    题材五格（`novel_genre` 系）、伏笔（`novel_hooks`）、卷纲（`volumes`）亦为真表。
  - 盘上只余：数据库文件与日志、每本书的 `novel-samples/`（文风蒸馏样本原件），以及用户主动产物
    （`manuscript/` 成稿导出、`backup/` 备份包——写用户所选目录，禁止落 DATA_ROOT）。
- **SSE 流式传输**：写作阶段每段一个 SSE 连接，支持并行流
- **Token 计费**：每次 AI 调用记录到 token_log，按模型单价扣除
