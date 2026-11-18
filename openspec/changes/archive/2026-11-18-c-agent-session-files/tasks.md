# c-agent-session-files Tasks

## 1. 文件后端

- [x] 1.1 session_store 平移：文件路径解析（DATA_ROOT/sessions/<novel>/）、文件名组装（日期__thread__id，: → -）、meta 行读写
- [x] 1.2 追加写（append_message 每事件一行）＋整段重写（tmp-then-replace：meta 变更/finalize 改行/compaction）
- [x] 1.3 解析（get_or_create：列目录读 meta 匹配 thread 取最新；无则建新文件）＋/new 语义（旧文件留档＋新文件）
- [x] 1.4 加载自愈（尾半行跳过＋streaming 悬行收尾 error）＋回看契约（load_messages 返回形状不变）
- [x] 1.5 router 调用点去 db 实参（约 15 处机械改）＋签名清理（session_store 函数去 AsyncSession 参数）

## 2. 迁移

- [x] 2.1 启动迁移钩子（db_lifecycle 后）：DB 两表 → JSONL 全量导出；幂等（目标存在跳过）；fail-soft 留日志
- [x] 2.2 DB 行保留归档（不删不改读路径）；迁移日志一条汇总（导出会话数/消息数）

## 3. 测试

- [x] 3.1 契约钉：文件名/目录/meta 行/append 顺序/整段重写 tmp-then-replace
- [x] 3.2 解析钉：同 thread 多文件取最新；/new 旧文件留档不混入回看；id 白名单防路径逃逸
- [x] 3.3 迁移钉：DB 播种 → 迁移 → 逐字段对拍 → 幂等重跑；半行＋streaming 悬行自愈钉
- [x] 3.4 route 回归：chat SSE 链路既有钉全绿（含 c-agent-nav 三钉）；全量 pytest＋ruff

## 4. 收尾

- [x] 4.1 重建安装＋真机走查：sessions 目录肉眼可读＋/new 出新文件＋老会话迁移内容一致
- [x] 4.2 归档（含 c-agent-nav 一起收）＋spec sync
