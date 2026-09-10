"""DatabaseFileBackend / CompositeStorageBackend 契约测试（ADR-001/002/003）。

依赖 conftest 会话级临时库基座（建表完成，含 project_settings）。
用独立临时 root_path 隔离，不落真实磁盘项目目录。
"""

import asyncio
import os
import tempfile

from filesystem.composite_storage import CompositeStorageBackend
from filesystem.db_storage import DatabaseFileBackend
from filesystem.paths import (
    CHARACTER_DIR,
    KEY_TO_PATH,
    PATH_TO_KEY,
    route_relative_path,
)


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
    # 非 settings 路径 → None（走 LocalFileBackend）
    assert route_relative_path("volumes/vol-1.yaml") is None
    assert route_relative_path("chapters/vol-1-ch-1.yaml") is None
    assert route_relative_path("prompts/p.md") is None
    # threads.yaml → KV 专用路由（PR④）；不得进 PATH_TO_KEY（会泄漏 /settings/threads 端点）
    assert route_relative_path("threads.yaml") == "threads"
    assert "threads.yaml" not in PATH_TO_KEY
    assert len(PATH_TO_KEY) == 8  # 坑1：9 类含 8 单文件 + 字符目录前缀
    assert set(KEY_TO_PATH) == set(PATH_TO_KEY.values())


def test_single_file_types_derivation():
    """settings/router.py SINGLE_FILE_TYPES 推导来源契约（去 story/status 后的 6 项单文件 CRUD）。"""
    from settings.router import SINGLE_FILE_TYPES

    assert set(KEY_TO_PATH) - {"story", "status"} == {
        "world", "style", "anti-ai", "hooks", "genre", "ai-model",
    }
    assert SINGLE_FILE_TYPES == set(KEY_TO_PATH) - {"story", "status"}
    assert "characters" not in SINGLE_FILE_TYPES


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
        "anti-ai",
        "hooks",
        "characters",
    }


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


# ── Composite 路由分派 ─────────────────────────────────────────────────────


def test_composite_routes_settings_to_db_rest_to_local():
    comp = CompositeStorageBackend()
    root = _tmp_root()
    _run_async(comp.write_yaml(root, "settings/writing-style.yaml", {"core": "x"}))
    _run_async(comp.write_yaml(root, "volumes/vol-1.yaml", {"volume": 1}))
    assert _run_async(comp.read_yaml(root, "settings/writing-style.yaml")) == {"core": "x"}
    assert _run_async(comp.read_yaml(root, "volumes/vol-1.yaml")) == {"volume": 1}
    # settings 只进 DB：磁盘无该 yaml；卷进磁盘
    assert not os.path.exists(os.path.join(root, "settings", "writing-style.yaml"))
    assert os.path.exists(os.path.join(root, "volumes", "vol-1.yaml"))
    # md 显式走文件（坑3）
    _run_async(comp.write_md(root, "prompts/p.md", "hello"))
    assert _run_async(comp.read_md(root, "prompts/p.md")) == "hello"


def test_list_dir_characters_returns_yaml_names():
    comp = CompositeStorageBackend()
    root = _tmp_root()
    _run_async(comp.write_yaml(root, f"{CHARACTER_DIR}/a.yaml", {"name": "A"}))
    _run_async(comp.write_yaml(root, f"{CHARACTER_DIR}/b.yaml", {"name": "B"}))
    _run_async(comp.write_yaml(root, "volumes/vol-1.yaml", {"volume": 1}))
    names = _run_async(comp.list_dir(root, CHARACTER_DIR))
    assert sorted(names) == ["a.yaml", "b.yaml"]  # 坑2：带 .yaml 后缀


def test_delete_root_clears_rows_and_dir():
    comp = CompositeStorageBackend()
    root = _tmp_root()
    _run_async(comp.write_yaml(root, "settings/hooks.yaml", {"active": []}))
    _run_async(comp.write_yaml(root, f"{CHARACTER_DIR}/a.yaml", {"name": "A"}))
    _run_async(comp.write_yaml(root, "threads.yaml", {"threads": {}}))
    assert _run_async(comp.read_yaml(root, "settings/hooks.yaml")) == {"active": []}
    _run_async(comp.delete_root(root))
    # 坑4：清行再 rmtree
    assert _run_async(comp.read_yaml(root, "settings/hooks.yaml")) == {}
    assert _run_async(comp.list_dir(root, CHARACTER_DIR)) == []
    assert not os.path.exists(root)


def test_init_skeleton_seeds_db_not_disk():
    comp = CompositeStorageBackend()
    root = _tmp_root(prefix="test_skeleton_")
    _run_async(comp.init_skeleton(root))
    # DB 有 5 类模板种子行（ADR-003）
    db = DatabaseFileBackend()
    for key in ["story", "world", "style", "anti-ai", "hooks"]:
        assert _run_async(db.has_key(root, key)) is True
    # 磁盘无 settings yaml（ADR-003：只进 DB 不进盘）
    assert not os.path.exists(os.path.join(root, "settings", "writing-style.yaml"))
    # PR⑤ 大扫除后盘上只剩项目根目录：无骨架文件/子目录
    assert os.path.isdir(root)
    assert os.listdir(root) == []
    assert not os.path.exists(os.path.join(root, "threads.yaml"))
    assert _run_async(db.has_key(root, "threads")) is False  # 首次归档时才建行
