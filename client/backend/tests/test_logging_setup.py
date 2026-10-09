"""backend-logging：日志单点初始化判据（openspec/changes/c-backend-daily-logging 2.1）。

①幂等 ②轮转参数与保留清理 ③uvicorn 桥接单行（双挂点不双写） ④业务 __name__ 落盘
⑤AINOVEL_LOG_OFF 关闭 ⑥uvicorn.access 压制 ⑦体积护栏限速 ⑧目录级联创建。
"""

import logging
import logging.handlers
import time

import logging_setup
from logging_setup import _LLM_LOGGERS, FoldRepeatFilter, setup_logging


def _marker_handlers() -> list:
    """root＋uvicorn 扫描去重（同一 handler 对象挂两个挂点是 D1 的设计形态）。"""
    seen: dict[int, logging.Handler] = {}
    for lg in (logging.getLogger(), logging.getLogger("uvicorn")):
        for h in lg.handlers:
            if getattr(h, "_ainovel_daily", False):
                seen[id(h)] = h
    return list(seen.values())


def _daily_handler() -> logging.Handler:
    assert _marker_handlers(), "daily handler 未挂载"
    return _marker_handlers()[0]


def _log_text(log_dir) -> str:
    return (log_dir / "app.log").read_text(encoding="utf-8")


def _ensure_file_exists(log_dir) -> None:
    """delay=True 下文件首条 emit 才创建——断言「X 不在文件里」前先落一条真行。"""
    logging.getLogger("biz.warmup").info("warmup-line")
    assert "warmup-line" in _log_text(log_dir)


# ① 幂等：重复初始化不重复挂 handler、单条消息单行


def test_setup_idempotent_single_handler_and_line(daily_file_log):
    log_dir = daily_file_log
    again = setup_logging()
    assert again == log_dir
    assert len(_marker_handlers()) == 1, "重复初始化不得重复挂文件 handler"

    logging.getLogger("biz.a").info("idem-one")
    logging.getLogger("biz.a").info("idem-two")
    text = _log_text(log_dir)
    assert text.count("idem-one") == 1, "同一条消息在文件中只出现一次"
    assert text.count("idem-two") == 1


# ② 轮转参数钉死 + 超 5 天自动清理


def test_rotation_params_and_backup_cleanup(daily_file_log):
    handler = _daily_handler()
    assert isinstance(handler, logging.handlers.TimedRotatingFileHandler)
    assert handler.when == "MIDNIGHT", "必须按本地自然日轮转"
    assert handler.backupCount == 5, "保留 5 天（含当日共 6 份以内）"

    log_dir = daily_file_log
    # 真实时序：轮转发生时 app.log 已写了一天（delay=True 下源文件必须存在，
    # 否则 rename 失败被 handleError 吞掉、清理不执行——与生产语义一致）。
    # 预置历史文件从「昨天」往前 6 天——今天的轮转产物（rolloverAt-interval 的日期）
    # 若预先存在，doRollover 判「Already rolled over」直接跳过（标准库语义）。
    logging.getLogger("biz.rotate").info("pre-rollover")
    from datetime import date
    from datetime import timedelta as _td

    today = date.today()
    # 预置「前天」往前 6 份历史：手动拨 rolloverAt=now 时标准库取 dfn=昨天日期
    # （rolloverAt-interval），同名预置会让 doRollover 判 Already-rolled-over 跳过——
    # 真实世界「昨天的轮转产物」在跨天时刻尚不存在，留空昨天即同构。
    for days_ago in range(2, 8):
        dd = today - _td(days=days_ago)
        (log_dir / f"app.log.{dd.isoformat()}").write_text("x", encoding="utf-8")
    oldest = f"app.log.{(today - _td(days=7)).isoformat()}"
    handler.rolloverAt = int(time.time())  # 强制下一次 emit 触发 rollover
    logging.getLogger("biz.rotate").info("trigger-rollover")

    assert not (log_dir / oldest).exists(), "最老的一份必须被清理"
    dated = list(log_dir.glob("app.log.20*"))
    assert len(dated) <= 6, f"目录内日志文件不超过保留上限（实际 {len(dated)}）"


# ③ uvicorn 桥接：uvicorn.error 的行落文件且只一行（无 dictConfig 环境——钉住
#    log_config=None 路径下 propagate 护栏必须由 setup_logging 显式补上）


def test_uvicorn_error_bridged_exactly_once(daily_file_log):
    logging.getLogger("uvicorn").propagate = True  # 模拟 log_config=None 的裸环境
    logging.getLogger("uvicorn.error").info("bridge-XYZ")
    text = _log_text(daily_file_log)
    assert "bridge-XYZ" in text
    assert text.count("bridge-XYZ") == 1, "uvicorn→root 双挂点不得双写（D1 propagate=False）"


# ④ 业务标准 logger 落盘（打包态不再丢 __name__ 行）


def test_business_logger_lands_in_file(daily_file_log):
    logging.getLogger("somebiz.module").info("bizline-XYZ")
    assert "bizline-XYZ" in _log_text(daily_file_log)


