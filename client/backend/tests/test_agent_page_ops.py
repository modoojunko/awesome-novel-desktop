"""agent 页面操作（c-agent-page-ops）测试。

- /auth 专用命令：查档/两档切换/坏值提示（HTTP 级，走真实 route）
- write_chapter_fields_cap：patch 语义（只写 provided 键）/前后对比/白名单/闭集
- write_settings_field_cap：genre merge 不覆盖他字段/story 单键/world 合并
- navigate 工具：target 校验（视图白名单/章定位仅工作台/页签白名单）
"""

import asyncio
import os
import tempfile
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_page_ops.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_root = tempfile.mkdtemp(prefix="page_ops_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_root

from db import Base, engine  # noqa: E402

_CFG = os.path.join(_tmp_root, "config.json")

from fastapi.testclient import TestClient  # noqa: E402

import auth_local.middleware as _mw  # noqa: E402
import auth_local.service as _service  # noqa: E402
from main import app  # noqa: E402


async def _setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)



asyncio.run(_setup())

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _startup():
    _orig = _mw.CONFIG_FILE
    with client:
        yield
    _mw.CONFIG_FILE = _orig


def _set_session():
    _mw.CONFIG_FILE = _CFG
    _service.CONFIG_FILE = _CFG
    cfg = _service.get_local_config()
    cfg.update({
        "tier": "max",
        "token": "tok-pageops",
        "username": "pageops",
        "last_login_at": datetime.now(UTC).isoformat(),
    })
    _service.save_local_config(cfg)


@pytest.fixture(autouse=True)
def _fresh_config():
    _orig = _mw.CONFIG_FILE
    _set_session()
    yield
    if os.path.exists(_CFG):
        os.remove(_CFG)
    _mw.CONFIG_FILE = _orig


