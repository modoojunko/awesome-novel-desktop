"""brand.py 品牌桥测试（brand-name-single-source）。

核心是防「兜底漂移」：内置默认 MUST 与仓库根 brand/brand.json 声明值逐键一致；
env 覆盖生效、脏数据逐键回落默认且绝不抛。
"""

import importlib
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import brand  # noqa: E402


def test_defaults_match_brand_json():
    """防漂移：内置默认 == brand/brand.json（单源契约的兜底一致性）。"""
    declared = json.loads((BACKEND_DIR.parents[1] / "brand" / "brand.json").read_text("utf-8"))
    assert brand.BRAND_NAME == declared["name"]
    assert brand.BRAND_NAME_EN == declared["nameEn"]
    assert brand.BRAND_MARK == declared["mark"]
    assert brand.BRAND_TAGLINE == declared["tagline"]


def test_env_resource_root_overrides(monkeypatch, tmp_path):
    """冻结包路径：RESOURCE_ROOT 指向的资源根下 brand.json 生效。"""
    (tmp_path / "brand.json").write_text(
        json.dumps({"name": "示例名", "nameEn": "Example", "mark": "示", "tagline": "描述"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESOURCE_ROOT", str(tmp_path))
    reloaded = importlib.reload(brand)
    try:
        assert reloaded.BRAND_NAME == "示例名"
        assert reloaded.BRAND_NAME_EN == "Example"
        assert reloaded.BRAND_MARK == "示"
    finally:
        monkeypatch.delenv("RESOURCE_ROOT")
        importlib.reload(brand)


def test_dirty_values_fall_back_per_key(monkeypatch, tmp_path):
    """脏数据逐键回落默认：非字符串/空白串/缺键都不得抛、不得上屏。"""
    (tmp_path / "brand.json").write_text(
        json.dumps({"name": 123, "nameEn": "  ", "mark": "示"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESOURCE_ROOT", str(tmp_path))
    reloaded = importlib.reload(brand)
    try:
        assert reloaded.BRAND_NAME == brand._DEFAULTS["name"]
        assert reloaded.BRAND_NAME_EN == brand._DEFAULTS["nameEn"]
        assert reloaded.BRAND_MARK == "示"
        assert reloaded.BRAND_TAGLINE == brand._DEFAULTS["tagline"]
    finally:
        monkeypatch.delenv("RESOURCE_ROOT")
        importlib.reload(brand)


def test_shallow_layout_never_raises(monkeypatch):
    """扁平布局回归（docker /app/brand.py 实锤过）：祖先目录不足 3 层时
    _candidate_dirs MUST 静默跳过 dev 候选而非 IndexError 炸 import。"""
    monkeypatch.setattr(brand, "__file__", "/app/brand.py")
    dirs = brand._candidate_dirs()  # 不得抛
    assert isinstance(dirs, list)


def test_missing_file_falls_back_to_defaults(monkeypatch, tmp_path):
    """文件缺失静默回落内置默认（启动路径零阻塞纪律）。

    注意顺序：先 reload 再打补丁——reload 重执行源码会把 _candidate_dirs
    重定义回真身，先 patch 后 reload 补丁会静默丢失（评审 P3）。
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("RESOURCE_ROOT", str(empty))
    importlib.reload(brand)  # 在 RESOURCE_ROOT 指向空目录的真实定位路径上重载
    monkeypatch.setattr(brand, "_candidate_dirs", lambda: [empty])
    reloaded = brand._load()
    monkeypatch.delenv("RESOURCE_ROOT")
    assert reloaded == brand._DEFAULTS
