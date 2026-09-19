"""Pytest configuration -- stubs external modules + session-level test DB base."""

import asyncio
import os
import sys
import tempfile
import types

import pytest
from sqlalchemy import text


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

    # ai_client 归一网络异常（AITimeoutError）依赖这两个名字，stub 与真 SDK 同形
    class APIConnectionError(Exception):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    class Timeout:
        """真 SDK 的 Timeout 类：与 httpx 无关，逐相位接收 connect/read/write/pool。"""

        def __init__(self, *, connect=None, read=None, write=None, pool=None):
            self.connect, self.read, self.write, self.pool = connect, read, write, pool

    anthropic.AsyncAnthropic = AsyncAnthropic
    anthropic.APIConnectionError = APIConnectionError
    anthropic.APITimeoutError = APITimeoutError
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

    # 同 anthropic：补齐 ai_client 依赖的异常名
    class APIConnectionError(Exception):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    class Timeout:
        def __init__(self, *, connect=None, read=None, write=None, pool=None):
            self.connect, self.read, self.write, self.pool = connect, read, write, pool

    openai_mod.AsyncOpenAI = AsyncOpenAI
    openai_mod.APIConnectionError = APIConnectionError
    openai_mod.APITimeoutError = APITimeoutError
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
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_TMP_DATA_ROOT, 'novel.db')}"


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

    asyncio.run(_create_tables())
    yield


# ── 章族入库后的通用种子（跨测试文件复用）────────────────────────────────────


async def seed_chapter_db(root: str, chapter: dict, *, summary: str = "") -> None:
    """种 Novel/Volume/Chapter 行并经统一写入口落章数据。

    slug 取 root 目录名保证跨测试唯一（UNIQUE(user_id, slug)）；
    供 AI 链路测试以 root_path 关联。story/世界观/角色/伏笔仍走文件种子。
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
