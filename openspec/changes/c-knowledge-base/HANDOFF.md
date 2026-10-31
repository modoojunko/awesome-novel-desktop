# 写作知识库 · 实施交接文档（10-31）

## 项目上下文

AI 小说写作桌面端（C端，中国网文作家）。本变更新增账号级「写作知识库」：让作家沉淀拆书拆出的好写法和自己踩的经验，写新书时复用。

**用户拍板**：
- 先建库（存/看/管/进书/备份），动态拼装提示词建完再看
- UI 去掉「派生」流程和用词
- 主题逐字对齐 `client/frontend/src/design/base.css`
- 每个题材各有一套子库（文风/文笔/世界/角色/手法）
- 全局图推迟到 ⑦ AI 整理同批
- AI 维护全量（关系/合并/纠偏/子概念/质量）在第二阶段
- 系统词汇全换作家日常用语

## 设计文档（权威，不要重写）

| 文档 | 路径 |
|---|---|
| 整体方案 | `docs/design-c/drafts/ai-novel-c端-写作知识库-整体方案.md` |
| 选型 | `docs/design-c/drafts/ai-novel-c端-知识星图-选型.md` |
| 数据结构 | `docs/design-c/drafts/ai-novel-c端-写作知识库-数据结构.md` |
| 原型 | `docs/design-c/drafts/ai-novel-c端-写作知识库-原型.html`（v29，自检 60 项全绿） |
| OpenDesign 立项 | `openspec/changes/c-knowledge-base/`（validate 绿） |
| 实施计划 | `openspec/changes/c-knowledge-base/roadmap.md` |

## 当前实施状态

### 已完成（代码在 `client/backend/kb/`）

| 文件 | 行数 | 内容 |
|---|---|---|
| `kb/models.py` | ~290 | 11 张表（账号 8 + 书内 3），partial unique index，全列 nullable/server_default |
| `kb/concepts.py` | ~107 | 六概念封闭注册表 + 21 题材目录 + 场面/情绪封闭词表与别名表 + infer_concept |
| `kb/payloads.py` | ~121 | 六概念 Pydantic 模型（extra=forbid、槽位一致性、场景槽位闸） |
| `kb/gates.py` | ~123 | 入库闸门（长度/红线/原文/when 白名单） |
| `kb/infer.py` | ~44 | 概念推断（关键词匹配，不跑模型） |
| `kb/__init__.py` | 6 | 包声明 |

### 未完成（需要继续做）

| 文件 | 内容 |
|---|---|
| `kb/service.py` | 核心服务：入库（闸门+payload校验+标签物化+默认库生成）、查询（列表/详情/搜索）、默认库管理 |
| `kb/router.py` | API 端点（FastAPI router，挂 /api/kb 前缀） |
| `models/__init__.py` | 已注册 kb 模型（已改） |
| `main.py` 或 `write/router.py` | 挂 kb router |
| 前端 | 知识库页（React，用 app token）、条目抽屉、手录表单 |
| 测试 | 单测（闸门/推断/默认库/标签重建） |

### tasks.md（批1 后端任务清单）

- [x] 1.1 models/kb.py
- [x] 1.2 kb/concepts.py
- [x] 1.3 kb/payloads.py
- [x] 1.3b kb/infer.py
- [x] 1.4 入库闸门
- [ ] 1.5 标签物化（service 层做）
- [ ] 1.6 题材归一 normalize_theme（service 层做）
- [ ] 1.7 默认库自动生成（service 层做）
- [ ] 1.8 API 端点契约
- [ ] 1.9 kb_prefs 拍板 (user_id, entry_id)
- [ ] 1.10 import 断言
- [ ] 1.11-1.17 前端/测试/门禁

## 关键设计决策（不要改）

| # | 决策 |
|---|---|
| 1 | 单表 kb_entries + payload_json 按概念 Pydantic；标签物化选择器不走 JSON 扫描 |
| 2 | 概念是注册表不是表；无消费链不进注册表；情节只展示占位 |
| 3 | 场景条目由 when_json 空/非空决定；文风场景只许 tone/register/sample |
| 4 | 默认库 auto_all 首条目触发；partial unique index 兜并发 |
| 5 | 选择器信号只读章纲（角色直取；场面/情绪走别名归类，不跑模型） |
| 6 | 注入位：user 层收尾行前；system 逐章字节一致红线不变 |
| 7 | 备份 FORMAT_VERSION 8→9（当前值已是 8） |
| 8 | 全局图 npm force-graph → ⑦（P1） |
| 9 | 档位：拆书入库/AI 整理 PRO；手录/蒸馏/浏览免费 |
| 10 | kb/ SHALL NOT import write/、deconstruct/ |
| 11 | 注入实现：write/router.py 存储稿后收尾行前 |
| 12 | kb_prefs (user_id, entry_id) 账号级全局 |
| 13 | 幂等键 partial unique index WHERE src_ref <> '' |
| 14 | entry_tags 冗余 user_id 列使单表索引成立 |
| 15 | 拆子变更：本变更=批1，批2-7 各立子变更 |
| 16 | 概念推断：封闭词表确定性规则；推断不出默认"手法" |
| 17 | 情节只展示占位（消费链未建）；手录/推断/全局图拒收情节条目 |
| 18 | 概念变更→自动库归属重算 |

## 代码约定（必须遵守）

- Python 类型用 `Optional[X]` 不用 `X | None`（后端 < 3.10）
- 全列 nullable 或 server_default（迁移引擎不认 Python default=）
- partial unique index 用 `sqlite_where=text(...)`
- 模型注册进 `models/__init__.py`
- 主题色逐字用 `client/frontend/src/design/base.css` 的 token
- 概念/词表/别名**前后端一致性测试**必须配（照 theme parity 路数）
- kb/ 包 **SHALL NOT import write/、deconstruct/**

## OpenDesign 状态

- 项目 `Web Prototype`（id `f0f156f1`）
- knowledge-base.html v29 已发布（digest `2228ae8e…`）
- 原型 v29 自检 60 项全绿
- **注意**：v29 之后的本地修改（清晰度/全节点辐条/主题对齐等）未推送到 OpenDesign（守护进程停了），需要重新发布

## 评审结论（三轮全绿）

- 后端：partial unique index 先例正确、表数已统一、闸门先例对齐
- 前端：IA 零冲突、token 对齐属实、数据护栏扎实
- 提示词：system 零字节红线钉死、重试确定性正确
- 架构师：spec 裁剪干净、drafts 不污染归档、批1 主体对齐
- PM：方向对（"存什么 → 以后哪里用"的闭环）、需要 ①② 捆绑发布
