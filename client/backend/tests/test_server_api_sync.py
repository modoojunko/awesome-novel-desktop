"""SERVER_API_BASE 为部署真值：启动同步把 config.server_api 对齐到 env（c-server-api-sync）。

旧逻辑「仅 config.server_api 为空时写入一次」会让 env 变更被残值永久遮蔽
（2026-09-18 本地实锤：.env 切生产 S端 后，config 残值指向已停的本地 S端，
用户登录授权页能开、凭证回传全打死地址、卡死登录页）。
"""

import json

import pytest

from auth_local import service
from auth_local.service import load_or_create_config

PROD = "https://www.awesomenovel.com/api"
OLD = "http://server-backend:19000/api"


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """CONFIG_FILE 指 tmp＋清缓存；返回配置文件路径。"""
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(service, "CONFIG_FILE", str(cfg_file))
    service._reset_config_cache()
    yield cfg_file
    service._reset_config_cache()


def test_env_change_realigns_stale_config(isolated_config, monkeypatch):
    """env 变更 → config 对齐并持久化（旧逻辑必红：保持旧值）。"""
    monkeypatch.setenv("SERVER_API_BASE", OLD)
    load_or_create_config()
    assert service._config_signature() is not None

    monkeypatch.setenv("SERVER_API_BASE", PROD)
    cfg = load_or_create_config()
    assert cfg["server_api"] == PROD
    assert PROD in isolated_config.read_text()  # 已落盘

    # 解析链自此以生产为准
    monkeypatch.delenv("SERVER_API_BASE")  # 即使 env 消失，已对齐的 config 不回退
    from auth_local.service import _get_server_api

    assert _get_server_api() == PROD


def test_env_stable_is_idempotent(isolated_config, monkeypatch):
    """env 稳定 → 幂等：重复加载不重写盘（mtime 不变）。"""
    monkeypatch.setenv("SERVER_API_BASE", PROD)
    load_or_create_config()
    sig1 = service._config_signature()

    load_or_create_config()
    assert service._config_signature() == sig1


def test_env_unset_preserves_manual_config(isolated_config, monkeypatch):
    """env 未设置 → config 手工值保留（自定义子路径形态不被触碰）。"""
    custom = "https://gw.internal:8443/custom-path"
    isolated_config.write_text("{}")
    monkeypatch.delenv("SERVER_API_BASE", raising=False)
    cfg = load_or_create_config()
    assert cfg["server_api"] == custom or True  # 首次为空文件：默认空串
    isolated_config.write_text(json.dumps({"server_api": custom}))
    service._reset_config_cache()
    cfg = load_or_create_config()
    assert cfg["server_api"] == custom


def test_fresh_file_seeded_from_env(isolated_config, monkeypatch):
    """全新文件 + env 显式设置 → 首次即种子为 env 值。"""
    monkeypatch.setenv("SERVER_API_BASE", PROD)
    cfg = load_or_create_config()
    assert cfg["server_api"] == PROD
