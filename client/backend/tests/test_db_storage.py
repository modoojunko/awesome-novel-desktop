"""DatabaseFileBackend 存储契约测试（ADR-001/002/003）。

依赖 conftest 会话级临时库基座（建表完成，含 project_settings）。
用独立临时 root_path 隔离，不落真实磁盘项目目录。
「LocalFileBackend / CompositeStorageBackend 盘上机器」已退役
（c-retire-local-file-storage）：settings KV 进 DB，非路由路径读 `{}` 写 no-op。
"""

import asyncio
import os
import tempfile

from filesystem.db_storage import DatabaseFileBackend, seed_settings_to_db
from filesystem.paths import (
    CHARACTER_DIR,
    KEY_TO_PATH,
    PATH_TO_KEY,
    route_relative_path,
)
from filesystem.storage import get_storage


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _tmp_root(prefix: str = "test_db_storage_") -> str:
    return tempfile.mkdtemp(prefix=prefix)


# ── paths.py 路由契约 ──────────────────────────────────────────────────────


def test_paths_routing():
    assert route_relative_path("settings/world-setting.yaml") == "world"
    assert route_relative_path("settings/settings-status.yaml") == "status"
    assert route_relative_path("settings/ai-model.yaml") == "ai-model"
    assert route_relative_path("story.yaml") == "story"
    assert route_relative_path("settings/character-setting/张三.yaml") == "character:张三.yaml"
    # 非 settings 路径 → None（storage 读 {} 写 no-op，盘上机器已退役）
    assert route_relative_path("volumes/vol-1.yaml") is None
    assert route_relative_path("chapters/vol-1-ch-1.yaml") is None
    assert route_relative_path("prompts/p.md") is None
    # threads.yaml → KV 专用路由（PR④）；不得进 PATH_TO_KEY（会泄漏 /settings/threads 端点）
    assert route_relative_path("threads.yaml") == "threads"
    assert "threads.yaml" not in PATH_TO_KEY
    # hooks 已退役（foreshadow-settings-v2 2.5）：伏笔升级真表 novel_hooks，
    # settings/hooks.yaml 不再路由 DB —— GET/PUT /settings/hooks 走「Invalid settings type」400
    assert route_relative_path("settings/hooks.yaml") is None
    assert len(PATH_TO_KEY) == 7  # 9 类设定 − characters（目录型）− hooks（真表化）
    assert set(KEY_TO_PATH) == set(PATH_TO_KEY.values())


def test_single_file_types_derivation():
    """settings/router.py SINGLE_FILE_TYPES 推导来源契约（去 story/status 后的单文件 CRUD）。"""
    from settings.router import SINGLE_FILE_TYPES

    assert set(KEY_TO_PATH) - {"story", "status"} == {
        "world", "style", "anti-ai", "genre", "ai-model",
    }
    assert SINGLE_FILE_TYPES == set(KEY_TO_PATH) - {"story", "status"}
    assert "characters" not in SINGLE_FILE_TYPES
    # hooks 分支下线（foreshadow-settings-v2 2.5）：不再受理 GET/PUT settings/hooks
    assert "hooks" not in SINGLE_FILE_TYPES


def test_multi_file_setting_keys():
    """目录型设定与单文件 key 不相交；characters 是唯一目录型。"""
    from filesystem.paths import MULTI_FILE_SETTING_KEYS

    assert MULTI_FILE_SETTING_KEYS == {"characters"}
    assert not (MULTI_FILE_SETTING_KEYS & set(KEY_TO_PATH))


def test_status_valid_types_derivation():
    """settings/status.py VALID_TYPES = readiness 集（D15/O-18 起 ai-model 不再可确认）。"""
    from settings.status import VALID_TYPES
    from workflow.readiness import READINESS_KEYS

    assert VALID_TYPES == set(READINESS_KEYS)
    assert VALID_TYPES == {
        "synopsis",
        "story-arc",
        "genre",
        "world",
        "style",
        "hooks",
        "characters",
    }
    # banned-words-into-style：anti-ai 检查项退役，不再可确认


