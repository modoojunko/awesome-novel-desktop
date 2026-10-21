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
    """自动链未覆盖的平台（如 linux）：指纹闸在平台闸之前（假 sha 会提前返回），到闸后
    留 pending 不动手回手动链。"""
    module = shell
    pkg, _ = _write_pending(module, tmp_path,
                            sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    monkeypatch.setattr(module.sys, "platform", "linux")
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert calls == []
    assert pkg.exists()
    assert "platform linux not supported by auto chain" in _log_text_of(module, tmp_path)


# ── macOS 分派（c-mac-autoupdate）：DMG 挂载＋bundle 原子换装＋bash runner ──────

def _mac_setup(module, monkeypatch):
    """darwin 态＋假 .app 布局；返回 (bundle, fake_exe)。"""
    monkeypatch.setattr(module.sys, "platform", "darwin")
    bundle = module.__test_install_dir / "Applications" / "AwesomeNovel.app"
    exe = bundle / "Contents" / "MacOS" / "AwesomeNovel"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(module.sys, "executable", str(exe))
    return bundle, exe


def _popens_cap(monkeypatch):
    """记录 (argv, kwargs) 的 Popen 桩（mac runner 的 env 形状对拍用）。"""
    calls = []
    import subprocess as _subprocess

    class _FakePopen:
        def __init__(self, argv, **kwargs):
            calls.append((argv, kwargs))

    monkeypatch.setattr(_subprocess, "Popen", _FakePopen)
    return calls


def test_macos_normal_path_runner_script_env_and_attempts(shell, tmp_path, monkeypatch):
    """macOS 正常路径：/bin/bash runner＋env 形状钉（等尸段/DMG 链/换装段/拉起段全量
    可对拍）＋attempts 递增＋pending 存活。"""
    module = shell
    bundle, _exe = _mac_setup(module, monkeypatch)
    payload = b"PKG-PAYLOAD"
    pkg, _ = _write_pending(module, tmp_path,
                            sha=hashlib.sha256(payload).hexdigest())
    calls = _popens_cap(monkeypatch)
    module.apply_pending_update(tmp_path)

    assert len(calls) == 1, f"runner spawn 应恰一次，实得 {len(calls)}"
    argv, kwargs = calls[0]
    assert argv[:2] == ["/bin/bash", "-c"]
    script = argv[2]
    # 等尸段：有界 60s（0.25s×240）＋结果变量（弹回类事故判读的第一分辨点）
    assert 'kill -0 "$UPD_PARENT"' in script
    assert "-ge 240" in script and "sleep 0.25" in script
    assert "parent_alive_after_wait=" in script and "wait_s=" in script
    # DMG 链：只读挂载→找 .app→ditto 复制→签名完整性硬闸
    assert "hdiutil attach -nobrowse -readonly -noautoopen -mountpoint" in script
    assert "ditto" in script
    # 隔离标记兜底（mac-gatekeeper-quarantine-diagnosis）：复制后清 quarantine，
    # 再验签——「换完启动被 Gatekeeper 拦」绝不留给用户
    assert 'xattr -cr "$stage"' in script
    assert "codesign --verify --strict" in script
    # 原子换装＋失败回滚＋卸载
    assert 'mv "$UPD_BUNDLE" "$old"' in script
    assert 'mv "$stage" "$UPD_BUNDLE"' in script
    assert 'mv "$old" "$UPD_BUNDLE"' in script  # 回滚臂
    assert "hdiutil detach" in script
    # 安装成功才拉起＋退出码语义
    assert 'open "$UPD_BUNDLE"' in script
    assert '[ "$ok" -eq 1 ] && exit 0' in script
    # 零转义面：可变数据（含 runner 日志路径）全走 env，不拼进脚本文本
    assert "installer-runner.log" not in script
    env = kwargs["env"]
    assert env["UPD_PARENT"] == str(os.getpid())
    assert Path(env["UPD_DMG"]) == pkg
    assert Path(env["UPD_BUNDLE"]) == bundle.resolve()
    assert env["UPD_RUNNER_LOG"].endswith("installer-runner.log")
    assert env["UPD_RELAUNCH"] == "1"
    assert kwargs.get("start_new_session") is True

    body = _pending_body(module)
    assert body["attempts"] == 1
    assert (module.__test_install_dir / "data" / "updates" / "applied.json").exists() is False


def test_macos_relaunch_flag_passthrough(shell, tmp_path, monkeypatch):
    """pending.relaunch=false → UPD_RELAUNCH=0（runner 装完不拉起）。"""
    module = shell
    _mac_setup(module, monkeypatch)
    _pkg, body = _write_pending(module, tmp_path,
                                sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    body["relaunch"] = False
    (module.__test_install_dir / "data" / "updates" / "pending.json").write_text(
        json.dumps(body), encoding="utf-8")
    calls = _popens_cap(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert len(calls) == 1
    assert calls[0][1]["env"]["UPD_RELAUNCH"] == "0"


def test_macos_bundle_not_detected_skips(shell, tmp_path, monkeypatch):
    """非 .app 形态（dev 态裸 python）：无安装位可钉 → 静默跳过留日志、pending 保留。"""
    module = shell
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(module.sys, "executable", str(tmp_path / "venv" / "bin" / "python"))
    pkg, _ = _write_pending(module, tmp_path,
                            sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert calls == []
    assert pkg.exists()
    assert ".app bundle not detected" in _log_text_of(module, tmp_path)
    assert _pending_body(module)["attempts"] == 0


def test_macos_install_dir_not_writable_skips(shell, tmp_path, monkeypatch):
    """安装目录探针不可写（典型：非 admin 装于 /Applications）：spawn 前跳过回手动链，
    不 spawn 执行体、pending 保留。"""
    module = shell
    bundle, _exe = _mac_setup(module, monkeypatch)
    bundle.parent.chmod(0o555)
    try:
        pkg, _ = _write_pending(module, tmp_path,
                                sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
        calls = _popens(monkeypatch)
        module.apply_pending_update(tmp_path)
        assert calls == []
        assert pkg.exists()
        assert "install dir not writable" in _log_text_of(module, tmp_path)
        assert _pending_body(module)["attempts"] == 0
    finally:
        bundle.parent.chmod(0o755)


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
    # 等待段结果必须落盘（评审 P3：弹回旧版类事故判读的第一分辨点）
    assert "$waitMs" in script and "$parentAlive" in script
    assert "parent_alive_after_wait=" in script
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
