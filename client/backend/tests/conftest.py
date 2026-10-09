"""Pytest configuration -- stubs external modules + session-level test DB base."""

import asyncio
import logging
import os
import sys
import tempfile
import types

import pytest
from sqlalchemy import text

# ── 无模板源环境的测试降级（c-prompt-source-flip 4.3 收口）──────────────────
# 提示词模板住 sibling 仓 awesome-novel-prompts（主库零 .prompt）；触及真实模板
# 的 AI 链路测试在「无模板源」环境（主库 CI：单仓 checkout、不配跨仓 token）必
# 因缺模板失败。口径与 e2e-scheduled 未配 S_SERVER_TOKEN 时整轮跳过同源：
# **缺源＝跳过，不是伪装通过**；本地/docker/e2e 按 CLAUDE.md 配好
# PROMPT_PACK_DEV_DIR（或历史包内镜像）即全量真跑。
#
# 判定两层：① 失败详情直接含 PromptPackMissing / prompts_missing（直读模板的
# 单测）；② 本轮测试内后端打过 `event=prompts_missing` 日志（端点 503 收敛点
# 统一留痕）——覆盖「端点没调到 AI、测试读 fake 调用记录才炸」的二阶失败。
# 走日志信号而非逐测试打标：零逐文件改动，新增 AI 测试自动纳入，模块 reload
# 也不影响（logging 全局）。误伤面＝同一测试内既触发缺包又有无关失败，此时
# skip 消息会写明触发原因，不会静默。
_PROMPT_MISS = {"miss": False}


class _PromptMissHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if "prompts_missing" in record.getMessage():
            _PROMPT_MISS["miss"] = True


def _prompt_source_ready() -> bool:
    """解析序②有无可用模板源（DEV_DIR 指定目录或包内镜像，至少 1 个 .prompt）。"""
    try:
        from prompts import dev_template_dir
    except Exception:  # noqa: BLE001 — loader 不可用视同无源
        return False
    dev_dir = dev_template_dir()
    try:
        return bool(dev_dir) and any(n.endswith(".prompt") for n in os.listdir(dev_dir))
    except OSError:
        return False


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    _PROMPT_MISS["miss"] = False
    handler = _PromptMissHandler(level=logging.DEBUG)
    uv_logger = logging.getLogger("uvicorn.error")
    # 缺包 503 的留痕走 info()——测试环境该 logger 生效级别沿 root（WARNING），
    # 不抬级别 info() 在 logger 门就被丢弃，handler 收不到；连同快照还原。
    snap_level = uv_logger.level
    uv_logger.setLevel(logging.DEBUG)
    uv_logger.addHandler(handler)
    yield
    uv_logger.removeHandler(handler)
    uv_logger.setLevel(snap_level)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "needs_prompts: 读取真实提示词模板——无模板源环境（主库 CI）收集期即跳过",
    )


def pytest_collection_modifyitems(config, items):
    """显式逃生口：无日志/无文本信号的缺源失败（如 job_runner 静默落库态）
    用 `pytest.mark.needs_prompts` 整文件/整类标记，收集期直接跳过。"""
    if _prompt_source_ready():
        return
    skip = pytest.mark.skip(
        reason="无模板源（PROMPT_PACK_DEV_DIR/sibling 提示词仓）——needs_prompts 标记按缺源跳过（c-prompt-source-flip）"
    )
    for item in items:
        if item.get_closest_marker("needs_prompts"):
            item.add_marker(skip)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when not in ("setup", "call") or not rep.failed:
        return
    if _prompt_source_ready():
        return
    detail = str(rep.longrepr)
    if (
        "PromptPackMissing" in detail
        or "prompts_missing" in detail
        # 后台 job 捕获异常后落库的是消息文案（state.error / detail 文本）
        or "Prompt pack missing template" in detail
        or _PROMPT_MISS["miss"]
    ):
        rep.outcome = "skip"
        rep.longrepr = (
            item.nodeid,
            0,
            "无模板源（PROMPT_PACK_DEV_DIR/sibling 提示词仓）——触及真实模板的测试按缺源跳过（c-prompt-source-flip）",
        )


