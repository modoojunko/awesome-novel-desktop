# c-agent-session-files Design

## Context

现载体＝SQLite 两表（assistant_sessions/assistant_messages），机制移植自 OpenWorker
conversations.py（原本就是「每会话 JSONL append-only」）——批A 改表时全部机制语义
（id 白名单/append-only/自愈/整段重写 tmp-then-replace）留在 docstring，本次平移
回文件形态有蓝本。

消费面（调用点盘点）：router.py 约 15 处（chat 主链/_stream_command/_compact/no_key/
approve/adopt/reset/stop/session 回看）＋profile 摘要任务。调用都经 session_store
函数，签名带 db/drv_db 参数。

## Goals / Non-Goals

- Goals：文件契约可肉眼直读（boss 核心诉求）；session_store 对外签名保持（调用面
  零变化）；存量无损迁移；/new 对齐 coding agent 语义（新文件旧留档）
- Non-Goals：历史会话浏览 UI（文件留档即可，UI 另立项）；多进程文件锁（单进程
  asyncio）；会话加密

## Decisions

### D1：布局与文件名

```
DATA_ROOT/sessions/<novel_id>/<YYYYMMDD>__<thread>__<session_id>.jsonl
```
- boss 口径「按 id+日期」；日期＝会话创建日（目录一眼看日期，文件名双条件可搜）
- thread_key 中 `:` 编码为 `-`（`ch:og` → `ch-og`；macOS Finder 对冒号不友好）
- 首行 meta：`{"type":"meta", thread_key, novel_id, user_id, grants, page_cursor,
  compaction, created_at, updated_at}`；消息行 `{"type":"msg", id, seq, role, page,
  content, payload, card_kind, status, run_id, created_at}`（字段同 DB 行）
- DATA_ROOT 复用 config.DATA_ROOT（打包端＝Application Support/data，与 novel-dev.db
  同级——boss 口径「安装目录下」）

### D2：session_store 同签名平移（调用面零变化）

`get_or_create_session / load_messages / append_message / update_message_status /
touch_session / load_compaction_state / save_compaction_state / reset_session` 保持
函数名与返回形状；**db 参数退役**（函数不再接 AsyncSession）。router 调用点同步去
db 实参（机械改动）。`get_or_create_session` 语义＝「解析最新文件，无则建」：
列目录读各文件 meta 行（读前 2KB 即可），匹配 thread_key 取 updated_at 最新。

### D3：写路径与原子性

- 追加：每事件 `open("a")` 写一行 flush（单进程 asyncio 串行，无锁；run 内事件
  天然顺序——_drive 单任务消费）
- 整段重写（meta 变更/finalize 改行/compact）：tmp 文件写全量 → os.replace（
  OpenWorker conversations.py:332 同款，文件系统原子替换替代 DB 事务）
- finalize（streaming→done/error）：读-改-写最后一行匹配 id

### D4：迁移（一次性＋幂等＋fail-soft）

- 启动钩子（db_lifecycle create_all 之后）：列 DB 会话 → 目标文件不存在则写全量
  JSONL；存在即跳过（幂等）
- DB 行永不删（归档备份）；代码不再读——「迁移」实为导出，回滚＝git revert 零风险
- 失败：try/except 留日志不阻塞启动，下次启动重试

### D5：/new 语义

reset_session 改为「解析旧文件留档＋生成新 session 文件」（新 id 新日期）。前端
契约不变（clear 事件清屏照旧）；旧对话文件在 sessions 目录永存。

### D6：测试钉

- 契约钉：文件名/目录/meta 行/append 顺序/整段重写（tmp-then-replace）
- 解析钉：同 thread 多文件取最新；/new 后旧文件留存且不混入回看
- 迁移钉：DB 播种 → 启动迁移 → 文件等价（逐字段对拍）→ 幂等重跑
- 自愈钉：半行跳过＋streaming 收尾 error
- route 钉：既有 chat SSE 链路全绿即回归证（调用面签名不变，测试改 db 实参）

## Risks / Trade-offs

- **目录扫描解析**：每书线程 ≤10、meta 头 2KB，代价毫秒级；未来会话多可加内存缓存
  （挂账不预做）
- **崩溃半行**：JSONL 读侧跳过容忍（业界惯例）；flush 每行降低窗口
- **DB 两表遗留**：保留归档不删——回滚零风险；版本清理另议

## Migration Plan

启动迁移（D4）＋旧版回滚＝git revert（DB 数据未动，文件为新产物可删）。

## Open Questions

<!-- 无：目录位置（DATA_ROOT/sessions）、文件名（日期__thread__id）、迁移口径
（DB 行留档）、/new 语义（新文件留档）均按 boss 口径＋coding agent 惯例定。 -->
