# assistant-session-files Specification

## ADDED Requirements

### Requirement: 会话文件目录契约

助手会话 SHALL 以 JSONL 文件持久化于 `DATA_ROOT/sessions/<novel_id>/`；文件名 SHALL 为 `<创建日期YYYYMMDD>__<thread_key>__<session_id>.jsonl`（id+日期口径，thread_key 中 ":" 编码为 "-"）。文件首行 SHALL 为 meta 行（含 thread_key/novel_id/user_id/grants/page_cursor/compaction/created_at/updated_at），其后每行 SHALL 为一条消息或事件（与现 assistant_messages 行字段同形）。写入 SHALL 为 append-only；meta 字段变更（touch/compaction/grants）SHALL 走整段重写（tmp-then-replace）。

#### Scenario: 文件落盘可见
- **WHEN** 作家与助手完成一轮对话
- **THEN** `sessions/<novel_id>/` 下存在 `<日期>__<thread>__<id>.jsonl`，文本编辑器可直接读出 meta 行与逐条消息

#### Scenario: grants 变更整段重写
- **WHEN** 作家切换授权档位
- **THEN** 该会话文件的 meta 行更新，消息行原样保留

### Requirement: 线程解析与会话新建

thread→session 解析 SHALL 扫描书目目录、读 meta 行匹配 thread_key 取最新文件。同 thread 新开会话（/new）SHALL 生成新文件（新 session id＋当日日期），旧文件 SHALL 留档不删。会话 id SHALL 延用既有白名单校验（防御路径逃逸）。

#### Scenario: /new 开新文件
- **WHEN** 作家发 /new
- **THEN** 同 thread 生成新会话文件，旧文件留在目录里可查

#### Scenario: 回看绑定最新
- **WHEN** 作家切回该页签
- **THEN** GET /session 返回最新会话文件的内容（历史文件不混入）

### Requirement: 存量迁移

启动迁移 SHALL 把 DB 两表（assistant_sessions/assistant_messages）的存量会话按同契约写成 JSONL；迁移 SHALL 幂等（目标文件存在即跳过）；DB 行 SHALL 保留作归档（代码不再读写）。迁移失败 SHALL NOT 阻塞启动（fail-soft 留日志，下次启动重试）。

#### Scenario: 老会话迁文件
- **WHEN** 带存量 DB 会话的旧库启动新版
- **THEN** `sessions/<novel_id>/` 出现等价 JSONL，作家切页签回看内容与迁移前一致

### Requirement: 加载自愈

加载会话 SHALL 容忍崩溃残迹：文件尾部半行 SHALL 跳过；悬挂的 streaming 状态消息 SHALL 收尾为 error（崩前已产出的卡与轨迹保留）——现 DB 路径自愈语义平移。

#### Scenario: 崩溃后半截能读
- **WHEN** 进程在写入中途崩溃后重启
- **THEN** 会话照常加载，半行被忽略，悬挂行收尾 error，不炸不挂