def _reject_httpx_object(name: str, value: object) -> None:
    """stub 拒收任何 MRO 根模块为 httpx 的构造参数（按真 SDK 最严口径守）。

    真 anthropic ≥1.4 会拒收（传输层迁 httpx2 后抛 TypeError）；真 openai 3.x
    目前尚容忍 httpx.Timeout，但传输层同样已是 httpx2——stub 有意从严统一两
    侧口径，防 openai 路径将来收紧时再静默漏进发布包（本次 500 的病根即
    stub「什么都收」，与真 SDK 脱节）。
    """
    for cls in type(value).__mro__:
        module = getattr(cls, "__module__", None)
        if isinstance(module, str) and module.partition(".")[0] == "httpx":
            raise TypeError(
                f"Invalid `{name}` argument; `httpx.{cls.__name__}` is from the "
                "`httpx` package, but this SDK uses `httpx2`."
            )


# Stub the `anthropic` module so tests can import story modules
# without the real SDK being installed.
if "anthropic" not in sys.modules:
    anthropic = types.ModuleType("anthropic")
    anthropic.__version__ = "0.0.0"

    class AsyncAnthropic:
        def __init__(self, *args, **kwargs):
            for k, v in kwargs.items():
                _reject_httpx_object(k, v)

    # ai_client 归一网络异常（AITimeoutError）与上游 404/405（AIRequestError）
    # 依赖这几个名字，stub 与真 SDK 同形（status_code 取 response.status_code）
    class APIConnectionError(Exception):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    class APIStatusError(Exception):
        def __init__(self, message, *, response=None, body=None):
            super().__init__(message)
            self.response = response
            self.status_code = getattr(response, "status_code", None)
            self.body = body

    class Timeout:
        """真 SDK 的 Timeout 类：与 httpx 无关，逐相位接收 connect/read/write/pool。"""

        def __init__(self, *, connect=None, read=None, write=None, pool=None):
            self.connect, self.read, self.write, self.pool = connect, read, write, pool

    anthropic.AsyncAnthropic = AsyncAnthropic
    anthropic.APIConnectionError = APIConnectionError
    anthropic.APITimeoutError = APITimeoutError
    anthropic.APIStatusError = APIStatusError
    anthropic.Timeout = Timeout
    sys.modules["anthropic"] = anthropic

    # Also stub anthropic.lib.streaming if accessed
    _streaming = types.ModuleType("anthropic.lib")
    _streaming.__path__ = []
    sys.modules["anthropic.lib"] = _streaming

    _streaming_stream = types.ModuleType("anthropic.lib.streaming")
    sys.modules["anthropic.lib.streaming"] = _streaming_stream

# Stub the `openai` module
if "openai" not in sys.modules:
    openai_mod = types.ModuleType("openai")
    openai_mod.__version__ = "0.0.0"

    class AsyncOpenAI:
        def __init__(self, *args, **kwargs):
            for k, v in kwargs.items():
                _reject_httpx_object(k, v)

    # 同 anthropic：补齐 ai_client 依赖的异常名（含 404/405 归一用的 APIStatusError）
    class APIConnectionError(Exception):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    class APIStatusError(Exception):
        def __init__(self, message, *, response=None, body=None):
            super().__init__(message)
            self.response = response
            self.status_code = getattr(response, "status_code", None)
            self.body = body

    class Timeout:
        def __init__(self, *, connect=None, read=None, write=None, pool=None):
            self.connect, self.read, self.write, self.pool = connect, read, write, pool

    openai_mod.AsyncOpenAI = AsyncOpenAI
    openai_mod.APIConnectionError = APIConnectionError
    openai_mod.APITimeoutError = APITimeoutError
    openai_mod.APIStatusError = APIStatusError
    openai_mod.Timeout = Timeout
    sys.modules["openai"] = openai_mod

    # Stub openai.types.chat if accessed
    _types = types.ModuleType("openai.types")
    _types.__path__ = []
    sys.modules["openai.types"] = _types

    _chat = types.ModuleType("openai.types.chat")
    sys.modules["openai.types.chat"] = _chat


