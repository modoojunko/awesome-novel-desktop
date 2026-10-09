# c-upgrade-log — design

## 专项档形态＝llm.log 同构复制

`upgrade.log` 不引入新机制：`logging_setup` 第三个 `TimedRotatingFileHandler`，
与 app.log/llm.log 同参（midnight、backupCount=5、UTF-8、delay=True）、独立
`FoldRepeatFilter` 实例（filter 状态不跨 handler 共享——同一条 record 在各 handler
独立判定）、挂具名 logger `migration` 且不动 propagate（行双写 app.log，求诊主档
不缺行——沿用 c-llm-call-log 判例）。幂等与 `AINOVEL_LOG_OFF` 语义随单点初始化
天然成立；测试夹具（`daily_file_log`）须同批快照/还原 migration logger，否则
handler 指向已删 tmp 目录渗漏进后续用例（llm 专项档同款判例）。

## logger 命名＝`migration`

链上三个模块（engine/db_lifecycle/router）统一从 `uvicorn.error` 切到
`migration`。`uvicorn.error` 是历史桥接名（c-backend-daily-logging 承接期产物），
语义上属于「启动期 uvicorn 侧」；迁移链有自己的一等身份。propagate=True 落 root
的路径与 `uvicorn.error` 等价（uvicorn 挂点也是同一 handler），app.log 面零变化。

## 留痕粒度：终局整份 report JSON 单行

六步逐事件行（start/precheck/plan/逐表/verify）回答「走到哪一步」；终局
`event=migration_report <整份 report JSON>` 单行回答「结果到底是什么」——report
dict 本就是 v:1 版本化 JSON 可序列化结构，原样 `json.dumps(ensure_ascii=False)`
落行，与 `app_meta.migration.last` 存的 payload 同源。逐表行带 `rows_source/
rows_inserted`：不同参数不同 key，FoldRepeatFilter 不折叠（判例
test_distinct_args_never_folded）。

## 线程异常：router 侧记日志后重抛，不改 job_runner

`run_thread` 把异常吞进 status 零落日志是「无法定位」的直接形态；但 job_runner
是备份/导出/下载共用的通用骨架——在那里加日志会让 migration 链的堆栈在 app.log
出现两份（router 侧一份＋骨架一份）。收口：router 线程体 `_body` try/except
经 `migration` logger 记 ERROR 堆栈后原样重抛，job_runner 兜底 state=error 语义
不变，其他 kind 零影响。其他 kind 的静默吞异常是同类问题但非本 change 范围。

## 隐私红线

report dict 与事件行只含表名、行数、原因码、文件名、版本标签——无 API Key
（密钥转接只落死钥**计数** `dead_keys`）、无用户正文。与 llm.log 红线同口径。