def _mk_book() -> str:
    r = client.post(
        "/api/novels",
        json={"name": f"page-ops-{datetime.now(UTC).timestamp()}", "source": "manual"},
        headers={"Authorization": "Bearer tok-pageops"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _chat(book_id: str, message: str) -> str:
    """POST /chat 收 SSE 文本（命令回复路径不依赖模型）。"""
    with client.stream(
        "POST",
        f"/api/novels/{book_id}/assistant/chat",
        json={"message": message, "page": "工作台 · 卷纲", "thread": "vol"},
        headers={"Authorization": "Bearer tok-pageops"},
    ) as r:
        assert r.status_code == 200, r.text[:200]
        return "".join(chunk.decode("utf-8") for chunk in r.iter_bytes())


# ── /auth 专用命令 ────────────────────────────────────────────────────────


def test_auth_command_reports_current_and_switches_two_tiers():
    book = _mk_book()
    out = _chat(book, "/auth")
    assert "当前授权：每写必确认" in out
    out = _chat(book, "/auth 自动")
    assert "授权已切到「自动执行·本书内」" in out
    # 切档后查档＝自动档（书级生效）
    out = _chat(book, "/auth")
    assert "当前授权：自动执行·本书内" in out
    out = _chat(book, "/auth 确认")
    assert "授权已切到「每写必确认（默认）」" in out


def test_auth_command_rejects_unknown_tier():
    book = _mk_book()
    out = _chat(book, "/auth all")
    assert "没这个档位" in out
    assert "/auth 确认" in out and "/auth 自动" in out


# ── write_chapter_fields_cap ─────────────────────────────────────────────


class _FakeScalars:
    def __init__(self, obj):
        self._o = obj

    def first(self):
        return self._o


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def scalars(self, stmt):
        return _FakeScalars(SimpleNamespace(id="n1", root_path="/tmp/page-ops-book"))


def _run(coro):
    return asyncio.run(coro)


def _patch_chapter_store(monkeypatch, assembled: dict, saved: dict):
    import chapters.store as store_mod
    import db as db_mod

    async def fake_load(root, ref):
        return assembled

    async def fake_save(root, ref, data):
        saved.update({"root": root, "ref": ref, "data": data})

    # Novel select 桩（cap 只取 root_path）——db.async_session 函数内导入，打模块属性
    class _FakeScalars:
        def __init__(self, obj):
            self._o = obj

        def first(self):
            return self._o

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def scalars(self, stmt):
            return _FakeScalars(SimpleNamespace(id="n1", root_path="/tmp/page-ops-book"))

        async def all(self, stmt):
            return []

    monkeypatch.setattr(db_mod, "async_session", lambda: _FakeSession())
    monkeypatch.setattr(store_mod, "load_chapter", fake_load)
    monkeypatch.setattr(store_mod, "save_chapter", fake_save)


def _assembled():
    return {
        "outline": {"summary": "旧概要", "characters": ["林野"]},
        "memo": {"required_changes": ["旧变化"], "prohibitions": []},
        "emotional_design": {"primary_mood": "旧情绪"},
        "challenge": "旧挑战",
        "plot_stage": "铺垫",
        "ladder_exit": "旧落点",
        "plot_items": ["旧条目"],
        "chapter": {"title": "旧题", "word_target": 2500},
    }


def test_write_chapter_fields_cap_patches_only_given_keys(monkeypatch):
    """patch 语义：只传挑战＋主情绪 → 其余字段零触碰；changes 带前后对比。"""
    from assistant.caps.chapter import write_chapter_fields_cap

    saved: dict = {}
    _patch_chapter_store(monkeypatch, _assembled(), saved)

    res = _run(
        write_chapter_fields_cap(
            "n1", "vol-1-ch-2", "u1",
            {"challenge": "新挑战", "primary_mood": "紧绷"},
        )
    )
    data = saved["data"]
    # 只写 provided 键映射出的族——patch-gates 保现值
    assert data == {"challenge": "新挑战", "emotional_design": {"primary_mood": "紧绷"}}
    assert saved["ref"] == "vol-1-ch-2"
    assert {c["field"] for c in res["changes"]} == {"challenge", "primary_mood"}
    before = {c["field"]: c["before"] for c in res["changes"]}
    after = {c["field"]: c["after"] for c in res["changes"]}
    assert before["challenge"] == "旧挑战" and after["challenge"] == "新挑战"
    assert before["primary_mood"] == "旧情绪" and after["primary_mood"] == "紧绷"


def test_write_chapter_fields_cap_list_and_stage_gates(monkeypatch):
    """列表字段形状闸（非数组拒）＋plot_stage 闭集拒（422 归一人话）。"""
    from assistant.caps.chapter import write_chapter_fields_cap

    saved: dict = {}
    _patch_chapter_store(monkeypatch, _assembled(), saved)

    with pytest.raises(Exception) as ei:
        _run(write_chapter_fields_cap("n1", "vol-1-ch-2", "u1", {"plot_items": "不是数组"}))
    assert "字符串数组" in str(ei.value)

    with pytest.raises(Exception) as ei:
        _run(write_chapter_fields_cap("n1", "vol-1-ch-2", "u1", {"plot_stage": "不存在的阶段"}))
    assert "阶段" in str(ei.value)

    # 合法列表写：required_changes
    res = _run(write_chapter_fields_cap("n1", "vol-1-ch-2", "u1", {"required_changes": ["新变化"]}))
    assert saved["data"]["memo"] == {"required_changes": ["新变化"]}
    assert res["changes"][0]["after"] == ["新变化"]


def test_write_chapter_fields_cap_rejects_unknown_key(monkeypatch):
    from assistant.caps.chapter import write_chapter_fields_cap

    saved: dict = {}
    _patch_chapter_store(monkeypatch, _assembled(), saved)
    with pytest.raises(Exception) as ei:
        _run(write_chapter_fields_cap("n1", "vol-1-ch-2", "u1", {"不存在的字段": "x"}))
    assert "不支持的章纲字段" in str(ei.value)
    assert saved == {}  # 未落库


def test_preview_write_chapter_fields_reads_current(monkeypatch):
    """preview_builder 读现值构造字段前后对比（确认档授权卡渲染源）。"""
    from assistant.tools import get_tool

    tool = get_tool("write_chapter_fields")
    assert tool is not None and tool.preview_builder is not None

    _patch_chapter_store(monkeypatch, _assembled(), {})
    project = SimpleNamespace(id="n1", root_path="/tmp/page-ops-book")
    pv = _run(
        tool.preview_builder(
            {"chapter_ref": "vol-1-ch-2", "fields": {"challenge": "新挑战"}}, project,
        )
    )
    assert pv["entity"] == "chapter:vol-1-ch-2"
    assert pv["changes"][0]["field"] == "challenge"
    assert pv["changes"][0]["before"] == "旧挑战"
    assert pv["changes"][0]["after"] == "新挑战"


# ── write_settings_field_cap ─────────────────────────────────────────────


class _FakeStorage:
    """story.yaml/world.yaml 的内存仓储（read_yaml/write_yaml 打桩）。"""

    def __init__(self, files: dict):
        self.files = files
        self.written: list[tuple[str, dict]] = []

    async def read_yaml(self, root, path):
        return self.files.get(path, {}) or {}

    async def write_yaml(self, root, path, data):
        self.files[path] = data
        self.written.append((path, data))


def _patch_settings_env(monkeypatch, storage: _FakeStorage, genre_card: dict, put_capture: dict):

    import db as db_mod

    async def fake_get_novel_genre(session, novel_id):
        return dict(genre_card)

    async def fake_put_novel_genre(session, novel_id, payload):
        put_capture["payload"] = payload

    def fake_get_storage():
        return storage

    import genres.novel_genre_service as genre_svc

    monkeypatch.setattr(genre_svc, "get_novel_genre", fake_get_novel_genre)
    monkeypatch.setattr(genre_svc, "put_novel_genre", fake_put_novel_genre)

    async def fake_select_first_project():
        return SimpleNamespace(id="n1", root_path="/tmp/page-ops-book")

    # Novel select：把 db.async_session 换成桩（scalars 返回桩项目）
    class _FakeScalars2:
        def __init__(self, obj):
            self._o = obj

        def first(self):
            return self._o

    class _FakeSession2:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def scalars(self, stmt):
            return _FakeScalars2(SimpleNamespace(id="n1", root_path="/tmp/page-ops-book"))

        async def all(self, stmt):
            return []

        async def commit(self):
            return None

    monkeypatch.setattr(db_mod, "async_session", lambda: _FakeSession2())
    monkeypatch.setattr("filesystem.storage.get_storage", fake_get_storage)


def test_write_settings_field_cap_genre_merges_without_clobber(monkeypatch):
    """genre 单字段写＝现卡整体合并后整卡落库——其他字段不被清空。"""
    from assistant.caps.settings import write_settings_field_cap

    card = {
        "core_promise": "旧承诺",
        "promise_note": "备注保留",
        "forbidden_list": [{"tagId": "t1", "text": "不能写成爽文"}],
        "cost_ratio": 3,
        "battlefield": ["旧战场"],
    }
    storage = _FakeStorage({})
    put_capture: dict = {}
    _patch_settings_env(monkeypatch, storage, card, put_capture)

    res = _run(
        write_settings_field_cap("n1", "genre", "battlefield", ["哨站", "教堂"], "u1")
    )
    payload = put_capture["payload"]
    # 只改 battlefield——他字段原样保留（merge 不 clobber）
    assert payload["battlefield"] == ["哨站", "教堂"]
    assert payload["core_promise"] == "旧承诺"
    assert payload["promise_note"] == "备注保留"
    assert payload["forbidden_list"] == [{"tagId": "t1", "text": "不能写成爽文"}]
    assert "旧战场" in str(res["before"])
    assert "哨站" in res["after"]
    assert res["entity"] == "settings:genre:battlefield"


def test_write_settings_field_cap_story_and_world(monkeypatch):
    """story.synopsis 单键写不覆盖 story.yaml 其他键；world v2 键合并写。"""
    from assistant.caps.settings import write_settings_field_cap

    storage = _FakeStorage({
        "story.yaml": {"synopsis": "旧简介", "genre": "西式奇幻"},
        "settings/world-setting.yaml": {"power": "旧力量体系", "stage": "旧阶段"},
    })
    put_capture: dict = {}
    _patch_settings_env(monkeypatch, storage, {}, put_capture)

    res = _run(write_settings_field_cap("n1", "story", "synopsis", "新简介", "u1"))
    story = storage.files["story.yaml"]
    assert story["synopsis"] == "新简介"
    assert story["genre"] == "西式奇幻"  # 其他键零触碰
    assert res["before"] == "旧简介" and res["after"] == "新简介"

    res = _run(write_settings_field_cap("n1", "world", "power", "新力量体系", "u1"))
    world = storage.files["settings/world-setting.yaml"]
    assert world["power"] == "新力量体系"
    assert world["stage"] == "旧阶段"  # v2 现键带齐——merge 不清他键
    assert res["entity"] == "settings:world:power"


def test_write_settings_field_cap_rejects_unknown(monkeypatch):
    from assistant.caps.settings import write_settings_field_cap

    storage = _FakeStorage({})
    _patch_settings_env(monkeypatch, storage, {}, {})
    with pytest.raises(Exception) as ei:
        _run(write_settings_field_cap("n1", "hooks", "任意", "x", "u1"))
    assert "不支持的字段" in str(ei.value)


# ── navigate 工具 target 校验 ────────────────────────────────────────────


def test_navigate_declares_navigate_effect():
    """navigate 走既有 navigate effect 通道（同 switch_tab）：registry 声明即生效。"""
    from assistant.tools import get_tool

    tool = get_tool("navigate")
    assert tool is not None and tool.kind == "read"
    assert tool.effect_action == "navigate"
    assert tool.effect_domain == "ui"
    assert tool.effect_target_from == "target"


def test_navigate_tool_target_validation(monkeypatch):
    """target 校验＋章存在性（review P3）：格式合法≠章存在。"""
    import db as db_mod
    from assistant.tools import ToolContext, get_tool

    class _Row:
        pass

    class _FakeScalars:
        def __init__(self, obj):
            self._o = obj

        def first(self):
            return self._o

    class _FakeSession:
        def __init__(self, obj):
            self._o = obj

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def scalars(self, stmt):
            return _FakeScalars(self._o)

    tool = get_tool("navigate")
    ctx = ToolContext(novel_id="n", root_path="/r", user_id="u")
    # 章存在：全链放行
    monkeypatch.setattr(db_mod, "async_session", lambda: _FakeSession(_Row()))
    ok = _run(tool.fn(ctx, "settings"))
    assert ok.ok and "设定面板" in ok.summary
    ok = _run(tool.fn(ctx, "workbench:vol-1-ch-3:prose"))
    assert ok.ok
    # 章不存在：人话拒绝（review P3 前会选到空）
    monkeypatch.setattr(db_mod, "async_session", lambda: _FakeSession(None))
    missing = _run(tool.fn(ctx, "workbench:vol-1-ch-99:prose"))
    assert not missing.ok and "没有「vol-1-ch-99」这一章" in missing.summary
    bad_view = _run(tool.fn(ctx, "胡写"))
    assert not bad_view.ok and "目标不认识" in bad_view.summary
    bad_ref = _run(tool.fn(ctx, "settings:vol-1-ch-3"))
    assert not bad_ref.ok and "workbench" in bad_ref.summary
    bad_tab = _run(tool.fn(ctx, "workbench:vol-1-ch-3:胡写"))
    assert not bad_tab.ok and "页签" in bad_tab.summary