# ── Session-level test database base ─────────────────────────────────────────
# 组合后端（ADR-001）mapped 路径写 DB：未自设 DATABASE_URL 的测试若触库，
# 落在临时库而非真实 ./data/novel.db。自设 DATABASE_URL 的测试在各模块顶部
# 覆盖这两个变量（engine 模块级缓存，第一个 import 者生效），维持现状。
_TMP_DATA_ROOT = tempfile.mkdtemp(prefix="ai-novel-test-data-")
os.environ["DATA_ROOT"] = _TMP_DATA_ROOT
# backend-logging：测试进程一律关闭文件日志（main.py 顶部 setup_logging 幂等
# 调用会随任意测试导入 main 触发）——否则 pytest 向 DATA_ROOT/logs 刷文件。
# 需要真实文件日志的用例用 daily_file_log fixture 临时开启并完整还原。
os.environ["AINOVEL_LOG_OFF"] = "1"
# c-db-per-version：测试库名＝「本机版本」派生（不设 CLIENT_VERSION 时是 dev 哨兵，
# 会话库会被按 dev 语义对待）——显式钉一个版本，测试库名与断言口径一致
os.environ.setdefault("CLIENT_VERSION", "0.25")
from schema_version import active_db_filename as _active_db_filename

os.environ["DATABASE_URL"] = (
    f"sqlite+aiosqlite:///{os.path.join(_TMP_DATA_ROOT, _active_db_filename())}"
)


@pytest.fixture(scope="session", autouse=True)
def _force_weak_pack_keystore():
    """提示词包钥匙库：测试一律走 weak 档（机器指纹派生），**不碰真实 DPAPI/Keychain**。

    为什么：真档会把钥匙写进「当前用户的系统钥匙串」（macOS 实测会留下
    awesomenovel-prompt-pack 条目），单元测试不该在开发机/CI 上留这种副作用。
    weak 只是换一把派生钥匙（解不开真档写的容器），**不是绕过**；真档路径由
    client/packaging/build/verify_pack_hardening.ps1 真机验收与人工实测覆盖。
    """
    prev = os.environ.get("AINOVEL_PACK_KEYSTORE")
    os.environ["AINOVEL_PACK_KEYSTORE"] = "weak"
    yield
    if prev is None:
        os.environ.pop("AINOVEL_PACK_KEYSTORE", None)
    else:
        os.environ["AINOVEL_PACK_KEYSTORE"] = prev


@pytest.fixture(scope="session", autouse=True)
def _session_test_db():
    """建表基座：任何测试触碰 DB 前，表已建好（含 project_settings）。

    import models 注册全部表——否则纯文件测试单独跑时 Base.metadata 为空，
    create_all 建不出 project_settings，组合后端写 DB 报 no such table。
    """
    import models  # noqa: F401
    from db import Base, engine

    async def _create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # PR0（c-novel-export-roundtrip）：会话库视为当前版本库——不打指纹戳，
        # lifespan 首启会把它当旧库整库留档，后续测试的数据全丢。
        import legacy_archive

        fp = legacy_archive.compute_schema_fingerprint(Base.metadata)
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT OR IGNORE INTO app_meta (key, value) VALUES (:k, :v)"),
                {"k": legacy_archive.SCHEMA_ID_KEY, "v": fp},
            )

        # key-crypto-selfcontained：测试库钥匙初始化（一次全局装载；
        # 死文态/迁移态用例用 crypto._reset_for_tests() 轮转后自行重置）。
        # 排在指纹戳之后，与生产 lifespan 同序。
        from api_configs.crypto import init_crypto
        from db import async_session as _session_factory

        async with _session_factory() as session:
            await init_crypto(session)

    asyncio.run(_create_tables())
    yield