# ── DatabaseFileBackend KV ─────────────────────────────────────────────────


def test_db_roundtrip_and_delete():
    db = DatabaseFileBackend()
    root = _tmp_root()
    assert _run_async(db.read_yaml(root, "settings/world-setting.yaml")) == {}
    _run_async(db.write_yaml(root, "settings/world-setting.yaml", {"geo": "山城"}))
    assert _run_async(db.read_yaml(root, "settings/world-setting.yaml")) == {"geo": "山城"}
    # 非 settings 路径不落 DB
    _run_async(db.write_yaml(root, "volumes/vol-1.yaml", {"volume": 1}))
    assert _run_async(db.read_yaml(root, "volumes/vol-1.yaml")) == {}
    _run_async(db.delete_file(root, "settings/world-setting.yaml"))
    assert _run_async(db.read_yaml(root, "settings/world-setting.yaml")) == {}


def test_read_yaml_tolerates_non_json_content():
    """坏行不炸整本书（2026-09-30 实锤：外部手修把裸 YAML 写进 world 行，
    readiness/拆章 AI 全 500）。非 dict 一律置空：裸 YAML 按 YAML 抢救；
    合法 JSON 但非 dict（null/标量/数组）也置空——or {} 只接得住 falsy，
    truthy 标量照样炸消费者（archive/service.py update_thread_state 无守卫）。"""
    from db import async_session
    from models.project_setting import ProjectSetting

    db = DatabaseFileBackend()
    root = _tmp_root(prefix="test_bad_content_")

    async def _seed(key: str, content: str):
        async with async_session() as session:
            session.add(ProjectSetting(root_path=root, key=key, content=content))
            await session.commit()

    # 裸 YAML（事故形状）→ 解析回 dict，数据不丢
    _run_async(_seed("world", "no_power: false\nstage: 灰港\n"))
    assert _run_async(db.read_yaml(root, "settings/world-setting.yaml")) == {
        "no_power": False,
        "stage": "灰港",
    }
    # 两种语法都救不回（空串 / 坏 YAML / 多文档）→ 空字典，不抛
    _run_async(_seed("style", ""))
    assert _run_async(db.read_yaml(root, "settings/writing-style.yaml")) == {}
    _run_async(_seed("anti-ai", "!!!bad: [unclosed"))
    assert _run_async(db.read_yaml(root, "settings/anti-ai.yaml")) == {}
    _run_async(_seed("ai-model", "a: 1\n---\nb: 2"))
    assert _run_async(db.read_yaml(root, "settings/ai-model.yaml")) == {}
    # YAML 解析成标量也不冒充 dict
    _run_async(_seed("genre", "just-a-word"))
    assert _run_async(db.read_yaml(root, "settings/genre.yaml")) == {}
    # 合法 JSON 但非 dict（null / 标量 / 数组）→ 同样置空，不透传
    _run_async(_seed("story", "null"))
    assert _run_async(db.read_yaml(root, "story.yaml")) == {}
    _run_async(_seed("status", '"just-a-string"'))
    assert _run_async(db.read_yaml(root, "settings/settings-status.yaml")) == {}
    _run_async(_seed("threads", "[1, 2]"))
    assert _run_async(db.read_yaml(root, "threads.yaml")) == {}


def test_parse_content_rejects_non_str():
    """DDL 是 NOT NULL，但手写 SQL 仍可能塞 NULL/异形——边界绝不容抛。"""
    from filesystem.db_storage import _parse_content

    assert _parse_content("./data/x", "world", None) == {}
    assert _parse_content("./data/x", "world", 123) == {}


