"""config.json 原子写的占用韧性（c-shell-hang-hardening 4.x）。

现场（2026-10-06 用户机 uvicorn.log）：固定 tmp 名 + 零重试，一次瞬时句柄冲突
（`PermissionError [WinError 32]`：杀软实时扫描 / 他进程短暂持锁）就把 `check-auth`
放大成用户可见的 500。本组钉住契约：

1. 临时文件名每次唯一（并发写不互踩）；
2. 瞬时占用由短退避重试吸收（每次失败留 warn）；
3. 重试仍失败必须**抛出**（不许静默吞——那会造成"文件没落盘、缓存却报成功"的状态丢失）；
4. 无论成败都不留 `.tmp` 残件，内存缓存只在成功后更新。
"""
from __future__ import annotations

import json
import os

import pytest

from auth_local import service as svc


@pytest.fixture()
def cfg_paths(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(svc, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(svc, "CONFIG_FILE", str(cfg))
    monkeypatch.setattr(svc, "_config_cache", {"token": "old"})
    monkeypatch.setattr(svc, "_config_cache_sig", None)
    return cfg


def test_save_local_config_retries_transient_sharing_violation(cfg_paths, monkeypatch):
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(32, "另一个程序正在使用此文件，进程无法访问。")
        return real_replace(src, dst)

    monkeypatch.setattr(svc.os, "replace", flaky)
    monkeypatch.setattr(svc.time, "sleep", lambda _s: None)

    svc.save_local_config({"token": "t1"})

    assert calls["n"] == 2, "瞬时占用应被重试吸收（现场那次就是这种形态）"
    assert json.loads(cfg_paths.read_text(encoding="utf-8")) == {"token": "t1"}
    assert not list(cfg_paths.parent.glob("*.tmp")), "成功路径不留 tmp"
    assert svc._config_cache == {"token": "t1"}, "成功后缓存必须与文件一致"


def test_save_local_config_raises_after_retries_and_cleans_tmp(cfg_paths, monkeypatch):
    def always_busy(_src, _dst):
        raise PermissionError(32, "一直被占用")

    monkeypatch.setattr(svc.os, "replace", always_busy)
    monkeypatch.setattr(svc.time, "sleep", lambda _s: None)

    with pytest.raises(PermissionError):
        svc.save_local_config({"token": "t2"})

    assert not list(cfg_paths.parent.glob("*.tmp")), "失败路径必须清掉自己的 tmp"
    assert svc._config_cache == {"token": "old"}, "写失败不许更新缓存（防文件/缓存漂移）"
    assert not cfg_paths.exists(), "写失败不能留下半截正式文件"


def test_save_local_config_uses_unique_tmp_names(cfg_paths, monkeypatch):
    seen: list[str] = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append(str(src))
        return real_replace(src, dst)

    monkeypatch.setattr(svc.os, "replace", spy)

    svc.save_local_config({"a": 1})
    svc.save_local_config({"a": 2})

    assert len(seen) == 2 and len(set(seen)) == 2, "两次写的 tmp 名必须唯一（并发/多实例不互踩）"
    assert json.loads(cfg_paths.read_text(encoding="utf-8")) == {"a": 2}


def test_save_local_config_warns_on_each_retry(cfg_paths, monkeypatch, caplog):
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(32, "占用中")
        return real_replace(src, dst)

    monkeypatch.setattr(svc.os, "replace", flaky)
    monkeypatch.setattr(svc.time, "sleep", lambda _s: None)

    with caplog.at_level("WARNING", logger=svc.logger.name):
        svc.save_local_config({"token": "t3"})

    assert calls["n"] == 3
    assert any("config.json 被占用" in r.message or "被占用" in r.getMessage() for r in caplog.records), (
        "每次重试都必须留痕——现场据此区分杀软瞬态与他进程长期持锁"
    )