# ── 章族入库后的通用种子（跨测试文件复用）────────────────────────────────────


async def seed_chapter_db(root: str, chapter: dict, *, summary: str = "") -> None:
    """种 Novel/Volume/Chapter 行并经统一写入口落章数据。

    slug 取 root 目录名保证跨测试唯一（UNIQUE(user_id, slug)）；
    供 AI 链路测试以 root_path 关联。story/世界观等设定走 KV 种子（seed_settings_to_db）。
    """
    import os

    from db import async_session
    from models import Novel
    from models.volume import Volume
    from repositories import chapter_repo

    async with async_session() as session:
        proj = Novel(
            user_id="seed_user", name="seed小说",
            slug=f"seed-{os.path.basename(root)}",
            root_path=root, source="manual", current_phase="write",
        )
        session.add(proj)
        await session.flush()
        vol = Volume(
            project_id=proj.id, volume_no=int(chapter.get("volume", 1) or 1),
            title="第一卷", summary=summary,
        )
        session.add(vol)
        await session.flush()
        await chapter_repo.upsert(
            session, proj.id, vol.id,
            chapter_no=int(chapter.get("chapter", 1) or 1),
            ref=f"vol-{chapter.get('volume', 1)}-ch-{chapter.get('chapter', 1)}",
            title=chapter.get("title", "第1章"),
        )
        await session.commit()

    from chapters.store import save_chapter

    await save_chapter(
        root, f"vol-{chapter.get('volume', 1)}-ch-{chapter.get('chapter', 1)}", chapter
    )


# ── backend-logging：按天文件日志测试夹具 ────────────────────────────────────
import logging as _logging

from logging_setup import _LLM_LOGGERS, _UPGRADE_LOGGERS
from logging_setup import setup_logging as _setup_logging

_NOISY = ("httpx", "httpcore", "openai", "sqlalchemy")


@pytest.fixture()
def daily_file_log(tmp_path, monkeypatch):
    """临时开启真实按天文件日志（AINOVEL_LOG_OFF 会被本夹具移除），结束后完整
    还原 root/uvicorn/noisy/llm 与 upgrade 专项挂点的 handler 与级别——测试互不渗漏。"""
    monkeypatch.delenv("AINOVEL_LOG_OFF", raising=False)
    monkeypatch.setenv("AINOVEL_LOG_DIR", str(tmp_path / "logs"))
    root, uv = _logging.getLogger(), _logging.getLogger("uvicorn")
    llm_loggers = {n: _logging.getLogger(n) for n in (*_LLM_LOGGERS, *_UPGRADE_LOGGERS)}
    snap_root_h, snap_uv_h = list(root.handlers), list(uv.handlers)
    snap_llm_h = {n: list(lg.handlers) for n, lg in llm_loggers.items()}
    snap = (root.level, uv.level, uv.propagate,
            _logging.getLogger("uvicorn.access").level,
            {n: _logging.getLogger(n).level for n in _NOISY})
    log_dir = _setup_logging()
    yield log_dir
    for h in list(root.handlers):
        if h not in snap_root_h:
            root.removeHandler(h)
    for h in list(uv.handlers):
        if h not in snap_uv_h:
            uv.removeHandler(h)
    for n, lg in llm_loggers.items():
        for h in list(lg.handlers):
            if h not in snap_llm_h[n]:
                lg.removeHandler(h)
    root_level, uv_level, uv_prop, access_level, noisy = snap
    root.setLevel(root_level)
    uv.setLevel(uv_level)
    uv.propagate = uv_prop
    _logging.getLogger("uvicorn.access").setLevel(access_level)
    for n, lvl in noisy.items():
        _logging.getLogger(n).setLevel(lvl)