# ⑤ AINOVEL_LOG_OFF=1 整体关闭


def test_log_off_switch(monkeypatch):
    monkeypatch.setenv("AINOVEL_LOG_OFF", "1")
    before = list(logging.getLogger().handlers)
    assert setup_logging() is None
    assert list(logging.getLogger().handlers) == before, "关闭态不得动 root"


# ⑥ uvicorn.access 逐请求行压制


def test_uvicorn_access_suppressed(daily_file_log):
    _ensure_file_exists(daily_file_log)
    logging.getLogger("uvicorn.access").info("ACCESS-NOISE-XYZ")
    assert "ACCESS-NOISE-XYZ" not in _log_text(daily_file_log)


# ⑦ 体积护栏：同型消息风暴限速去重


def test_storm_folded_to_bounded_lines(daily_file_log):
    storm = logging.getLogger("storm")
    for _ in range(200):
        storm.error("boom-template-%s", "same")
    text = _log_text(daily_file_log)
    assert text.count("boom-template-same") == 1, "同型消息窗口内只记首条"


def test_distinct_args_never_folded(daily_file_log):
    """反向判据（评审 P1）：请求行/AI 留痕行共用固定模板、参数各异——必须逐行落盘。"""
    req = logging.getLogger("api.request")
    for path in ("/api/a", "/api/b", "/api/c", "/api/d"):
        req.info("%s %s %s %.0fms", "POST", path, 200, 12.0)
    ai = logging.getLogger("ai_client")
    tpl = "event=ai_call op=%s result=ok"
    for op in ("op_x", "op_y"):
        ai.info(tpl, op)

    text = _log_text(daily_file_log)
    for path in ("/api/a", "/api/b", "/api/c", "/api/d"):
        assert path in text, f"不同参数的请求行不得被折叠：{path} 丢失"
    assert text.count("event=ai_call") == 2, "不同 operation 的 AI 行不得被折叠"


def test_fold_filter_carries_count_after_window(monkeypatch):
    f = FoldRepeatFilter(window_seconds=10.0)
    now = [1000.0]
    monkeypatch.setattr(logging_setup.time, "monotonic", lambda: now[0])

    def _rec():
        return logging.LogRecord("x", logging.ERROR, "p", 1, "boom-tpl", None, None)

    assert f.filter(_rec()) is True  # 首条放行
    now[0] += 1
    assert f.filter(_rec()) is False  # 窗口内折叠
    now[0] += 1
    assert f.filter(_rec()) is False
    now[0] += 11  # 窗口关闭
    third = _rec()
    assert f.filter(third) is True
    assert "[+2 重复已折叠]" in third.getMessage(), "折叠计数必须随下一条放行消息落盘"


# ⑧ 日志目录（含父目录）不存在时初始化后首条消息仍落盘


def test_missing_dirs_created(tmp_path, monkeypatch):
    nested = tmp_path / "nested" / "deeper" / "logs"
    monkeypatch.delenv("AINOVEL_LOG_OFF", raising=False)
    monkeypatch.setenv("AINOVEL_LOG_DIR", str(nested))
    root, uv = logging.getLogger(), logging.getLogger("uvicorn")
    snap_root, snap_uv = list(root.handlers), list(uv.handlers)
    try:
        assert setup_logging() == nested
        assert nested.is_dir(), "初始化必须级联创建日志目录"
        logging.getLogger("biz.mkdir").info("first-line-XYZ")
        assert "first-line-XYZ" in (nested / "app.log").read_text(encoding="utf-8")
    finally:
        for h in list(root.handlers):
            if h not in snap_root:
                root.removeHandler(h)
        for h in list(uv.handlers):
            if h not in snap_uv:
                uv.removeHandler(h)
        # llm 专项 handler 挂具名 logger（不在 root 上）——不摘会指向已删 tmp 目录
        # 并泄漏进后续用例
        for name in _LLM_LOGGERS:
            lg = logging.getLogger(name)
            for h in list(lg.handlers):
                if getattr(h, "_ainovel_llm", False):
                    lg.removeHandler(h)


# 静音名单：httpx 等不进文件（D2）


def test_noisy_loggers_silenced(daily_file_log):
    _ensure_file_exists(daily_file_log)
    logging.getLogger("httpx").info("HTTPX-NOISE-XYZ")
    assert "HTTPX-NOISE-XYZ" not in _log_text(daily_file_log)


# ⑨ llm.log 专项档（c-llm-call-log）：大模型出网调用双写 app.log＋llm.log


def _llm_handlers(name: str) -> list[logging.Handler]:
    return [
        h for h in logging.getLogger(name).handlers
        if getattr(h, "_ainovel_llm", False)
    ]