def test_yaml_rescue_self_heals_on_next_save():
    """抢救只兜一程：读（YAML 转正为 dict）→ 正常保存 → 库里已是 JSON。"""
    from db import async_session
    from models.project_setting import ProjectSetting

    db = DatabaseFileBackend()
    root = _tmp_root(prefix="test_rescue_heal_")

    async def _seed(key: str, content: str):
        async with async_session() as session:
            session.add(ProjectSetting(root_path=root, key=key, content=content))
            await session.commit()

    _run_async(_seed("world", "stage: 灰港\n"))
    rescued = _run_async(db.read_yaml(root, "settings/world-setting.yaml"))
    assert rescued == {"stage": "灰港"}
    _run_async(db.write_yaml(root, "settings/world-setting.yaml", rescued))
    assert _run_async(db.read_yaml(root, "settings/world-setting.yaml")) == {
        "stage": "灰港"
    }

    # 库内 content 已是 JSON（抢救不再每次读都触发）
    async def _content() -> str:
        async with async_session() as session:
            row = await session.get(ProjectSetting, (root, "world"))
            return row.content

    assert _run_async(_content()) == '{"stage": "灰港"}'


# ── storage 终态契约（c-retire-local-file-storage） ────────────────────────


def test_storage_is_db_backend_unrouted_paths_noop():
    """get_storage() 即 DatabaseFileBackend（composite/盘上后端已退役）。

    settings 路由路径走 KV；非路由路径读 `{}` 写 no-op，盘上零足迹（D2）。
    """
    storage = get_storage()
    assert isinstance(storage, DatabaseFileBackend)
    root = _tmp_root()
    _run_async(storage.write_yaml(root, "settings/writing-style.yaml", {"core": "x"}))
    assert _run_async(storage.read_yaml(root, "settings/writing-style.yaml")) == {
        "core": "x"
    }
    # 非 settings 路由：读 {} 写 no-op
    _run_async(storage.write_yaml(root, "volumes/vol-1.yaml", {"volume": 1}))
    assert _run_async(storage.read_yaml(root, "volumes/vol-1.yaml")) == {}
    # 盘上零足迹；md 读写接口已随盘上后端退役
    assert not os.path.exists(os.path.join(root, "settings"))
    assert not os.path.exists(os.path.join(root, "volumes"))
    assert not hasattr(storage, "read_md")
    assert not hasattr(storage, "init_skeleton")
    assert not hasattr(storage, "delete_root")


def test_list_dir_characters_returns_yaml_names():
    storage = get_storage()
    root = _tmp_root()
    _run_async(storage.write_yaml(root, f"{CHARACTER_DIR}/a.yaml", {"name": "A"}))
    _run_async(storage.write_yaml(root, f"{CHARACTER_DIR}/b.yaml", {"name": "B"}))
    names = _run_async(storage.list_dir(root, CHARACTER_DIR))
    assert sorted(names) == ["a.yaml", "b.yaml"]  # 坑2：带 .yaml 后缀


def test_seed_settings_seeds_db_not_disk():
    """新项目种子：settings 模板只进 DB 不进盘（ADR-003）。

    种子连目录也不建——根目录 mkdir 是建书调用点的 novel-samples 锚点职责
    （c-retire-local-file-storage D3）。
    """
    root = _tmp_root(prefix="test_skeleton_")
    _run_async(seed_settings_to_db(root))

    from db import async_session
    from models.project_setting import ProjectSetting

    async def _has(key: str) -> bool:
        async with async_session() as session:
            return await session.get(ProjectSetting, (root, key)) is not None

    # DB 有模板种子行；hooks 已真表化不再种子（foreshadow-settings-v2 2.5）；
    # anti-ai 不再种子（banned-words-into-style）
    for key in ["story", "world", "style"]:
        assert _run_async(_has(key)) is True
    assert _run_async(_has("hooks")) is False
    assert _run_async(_has("anti-ai")) is False
    assert _run_async(_has("threads")) is False  # 首次归档时才建行
    # 盘上零足迹：种子不落任何文件/子目录（root 本身是 mkdtemp 建的测试容器）
    assert os.path.isdir(root)
    assert os.listdir(root) == []
