# backend/logging_setup.py
"""C端 后端日志单点初始化（backend-logging）。

设计要点（openspec/changes/c-backend-daily-logging/design.md）：
- 单一日志目录：打包态由壳层注入 AINOVEL_LOG_DIR（运行目录/logs），开发态兜底
  DATA_ROOT/logs；AINOVEL_LOG_OFF=1 整体关闭（conftest 全局设置，测试零副作用）。
- 按天轮转：TimedRotatingFileHandler（midnight、backupCount=5、UTF-8、delay=True），
  现文件 app.log、轮转产物 app.log.YYYY-MM-DD。
- llm.log 专项档（c-llm-call-log）：同参第二个 handler，只挂三类大模型出网调用的
  具名 logger（ai_client / llm_probe / zhuque.client）；这些 logger 保持
  propagate=True——行双写 app.log（求诊主档不缺行）＋ llm.log（专项档）。
- Handler 拓扑（D1）：挂 root＋`uvicorn` 两个挂点，并显式 `uvicorn.propagate=False`
  ——log_config=None 跳过 dictConfig 后，uvicorn 默认配置里的 propagate 护栏不再
  生效，不钉这条同一个 record 会在两个挂点各写一行（dev 看不出、打包必现双行）。
- 级别陷阱（D2）：log_config=None 时 `uvicorn` logger 本体 NOTSET 沿 root（默认
  WARNING）判定，启动期 INFO 全被吞——root 与 uvicorn 都显式 INFO。uvicorn.access
  压到 WARNING（逐请求行由请求中间件承载，避免同请求双行）。
- 挂载时机（D3）：main.py 模块顶部调用，早于业务 import——router 导入期崩溃的
  traceback 由 uvicorn error logger 打出时文件 handler 已在位。
- 幂等（D9）：handler 打 _ainovel_daily 标记，重入扫描到即返回（防 pytest 反复
  导入 main、防 reload 双挂）。
"""

import logging
import os
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_MARK = "_ainovel_daily"
_LLM_MARK = "_ainovel_llm"

# 第三方库静音名单（D2）：root 提到 INFO 后它们会刷屏/进求诊文件——httpx 每个
# 上游请求一行且含完整 URL（隐私面）；AI 调用观测由 ai_client 的留痕行承载。
_NOISY_LOGGERS = ("httpx", "httpcore", "openai", "sqlalchemy")

# llm.log 专项档挂载点（c-llm-call-log）：大模型出网调用的三类具名 logger
# （生成调用 / 连接探针 / 朱雀检测）。不设 propagate=False——app.log 双写保留。
_LLM_LOGGERS = ("ai_client", "llm_probe", "zhuque.client")


class FoldRepeatFilter(logging.Filter):
    """同型消息限速（D4 体积护栏）：窗口内同 (logger, level, 消息模板) 只放行首条。

    被折叠的条数计在窗口关闭后的下一条放行消息上（追加「[+N 重复已折叠]」），
    异常风暴（每请求 traceback）下当日体积有界，替代旧管道 2MB×3 的有界语义。
    handler 锁内调用（emit 序列化），状态无需另加锁。"""

    def __init__(self, window_seconds: float = 10.0):
        super().__init__()
        self._window = window_seconds
        self._state: dict[tuple, tuple[float, int]] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        now = time.monotonic()
        template = record.msg if isinstance(record.msg, str) else str(record.msg)
        # args 必须进 key：请求行/AI 留痕行共用固定模板、参数各异——不含 args 会把
        # 连续正常操作折叠成一行（违反 spec「一行一条」）；风暴场景（同异常文本、
        # args=() 或相同参数）折叠语义不变。
        key = (record.name, record.levelno, template, record.args)
        state = self._state.get(key)
        if state is not None and (now - state[0]) < self._window:
            self._state[key] = (state[0], state[1] + 1)
            return False
        if state is not None and state[1] and isinstance(record.msg, str):
            record.msg = f"{record.msg} [+{state[1]} 重复已折叠]"
        self._state[key] = (now, 0)
        return True


def setup_logging(log_dir: str | os.PathLike | None = None) -> Path | None:
    """挂按天文件日志；返回日志目录（关闭态返回 None）。

    幂等：root/uvicorn 任一已有标记 handler 即视为已初始化，直接返回其目录。
    """
    if os.environ.get("AINOVEL_LOG_OFF"):
        return None
    root = logging.getLogger()
    uvicorn_logger = logging.getLogger("uvicorn")
    for handler in (*root.handlers, *uvicorn_logger.handlers):
        if getattr(handler, _MARK, False):
            return getattr(handler, "_ainovel_dir", None)

    if log_dir is None:
        log_dir = os.environ.get("AINOVEL_LOG_DIR") or os.path.join(
            os.environ.get("DATA_ROOT", "./data"), "logs"
        )
    log_dir = Path(log_dir)
    # logging 不创建父目录；漏建＝全新安装首条 emit 失败被 handleError 静默吞掉
    # （整份日志静默消失，恰是本 change 要消灭的形态）。
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = TimedRotatingFileHandler(
        log_dir / "app.log",
        when="midnight",
        backupCount=5,
        encoding="utf-8",
        delay=True,
    )
    handler._ainovel_daily = True
    handler._ainovel_dir = log_dir
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(FoldRepeatFilter())

    root.addHandler(handler)
    root.setLevel(logging.INFO)

    uvicorn_logger.addHandler(handler)
    uvicorn_logger.setLevel(logging.INFO)
    uvicorn_logger.propagate = False  # 双挂点防双写（D1），dev/packaged 两态一致

    # 逐请求 access 行停用：请求日志由 request_logging 中间件承载（含耗时）。
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # llm.log 专项档（c-llm-call-log）：同参第二 handler，独立折叠实例（filter 状态
    # 不共享——同一条 record 在两个 handler 各自独立判定，互不干扰）。
    llm_handler = TimedRotatingFileHandler(
        log_dir / "llm.log",
        when="midnight",
        backupCount=5,
        encoding="utf-8",
        delay=True,
    )
    llm_handler._ainovel_llm = True
    llm_handler._ainovel_dir = log_dir
    llm_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    llm_handler.addFilter(FoldRepeatFilter())
    for name in _LLM_LOGGERS:
        logging.getLogger(name).addHandler(llm_handler)

    if sys.stdout is not None:  # 打包 GUI 态 stdout 可能是 None（壳层已垫 devnull 则非 None）
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter("%(levelname)s:%(name)s %(message)s"))
        root.addHandler(console)

    return log_dir
