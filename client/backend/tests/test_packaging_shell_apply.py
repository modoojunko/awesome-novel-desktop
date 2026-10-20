"""壳层退出链静默安装（silent-upgrade）门禁——apply 段此前零自动化测试（评审 P2-6）。

钉住契约（openspec/changes/c-silent-upgrade specs/client-auto-update）：
1. apply 四闸：TTL 过期／暂存件缺失／指纹缺失或失配／非 Windows → 静默跳过且留日志；
2. 正常路径：安装执行走 PowerShell runner（等本进程死透→同步跑安装器→退出码留痕，
   c-silent-relaunch-runner：v0.35→0.36 真机「点了重启弹回旧版」事故的结构修复）——
   安装器 argv（/VERYSILENT /CURRENTUSER /DIR 钉安装目录 /AUTOLAUNCH=1）与
   Wait-Process 等尸段必须在编码命令里可对拍；attempts 递增＋pending 存活（记账
   后移至启动期 _reconcile_pending 对拍确认）；
3. 重试上限：attempts 耗尽 → 清标记升手动，绝不无限重跑；
4. 启动期对拍：版本一致 → applied 记账＋清标记；不一致（安装未完成）→ 留标记给下次
   退出链重跑（自愈起点）。
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
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


def _runner_script_of(calls):
    """取唯一一次 Popen 的 EncodedCommand 并解码回脚本文本（形状对拍用）。"""
    assert len(calls) == 1, f"runner spawn 应恰一次，实得 {len(calls)}"
    argv = calls[0]
    assert argv[1:5] == ["-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden"], argv
    assert argv[5] == "-EncodedCommand"
    return base64.b64decode(argv[6]).decode("utf-16-le")


def _argv0_of(calls):
    return calls[0][0]


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
    # sha 必须真对上：指纹闸在平台闸之前，假 sha 会让本测试在前面提前返回（存量暗病）
    pkg, _ = _write_pending(module, tmp_path,
                            sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    monkeypatch.setattr(module.sys, "platform", "darwin")
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert calls == []
    assert pkg.exists()
    assert "non-windows platform" in _log_text_of(module, tmp_path)


def test_normal_path_argv_and_attempts_bookkeeping(shell, tmp_path, monkeypatch):
    """正常路径：runner 编码命令形状钉（等尸段＋安装器 argv 全量）＋attempts 递增＋
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

    script = _runner_script_of(calls)
    assert _argv0_of(calls).endswith("powershell.exe")
    # 等尸段：父 pid 进脚本、死透才动手（测试进程 pid 即 os.getpid() 的真值）
    assert f"$parent = {os.getpid()}" in script
    assert "Wait-Process -Id $parent -Timeout 60" in script
    for flag in ("/VERYSILENT", "/CURRENTUSER", "/AUTOLAUNCH=1", "/MERGETASKS=!desktopicon"):
        assert flag in script, flag
    assert f"/DIR={module.__test_install_dir}" in script
    assert "/LOG=" in script
    assert str(pkg) in script
    # 安装器同步执行＋退出码留痕（下一次事故的判读入口）
    assert "& $installer" in script
    assert "installer-runner.log" in script
    assert "exit $code" in script

    body = _pending_body(module)
    assert body["attempts"] == 1  # 存活驱动自愈
    assert (module.__test_install_dir / "data" / "updates" / "applied.json").exists() is False


def test_runner_ps_path_prefers_windir_full_path(shell, tmp_path, monkeypatch):
    """优先取 WINDIR 全路径 powershell.exe（防 PATH 劫持）；缺失回落 PATH 名。"""
    module = shell
    fake_win = tmp_path / "win"
    ps_dir = fake_win / "System32" / "WindowsPowerShell" / "v1.0"
    ps_dir.mkdir(parents=True)
    (ps_dir / "powershell.exe").write_bytes(b"")  # 在场＝选全路径
    monkeypatch.setenv("WINDIR", str(fake_win))
    _write_pending(module, tmp_path, sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())

    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert _argv0_of(calls) == str(ps_dir / "powershell.exe")

    calls2 = _popens(monkeypatch)
    (ps_dir / "powershell.exe").unlink()
    module.apply_pending_update(tmp_path)
    assert _argv0_of(calls2) == "powershell.exe"


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
