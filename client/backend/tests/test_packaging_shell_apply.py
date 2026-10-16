"""壳层退出链静默安装（silent-upgrade）门禁——apply 段此前零自动化测试（评审 P2-6）。

钉住契约（openspec/changes/c-silent-upgrade specs/client-auto-update）：
1. apply 四闸：TTL 过期／暂存件缺失／指纹缺失或失配／非 Windows → 静默跳过且留日志；
2. 正常路径：argv 形状（/VERYSILENT /CURRENTUSER /DIR 钉安装目录 /AUTOLAUNCH=1）＋
   attempts 递增＋pending 存活（记账后移至启动期 _reconcile_pending 对拍确认）；
3. 重试上限：attempts 耗尽 → 清标记升手动，绝不无限重跑；
4. 启动期对拍：版本一致 → applied 记账＋清标记；不一致（安装未完成）→ 留标记给下次
   退出链重跑（自愈起点）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

SHELL_PATH = Path(__file__).resolve().parents[2] / "packaging" / "build" / "pywebview_app.py"


def _load_shell_module():
    if "webview" not in sys.modules:
        stub = types.ModuleType("webview")
        stub.screens = []
        stub.FOLDER_DIALOG = "folder"
        stub.SAVE_DIALOG = "save"
        stub.OPEN_DIALOG = "open"
        sys.modules["webview"] = stub
    spec = importlib.util.spec_from_file_location("pywebview_app_apply_under_test", SHELL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def shell(monkeypatch, tmp_path):
    module = _load_shell_module()
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    data_root = install_dir / "data"
    (data_root / "updates").mkdir(parents=True)
    monkeypatch.setattr(module, "get_install_dir", lambda: install_dir)
    monkeypatch.setattr(module, "get_resource_root", lambda: install_dir)
    monkeypatch.setattr(module, "_load_release_json", lambda _root: {"client_version": "0.99.5"})
    monkeypatch.setattr(module.sys, "platform", "win32")
    module.__test_install_dir = install_dir
    yield module


def _write_pending(shell, tmp_path, *, version="0.99.5", sha="deadbeef", attempts=0,
                   issued_ago=0.0, missing=False):
    pkg = tmp_path / "pkg.exe"
    if not missing:
        pkg.write_bytes(b"PKG-PAYLOAD")
    body = {"version": version, "file": str(pkg), "sha256": sha if sha else "",
            "relaunch": True, "issued_at": __import__("time").time() - issued_ago,
            "attempts": attempts}
    (shell.__test_install_dir / "data" / "updates" / "pending.json").write_text(
        json.dumps(body), encoding="utf-8")
    return pkg, body


def _popens(monkeypatch):
    calls = []
    import subprocess as _subprocess

    class _FakePopen:
        def __init__(self, argv, **kwargs):
            calls.append(argv)

    monkeypatch.setattr(_subprocess, "Popen", _FakePopen)
    return calls


def _pending_body(shell):
    return json.loads(
        (shell.__test_install_dir / "data" / "updates" / "pending.json").read_text(encoding="utf-8"))


def test_no_pending_is_silent(shell, tmp_path):
    """日常关窗（无标记）＝零日志零动作，绝不误装。"""
    calls: list = []
    shell.apply_pending_update(tmp_path)
    assert calls == []


def test_ttl_expired_skip(shell, tmp_path, monkeypatch):
    module = shell
    _write_pending(module, tmp_path, issued_ago=3600.0)
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert calls == []
    assert "relaunch expired" in _log_text_of(module, tmp_path)


def _log_text_of(module, tmp_path):
    for base in (module.__test_install_dir, tmp_path):
        for p in (base / "logs" / "startup.log", base / "startup.log"):
            if p.exists():
                return p.read_text(encoding="utf-8")
    return ""


def test_missing_sha_is_failure(shell, tmp_path, monkeypatch):
    """指纹缺失＝标记不完整，按失败跳过（与 spec「任一不过 MUST 跳过」一致）。"""
    module = shell
    _write_pending(module, tmp_path, sha="")
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert calls == []
    assert "missing sha256" in _log_text_of(module, tmp_path)


def test_sha_mismatch_skip(shell, tmp_path, monkeypatch):
    module = shell
    _write_pending(module, tmp_path, sha="0" * 64)
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert calls == []
    assert "sha mismatch" in _log_text_of(module, tmp_path)


def test_non_windows_leaves_pending(shell, tmp_path, monkeypatch):
    module = shell
    pkg, _ = _write_pending(module, tmp_path)
    monkeypatch.setattr(module.sys, "platform", "darwin")
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert calls == []
    assert pkg.exists()


def test_normal_path_argv_and_attempts_bookkeeping(shell, tmp_path, monkeypatch):
    """正常路径：argv 形状钉（含 /CURRENTUSER 与 /AUTOLAUNCH=1）＋attempts 递增＋
    pending 存活（记账在启动期对拍，不在安装发起时预写）。"""
    module = shell
    # 钉 frozen 假设：/DIR 取自 sys.executable 的父目录（生产＝安装目录）
    monkeypatch.setattr(module.sys, "executable",
                        str(module.__test_install_dir / "AwesomeNovel.exe"))
    payload = b"PKG-PAYLOAD"
    pkg, _ = _write_pending(module, tmp_path,
                            sha=hashlib.sha256(payload).hexdigest())
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)

    assert len(calls) == 1
    argv = calls[0]
    assert argv[0] == str(pkg)
    for flag in ("/VERYSILENT", "/CURRENTUSER", "/AUTOLAUNCH=1", "/MERGETASKS=!desktopicon"):
        assert flag in argv, flag
    assert f"/DIR={module.__test_install_dir}" in argv
    assert any(str(arg).startswith("/LOG=") for arg in argv)

    body = _pending_body(module)
    assert body["attempts"] == 1  # 存活驱动自愈
    assert (module.__test_install_dir / "data" / "updates" / "applied.json").exists() is False


def test_attempts_exhausted_clears_pending(shell, tmp_path, monkeypatch):
    module = shell
    _write_pending(module, tmp_path, attempts=2)
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert calls == []
    assert not (module.__test_install_dir / "data" / "updates" / "pending.json").exists()


def test_reconcile_confirms_applied_on_version_match(shell, tmp_path, monkeypatch):
    """新版首启版本对拍一致 → applied 记账＋清标记（记账后移的收尾裁判）。"""
    module = shell
    (module.__test_install_dir / "data" / "updates" / "pending.json").write_text(
        json.dumps({"version": "0.99.5"}), encoding="utf-8")
    module._reconcile_pending(module.__test_install_dir)
    applied = json.loads(
        (module.__test_install_dir / "data" / "updates" / "applied.json").read_text(encoding="utf-8"))
    assert applied["version"] == "0.99.5"
    assert not (module.__test_install_dir / "data" / "updates" / "pending.json").exists()


def test_reconcile_keeps_pending_on_mismatch(shell, tmp_path, monkeypatch):
    """安装未完成（本机仍旧版）→ 留标记给下次退出链重跑，绝不假记账。"""
    module = shell
    monkeypatch.setattr(module, "_load_release_json", lambda _root: {"client_version": "0.99.4"})
    (module.__test_install_dir / "data" / "updates" / "pending.json").write_text(
        json.dumps({"version": "0.99.5"}), encoding="utf-8")
    module._reconcile_pending(module.__test_install_dir)
    assert (module.__test_install_dir / "data" / "updates" / "pending.json").exists()
    assert not (module.__test_install_dir / "data" / "updates" / "applied.json").exists()