def test_llm_handler_mounted_with_rotation_params(daily_file_log):
    for name in ("ai_client", "llm_probe", "zhuque.client"):
        handlers = _llm_handlers(name)
        assert len(handlers) == 1, f"{name} 须恰好挂一个 llm 专项 handler"
    handler = _llm_handlers("ai_client")[0]
    assert isinstance(handler, logging.handlers.TimedRotatingFileHandler)
    assert handler.when == "MIDNIGHT", "llm.log 与 app.log 同口径按自然日轮转"
    assert handler.backupCount == 5, "llm.log 同口径保留 5 天"


def test_setup_idempotent_llm_handler_not_duplicated(daily_file_log):
    setup_logging()
    setup_logging()
    assert len(_llm_handlers("ai_client")) == 1, "重入初始化不得重复挂 llm handler"


def test_llm_line_dual_writes_app_and_llm(daily_file_log):
    logging.getLogger("llm_probe").warning(
        "event=llm_probe kind=models_list vendor=%s format=%s host=%s path=%s"
        " model=%s status=%d duration_ms=%.0f result=%s",
        "custom", "openai", "relay.example.com", "/v1/models", "-", 401, 123.0,
        "auth_error",
    )
    llm_text = (daily_file_log / "llm.log").read_text(encoding="utf-8")
    assert "status=401" in llm_text and "result=auth_error" in llm_text, (
        "探针 401 行是 llm.log 的定诊本命（Gemini 401 案）"
    )
    assert "relay.example.com" in _log_text(daily_file_log), (
        "双写：app.log 求诊主档不缺行"
    )


def test_llm_file_excludes_non_llm_loggers(daily_file_log):
    _ensure_file_exists(daily_file_log)
    logging.getLogger("biz.other").info("NOT-LLM-XYZ")
    logging.getLogger("llm_probe").info("LLM-LINE-XYZ")
    llm_text = (daily_file_log / "llm.log").read_text(encoding="utf-8")
    assert "LLM-LINE-XYZ" in llm_text
    assert "NOT-LLM-XYZ" not in llm_text, "llm.log 只收大模型出网调用，业务行不进"


def test_log_off_no_llm_handler(monkeypatch):
    monkeypatch.setenv("AINOVEL_LOG_OFF", "1")
    assert setup_logging() is None
    for name in ("ai_client", "llm_probe", "zhuque.client"):
        assert _llm_handlers(name) == [], f"关闭态不得给 {name} 挂 llm handler"


# ⑩ 启动首行＋目录回退链（c-shell-release-env-order：v0.30 真机「只有 startup.log
#    没有 app.log」排查教训——delay=True 首条 emit 失败会被静默吞掉、整份日志消失）


def test_boot_line_creates_app_log_immediately(daily_file_log):
    """setup_logging 返回时 app.log 必已存在且带「logging ready」启动行（含最终落点）。"""
    log_dir = daily_file_log
    text = (log_dir / "app.log").read_text(encoding="utf-8")
    assert "logging ready" in text, "启动即落首行——app.log 不得等首条业务日志才出现"
    assert str(log_dir) in text, "首行必须写明最终落点（回退发生过时现场一眼可辨）"


def test_unwritable_log_dir_falls_back_to_next_candidate(tmp_path, monkeypatch):
    """AINOVEL_LOG_DIR 写不出（被文件占位）→ 落 DATA_ROOT/logs 并返回该目录；
    绝不静默——返回 None 只发生在全链不可写。"""
    monkeypatch.delenv("AINOVEL_LOG_OFF", raising=False)
    blocker = tmp_path / "blocked"
    blocker.write_text("i am a file", encoding="utf-8")
    monkeypatch.setenv("AINOVEL_LOG_DIR", str(blocker / "logs"))
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    root, uv = logging.getLogger(), logging.getLogger("uvicorn")
    snap_root, snap_uv = list(root.handlers), list(uv.handlers)
    try:
        got = setup_logging()
        assert got == tmp_path / "data" / "logs", "写不出必须回退到 DATA_ROOT/logs"
        assert "logging ready" in (got / "app.log").read_text(encoding="utf-8")
    finally:
        for h in list(root.handlers):
            if h not in snap_root:
                root.removeHandler(h)
        for h in list(uv.handlers):
            if h not in snap_uv:
                uv.removeHandler(h)
        for name in _LLM_LOGGERS:
            lg = logging.getLogger(name)
            for h in list(lg.handlers):
                if getattr(h, "_ainovel_llm", False):
                    lg.removeHandler(h)


def test_fold_filter_unhashable_args_never_raises():
    """过滤器纪律：args 含 dict（logger.info(msg, {"k": v}) 的 %()s 形态，元组包 dict）
    整体不可哈希——不得 TypeError 炸调用方，参数不同照常放行不折叠。"""
    f = FoldRepeatFilter()
    rec = logging.LogRecord("x", logging.INFO, "p", 1, "hi %(k)s", ({"k": 1},), None)
    assert f.filter(rec) is True
    rec2 = logging.LogRecord("x", logging.INFO, "p", 1, "hi %(k)s", ({"k": 2},), None)
    assert f.filter(rec2) is True, "参数不同必须照常放行（不折叠）"
