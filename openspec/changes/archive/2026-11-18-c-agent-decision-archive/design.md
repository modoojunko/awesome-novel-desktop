# c-agent-decision-archive Design

## Context

书级决策（remember_decision）注入系统提示词，预算 1200 字、超限从最旧**截断丢弃**
（memory.py render_memory_section）——决定条数一多，半年前的先被挤掉；会话文件化
后原始对话永在磁盘但没有注入路径。coding agent 同构答案＝CLAUDE.md 三件套：
常驻摘要＋全量在盘＋agent 按需读文件。

既有面（实勘）：
- memory.py：add_decision/list_decisions（DB）、render_memory_section（纯函数截断）、
  delete_book_memory（删书级联）、load_book_memory_section（注入入口）
- tools.py：_memory_recall/_memory_decide（各自 async_session 短会话）；MEMORY_TOOLS
- 书删除级联：novels/router.py delete → delete_book_memory
- 会话文件化先例：c-agent-session-files 的 append/tmp-replace/迁移幂等套路全套可抄

## Goals / Non-Goals

- Goals：决策原文永不截断；注入段分层（全文→索引→尾注）；agent 可自主召回；
  迁移无损；书级写作规矩（800 字层）不动
- Non-Goals：向量检索/语义搜索（子串过滤够用，决策量级 ≤数百条）；写作规矩文件化
  （量小，DB 层够用，挂账）；决策编辑/撤销 UI（append-only 留痕是语义本身）

## Decisions

### D1：档案布局

`DATA_ROOT/decisions/<novel_id>.jsonl`，每行：
`{"id", "decision", "reason", "created_at"}`——append-only；读侧容忍坏行。
路径校验同 session_store（novel_id 白名单）。

### D2：写读路径切文件（memory.py 函数签名去 db）

- `add_decision(novel_id, decision, reason)`：追加一行
- `list_decisions(novel_id)`：读档案，created_at 倒序返回（注入口径不变）
- `delete_book_memory(novel_id)`：DB 记忆行照删＋档案文件移除（零孤儿）
- tools.py 三个工具的 async_session 短会话包裹随之退役（_memory_decide/
  _memory_recall 不再开 DB 会话；_memory_remember/_memory_forget 是写作规矩层，
  仍走 DB 不动）

### D3：分层注入（render_memory_section 演进；纯函数可单测）

```
预算内最近决策 → 全文行（现行为）
超预算更早决策 → 索引行「- [YYYY-MM-DD] 决定首句」
                （首句＝按句号/换行截 40 字；索引自身预算 INDEX_BUDGET=600 字）
仍超限 → 尾注「（另有 N 条更早的决定在档——作家提起时用 recall_decisions 查）」
```
- 段头「项目决定（最近优先）」改「项目决定（旧的也在档，可随时查）」——句子
  念出声像人话（红线）
- 书级写作规矩段零变化

### D4：recall_decisions 工具

read 类免授权、risk_level=low（可并行）；参数 `query`（子串，空＝最近 N 条）与
`limit`（默认 20）；过滤 decision+reason 不区分大小写；输出按时间倒序、单条
裁 160 字、总条数标注；空档案如实返回。进 scopes._SHARED_TOOLS（全页签可见）。

### D5：迁移与级联

- `migrate_book_decisions()`（memory.py）：DB book_decisions → 档案追加，幂等
  （同 id 已在档跳过）；main lifespan fail-soft 挂钩（session 迁移同位）
- delete_book_memory：DB 行照删＋档案文件 unlink
- novels/router.py 删书级联调用点不变（函数签名去 db）

## Risks / Trade-offs

- **索引预算**：600 字≈15 条索引；再老的靠尾注计数＋召回工具——无限注入会撑爆
  提示词，计数告知是诚实且有出路的折中
- **子串召回漏召回**：作家换词提旧决定（「不能上天」vs「不能飞」）——检索层弱是
  已知取舍；后续可并入知识库 kb_search（挂账）
- **双源窗口**：迁移后 DB 行归档不读，新写入只进文件——无双写、无一致性窗口

## Migration Plan

启动迁移（幂等＋fail-soft）；DB 行归档；回滚＝revert（档案文件是新产物可删）。

## Open Questions

<!-- 无：方案四层结构 boss 拍板立项（2026-11-18）；成本约 2 天。 -->
