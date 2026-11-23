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
    # 快照根/安装目录指针落点（c-update-fail-safe）：测试内收进 tmp，绝不写真实用户目录
    local_appdata = tmp_path / "localappdata"
    local_appdata.mkdir()
    monkeypatch.setattr(module, "get_local_appdata_dir", lambda: local_appdata)
    monkeypatch.setattr(module.sys, "platform", "win32")
    module.__test_install_dir = install_dir
    module.__test_local_appdata = local_appdata
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


def _simulate_runner_started(argv: list[str]) -> None:
    """模拟真 runner 的首动作：把 `runner: started` 写进执行日志。

    c-update-fail-safe 起，`_spawn_install_runner` 在 Popen 后会有界等待这行；
    正常路径用例默认模拟启动，超时/回退用例显式关掉（simulate_started=False）。
    """
    import contextlib
    import re

    if "-EncodedCommand" not in argv:
        return
    with contextlib.suppress(Exception):  # 模拟失败不改变被测契约
        encoded = argv[argv.index("-EncodedCommand") + 1]
        script = base64.b64decode(encoded).decode("utf-16-le")
        m = re.search(r"\$log = '([^']+)'", script)
        if m:
            with open(m.group(1), "a", encoding="utf-8") as f:
                f.write("2026-11-23 00:00:00 runner: started (runner_pid=1 parent=1)\n")


def _popens(monkeypatch, *, simulate_started: bool = True):
    calls = []
    import subprocess as _subprocess

    class _FakePopen:
        def __init__(self, argv, **kwargs):
            calls.append(argv)
            if simulate_started:
                _simulate_runner_started(argv)

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
    _mac_setup(module, monkeypatch)
    # 用探针桩表达「不可写」：POSIX chmod 在 Windows/管理员下不生效（Windows CI 判例）
    monkeypatch.setattr(module, "_install_dir_writable", lambda _p: False)
    pkg, _ = _write_pending(module, tmp_path,
                            sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)
    assert calls == []
    assert pkg.exists()
    assert "install dir not writable" in _log_text_of(module, tmp_path)
    assert _pending_body(module)["attempts"] == 0


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
    for flag in ("/VERYSILENT", "/CURRENTUSER", "/AUTOLAUNCH=1"):
        assert flag in script, flag
    # c-update-fail-safe §4.3：不再强制取消桌面图标任务（快捷方式改由 [Icons] 与
    # ssPostInstall 修复承接）；该参数留在 argv 会把用户已勾选的图标任务也砍掉
    assert "/MERGETASKS=!desktopicon" not in script
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


# ── c-update-detached-ps-fix：创建形态／启动痕／回退直连／安装结果回读 ──────────


def _popens_kw(monkeypatch, *, simulate_started: bool = True):
    """记录 (argv, kwargs) 的 Popen 桩（creationflags 形状对拍用；_popens 只记 argv）。"""
    calls = []
    import subprocess as _subprocess

    class _FakePopen:
        def __init__(self, argv, **kwargs):
            calls.append((argv, kwargs))
            if simulate_started:
                _simulate_runner_started(argv)

    monkeypatch.setattr(_subprocess, "Popen", _FakePopen)
    return calls


def test_win_runner_flags_create_no_window(shell, tmp_path, monkeypatch):
    """创建形态钉（2026-10-24 三次事故根因）：CREATE_NO_WINDOW 位在场、
    DETACHED_PROCESS 位不在场——DETACHED 下 powershell.exe 引擎初始化后静默死、
    脚本零执行；argv（含 -WindowStyle Hidden）不变。"""
    module = shell
    monkeypatch.setattr(module.sys, "executable",
                        str(module.__test_install_dir / "AwesomeNovel.exe"))
    _write_pending(module, tmp_path, sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    calls = _popens_kw(monkeypatch)
    module.apply_pending_update(tmp_path)

    argv, kwargs = calls[0]
    assert "powershell" in argv[0]
    flags = kwargs["creationflags"]
    import subprocess as _subprocess
    no_window = getattr(_subprocess, "CREATE_NO_WINDOW", 0x08000000)
    # DETACHED_PROCESS=0x8（POSIX 上 subprocess 无该常量，getattr 兜底 0 会把断言
    # 变空转——按字面位断言才有牙）
    assert flags & no_window
    assert not (flags & 0x8)
    assert argv[1:5] == ["-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden"]


def test_win_runner_started_line_before_wait(shell, tmp_path, monkeypatch):
    """启动痕形状：started 行引用 $log/$parent、位于 Wait-Process 之前——
    「执行体是否真的运行过」的第一判据（插早了静默失败恒缺）。"""
    module = shell
    monkeypatch.setattr(module.sys, "executable",
                        str(module.__test_install_dir / "AwesomeNovel.exe"))
    _write_pending(module, tmp_path, sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)

    script = _runner_script_of(calls)
    assert script.index("$log =") < script.index("started (runner_pid")
    assert script.index("started (runner_pid") < script.index("Wait-Process -Id $parent")


def test_mac_runner_started_line_before_wait(shell, tmp_path, monkeypatch):
    """macOS runner 同串启动痕：log() 定义后、等待循环前（spec 启动痕平台中立）。"""
    module = shell
    _mac_setup(module, monkeypatch)
    _write_pending(module, tmp_path, sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    calls = _popens_cap(monkeypatch)
    module.apply_pending_update(tmp_path)

    script = calls[0][0][2]
    assert 'log "started (runner_pid=$$ parent=$UPD_PARENT)"' in script
    assert script.index('log "started') < script.index('kill -0 "$UPD_PARENT"')


def test_runner_spawn_failure_falls_back_to_direct_installer(shell, tmp_path, monkeypatch):
    """执行体创建失败 → 回退直接 detached 拉起安装器（有代价的降级，仅此一路）；
    回退派发成功＝attempts 照递增；回退动作留痕。"""
    module = shell
    monkeypatch.setattr(module.sys, "executable",
                        str(module.__test_install_dir / "AwesomeNovel.exe"))
    payload = b"PKG-PAYLOAD"
    pkg, _ = _write_pending(module, tmp_path,
                            sha=hashlib.sha256(payload).hexdigest())
    import subprocess as _subprocess
    calls = []
    state = {"runner_alive": True}

    class _FakePopen:
        def __init__(self, argv, **kwargs):
            if state["runner_alive"] and "powershell" in str(argv[0]):
                raise OSError("spawn blocked")
            calls.append((argv, kwargs))

    monkeypatch.setattr(_subprocess, "Popen", _FakePopen)
    module.apply_pending_update(tmp_path)

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[0] == str(pkg)
    # DETACHED_PROCESS=0x8（非 Windows 测试环境 subprocess 无该常量，按字面位断言）
    assert kwargs["creationflags"] & 0x8
    # 回退留痕走 runtime_dir（apply_pending_update 的入参），不是安装目录
    startup = (tmp_path / "logs" / "startup.log").read_text("utf-8")
    assert "fallback to direct installer" in startup
    assert _pending_body(module)["attempts"] == 1


def test_runner_spawn_double_failure_keeps_pending(shell, tmp_path, monkeypatch):
    """双失败（runner 与直连都建不出）→ 异常上抛（main 兜底留日志），attempts 不
    递增——环境性故障不烧重试预算，pending 留给下次退出链重试。"""
    module = shell
    monkeypatch.setattr(module.sys, "executable",
                        str(module.__test_install_dir / "AwesomeNovel.exe"))
    _write_pending(module, tmp_path, sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    import subprocess as _subprocess

    class _AlwaysFail:
        def __init__(self, argv, **kwargs):
            raise OSError("no exec")

    monkeypatch.setattr(_subprocess, "Popen", _AlwaysFail)
    with pytest.raises(OSError):
        module.apply_pending_update(tmp_path)
    assert _pending_body(module)["attempts"] == 0


def _reconcile_mismatch(shell, monkeypatch, *, attempts, log_text=None):
    """构造「标记在场且版本未达」场景并跑对拍，返回落盘的尝试记录。"""
    module = shell
    monkeypatch.setattr(module, "_load_release_json",
                        lambda _root: {"client_version": "0.99.4"})
    (module.__test_install_dir / "data" / "updates" / "pending.json").write_text(
        json.dumps({"version": "0.99.5", "attempts": attempts}), encoding="utf-8")
    runner_log = (module.__test_install_dir / "data" / "updates"
                  / "installer-runner.log")
    if log_text is None:
        runner_log.unlink(missing_ok=True)  # None＝模拟日志不在场
    else:
        runner_log.write_text(log_text, encoding="utf-8")
    module._reconcile_pending(module.__test_install_dir)
    return json.loads(
        (module.__test_install_dir / "data" / "updates"
         / "last-install-attempt.json").read_text(encoding="utf-8"))


_WIN_ATTEMPT = ("2026-10-24 16:14:38 runner: dispatched (version=0.99.5 attempt=1)\n"
                "2026-10-24 16:14:38 runner: started (runner_pid=9 parent=1)\n"
                "2026-10-24 16:15:40 runner: wait_ms=0 parent_alive_after_wait=False "
                "installer_exit=0 install_seconds=62\n")


def test_readback_three_states(shell, monkeypatch):
    """回读三态（按派发标记取末段）：跑了且装完（exit 可见）／跑了没跑完（exit 缺）／
    派发未运行；startup.log 同步一行（失败可见的最小面）。"""
    module = shell

    rec = _reconcile_mismatch(shell, monkeypatch, attempts=1, log_text=_WIN_ATTEMPT)
    assert rec["runner_started"] is True and rec["installer_exit"] == 0
    assert rec["attempts"] == 1 and rec["version"] == "0.99.5"
    assert "recorded_at" in rec

    # 无标记的历史日志退化为全文件口径：仅 started 行＝跑了没跑完
    rec = _reconcile_mismatch(shell, monkeypatch, attempts=1,
                              log_text=_WIN_ATTEMPT.splitlines()[1] + "\n")
    assert rec["runner_started"] is True and rec["installer_exit"] is None

    rec = _reconcile_mismatch(shell, monkeypatch, attempts=1, log_text=None)
    assert rec["runner_started"] is False and rec["installer_exit"] is None
    startup = (module.__test_install_dir / "logs" / "startup.log").read_text("utf-8")
    assert "last install attempt for v0.99.5" in startup


def test_readback_mac_install_ok_and_append_last_segment(shell, monkeypatch):
    """macOS 行文 install_ok 映射退出码；按派发标记取末段——attempt 2 死在 started
    之前时，不得把 attempt 1 的 started/exit 张冠李戴到最近一次。"""
    attempt1 = ("2026-10-24 16:20:00 runner: dispatched (version=0.99.5 attempt=1)\n"
                "runner: started (runner_pid=11 parent=1)\n"
                "runner: wait_s=0 parent_alive_after_wait=0 install_ok=0 "
                "detail=hdiutil attach failed install_seconds=1 relaunched=0\n")

    rec = _reconcile_mismatch(shell, monkeypatch, attempts=1, log_text=attempt1)
    assert rec["runner_started"] is True and rec["installer_exit"] == 1

    # attempt 2：派发标记已落、runner 又静默死（日志零新增）→ 不吃 attempt 1 的痕
    attempt2_dispatched = attempt1 + ("2026-10-24 16:30:00 runner: dispatched "
                                      "(version=0.99.5 attempt=2)\n")
    rec = _reconcile_mismatch(shell, monkeypatch, attempts=2,
                              log_text=attempt2_dispatched)
    assert rec["runner_started"] is False and rec["installer_exit"] is None

    # attempt 2 完整跑完且成功 → 以末段为准
    attempt2 = attempt2_dispatched + ("runner: started (runner_pid=12 parent=1)\n"
                                      "runner: wait_s=0 parent_alive_after_wait=0 "
                                      "install_ok=1 detail= install_seconds=9 "
                                      "relaunched=1\n")
    rec = _reconcile_mismatch(shell, monkeypatch, attempts=2, log_text=attempt2)
    assert rec["runner_started"] is True and rec["installer_exit"] == 0


def test_readback_cross_update_accumulation_not_misattributed(shell, monkeypatch):
    """跨版本累积回归（评审 P2 定罪案）：installer-runner.log 永久追加而 attempts
    每版重置——上一版本的 started/exit 不得越过分发标记污染本次的「派发未执行」。"""
    history = ("2026-10-20 19:24:00 runner: started (runner_pid=77 parent=1)\n"
               "2026-10-20 19:25:00 runner: wait_ms=0 parent_alive_after_wait=False "
               "installer_exit=1 install_seconds=60\n")
    dispatched = history + ("2026-10-24 16:14:38 runner: dispatched "
                            "(version=0.99.5 attempt=1)\n")
    rec = _reconcile_mismatch(shell, monkeypatch, attempts=1, log_text=dispatched)
    assert rec["runner_started"] is False and rec["installer_exit"] is None


def test_readback_legacy_runner_without_started_line(shell, monkeypatch):
    """过渡臂：0.39 及以前的旧格式 runner 无启动痕、只有结束行（且无派发标记＝
    全文件口径）——已运行＋exit 照读，不得误标「派发未执行」。"""
    legacy = ("2026-10-24 16:15:40 runner: wait_ms=0 parent_alive_after_wait=False "
              "installer_exit=1 install_seconds=60\n")
    rec = _reconcile_mismatch(shell, monkeypatch, attempts=1, log_text=legacy)
    assert rec["runner_started"] is True and rec["installer_exit"] == 1


def test_reconcile_success_clears_stale_attempt_record(shell, monkeypatch):
    """升级成功的对拍（版本一致）→ applied＋清 pending，并清过期失败记录——
    不得常驻诊断面误报。"""
    module = shell
    updates = module.__test_install_dir / "data" / "updates"
    (updates / "pending.json").write_text(
        json.dumps({"version": "0.99.5", "attempts": 1}), encoding="utf-8")
    (updates / "last-install-attempt.json").write_text(
        json.dumps({"version": "0.99.5", "runner_started": False}), encoding="utf-8")
    module._reconcile_pending(module.__test_install_dir)
    assert (updates / "applied.json").exists()
    assert not (updates / "pending.json").exists()
    assert not (updates / "last-install-attempt.json").exists()


# ── c-mac-relaunch-frontmost：窗口呈现后自激活到前台 ──────────────────────────
# 后台来源（更新 runner 的 `open` 等）拉起的新实例不抢焦点（pywebview 6.2.1 只
# makeKeyAndOrderFront，macOS 14+ 后台启动不自行到前）——用户体感「重启更新没拉起来」
# （2026-10-26 真机定案）。壳层无条件自激活，非 darwin/AppKit 异常一律 no-op 不阻断。


def _install_fake_appkit(monkeypatch, record: dict, exc: Exception | None = None):
    appkit = types.ModuleType("AppKit")

    class _FakeNSApp:
        @staticmethod
        def activateIgnoringOtherApps_(flag):
            record["flag"] = flag
            if exc is not None:
                raise exc

    class _FakeNSApplication:
        @staticmethod
        def sharedApplication():
            return _FakeNSApp

    appkit.NSApplication = _FakeNSApplication
    monkeypatch.setitem(sys.modules, "AppKit", appkit)


def test_activate_to_front_darwin_calls_appkit(shell, monkeypatch):
    """darwin 臂：激活 API 以 True 被调用（ignoreOtherApps＝后台拉起强制到前）。"""
    record: dict = {}
    _install_fake_appkit(monkeypatch, record)
    monkeypatch.setattr(shell.sys, "platform", "darwin")
    assert shell._activate_to_front() == "front"
    assert record["flag"] is True


def test_activate_to_front_non_darwin_skips_without_import(shell, monkeypatch):
    """非 darwin 臂：直接跳过——AppKit 不被导入，Windows 链路零行为变化。"""
    record: dict = {}

    class _Spy:
        @staticmethod
        def sharedApplication():  # pragma: no cover——被调用即失败
            record["called"] = True

    appkit = types.ModuleType("AppKit")
    appkit.NSApplication = _Spy
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    monkeypatch.setattr(shell.sys, "platform", "win32")
    assert shell._activate_to_front() == "skipped"
    assert record == {}


def test_activate_to_front_appkit_failure_swallowed(shell, monkeypatch):
    """异常臂：AppKit 缺失/激活抛错吞掉返回 FAILED 串——绝不阻断启动链。"""
    _install_fake_appkit(monkeypatch, {}, exc=RuntimeError("no window server"))
    monkeypatch.setattr(shell.sys, "platform", "darwin")
    out = shell._activate_to_front()
    assert out.startswith("FAILED:") and "no window server" in out


def test_window_shown_callback_wires_activation(shell):
    """回调接线形状：shown 回调内含激活调用＋前台/失败两行启动日志。"""
    src = SHELL_PATH.read_text(encoding="utf-8")
    assert "_activate_to_front()" in src
    assert "window activated (front)" in src
    assert '"window activate " + _act' in src


# ── c-window-origin-topleft：窗口初始位置锚定主屏左上角 ───────────────────────
# create_window 此前只传 width/height，Windows 走 CW_USEDEFAULT 级联——每次拉起
# 错开一格越弹越靠右下（用户采证：更新拉起的新窗落右下角）。主屏原点直锚，
# 位置信息缺失/异常一律回退 (0, 0)，绝不阻断窗口创建。


def test_window_origin_reads_primary_screen_xy(shell):
    """6.x 臂：Screen 有 x/y——直取主屏原点（负坐标布局下 screen.x 原样透传）。"""
    screen = types.SimpleNamespace(x=120, y=80, width=2560, height=1440)
    assert shell._window_origin(screen) == (120, 80)


def test_window_origin_5x_resolution_tuple_falls_back(shell):
    """5.x 臂：仅 resolution 元组、无位置信息——回退主屏原点 (0, 0)。"""
    screen = types.SimpleNamespace(resolution=(2560, 1440))
    assert shell._window_origin(screen) == (0, 0)


def test_window_origin_broken_screen_swallowed(shell):
    """异常臂：属性访问即抛（无头环境等）——回退 (0, 0) 且不外抛。"""

    class _Boom:
        @property
        def x(self):  # pragma: no cover——被访问即抛
            raise RuntimeError("no display")

    assert shell._window_origin(_Boom()) == (0, 0)


def test_create_window_wires_origin(shell):
    """接线形状：create_window 恒传 x=/y=，位置由 _window_origin 供给。"""
    src = SHELL_PATH.read_text(encoding="utf-8")
    assert "_window_origin(" in src
    assert "x=win_x," in src
    assert "y=win_y," in src


# ── c-relaunch-version-selfreport：更新拉起新实例版本自报 ─────────────────────
# CLIENT_VERSION 经执行体环境链传染（旧实例 env → runner → open/Inno → 新实例），
# v0.43 灰度跳实证 0.43 二进制自报 0.42。修＝冻结态烘焙恒优先＋执行体环境剥 baked 键。


def test_without_baked_env_strips_baked_keys(shell):
    env = {"PATH": "/usr/bin", "SystemRoot": "C:\\Windows",
           "CLIENT_VERSION": "0.42", "CLIENT_UPDATE_URL": "u",
           "CLIENT_UPDATE_URL_FALLBACK": "uf", "SERVER_API_BASE": "a",
           "SERVER_API_FALLBACK": "af", "PUBLIC_SERVER_API": "p",
           "PORTAL_URL": "portal"}
    assert shell._without_baked_env(env) == {"PATH": "/usr/bin",
                                             "SystemRoot": "C:\\Windows"}


def test_without_baked_env_empty_dict_safe(shell):
    assert shell._without_baked_env({}) == {}


def test_without_baked_env_does_not_mutate_input(shell):
    env = {"CLIENT_VERSION": "0.42", "PATH": "/x"}
    shell._without_baked_env(env)
    assert env == {"CLIENT_VERSION": "0.42", "PATH": "/x"}


def test_version_selfreport_wiring(shell):
    """接线形状：冻结态烘焙覆盖＋boot 行冻结不读 env＋双平台 spawn 剥 baked 键。"""
    src = SHELL_PATH.read_text(encoding="utf-8")
    assert "os.environ[name] = release.get(key) or fallback" in src
    assert ('client_version_at_boot = release_at_boot.get("client_version")'
            ' or "dev"') in src
    assert "_without_baked_env(os.environ)" in src
    assert "env=_without_baked_env(" in src


# ── c-update-fail-safe：三段留痕＋启动确认回退（记录切片）────────────────────


def test_win_runner_script_three_stage_markers(shell, tmp_path, monkeypatch):
    """三段留痕形状：started →（等尸）→ 快照 → installer_start → finished。

    installer_start 必须在真正调用安装器之前；finished 在 finally 里（异常路径也写），
    含 status/exit/retry/错误摘要——「装了没装、谁失败」事后可判读。
    """
    module = shell
    monkeypatch.setattr(module.sys, "executable",
                        str(module.__test_install_dir / "AwesomeNovel.exe"))
    _write_pending(module, tmp_path, sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)

    script = _runner_script_of(calls)
    assert script.index("started (runner_pid") < script.index("Wait-Process -Id $parent")
    assert script.index("Wait-Process -Id $parent") < script.index("installer_start (attempt=")
    assert script.index("installer_start (attempt=") < script.index("& $installer")
    # 终局痕在 finally：catch 之后仍必写；异常路径记专属 status
    assert "finally {" in script
    assert script.index("} catch {") < script.index("finished (status=")
    assert "status={0} exit={1} retry={2} error={3}" in script
    assert "runner_exception" in script
    # 批二：快照在安装之前、回滚分支、失败可见（headless 开关）都在脚本里
    assert script.index("snapshot_ready") < script.index("installer_start")
    assert "$rollbackRoot" in script and "$version" in script
    assert "rollback_restored" in script and "snapshot_failed" in script
    assert "$headless" in script and "爱小说更新失败-" in script
    assert "MessageBox" in script


def test_mac_runner_finished_line(shell):
    """macOS runner 补终局痕（与 Windows 同串 runner: finished），在退出前必写。"""
    script = shell._install_runner_script_macos()
    assert 'log "finished (status=$status exit=$exit_code detail=$detail)"' in script
    assert script.index("runner: started") < script.index("finished (status=")
    assert script.rindex("finished (status=") < script.rindex("exit 1")


def test_runner_started_marker_segments_by_dispatch(shell, tmp_path):
    """回读按派发标记分段：历史 started 不冒充本次（跨版本累积日志同口径）。"""
    log = tmp_path / "r.log"
    log.write_text(
        "t runner: dispatched (version=a attempt=1)\n"
        "t runner: started (runner_pid=1 parent=1)\n"
        "t runner: dispatched (version=b attempt=1)\n",
        encoding="utf-8")
    assert shell._runner_started_since_dispatch(log) is False
    with open(log, "a", encoding="utf-8") as f:
        f.write("t runner: started (runner_pid=2 parent=1)\n")
    assert shell._runner_started_since_dispatch(log) is True
    assert shell._runner_started_since_dispatch(tmp_path / "missing.log") is False


def test_runner_started_timeout_falls_back_direct(shell, tmp_path, monkeypatch):
    """有界等待内无 started → 先杀残余进程（防双装）→ 回退直连 → 双处留痕。"""
    module = shell
    monkeypatch.setattr(module.sys, "executable",
                        str(module.__test_install_dir / "AwesomeNovel.exe"))
    monkeypatch.setattr(module, "_RUNNER_START_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(module, "_RUNNER_START_POLL_SECONDS", 0.005)
    payload = b"PKG-PAYLOAD"
    pkg, _ = _write_pending(module, tmp_path, sha=hashlib.sha256(payload).hexdigest())
    import subprocess as _subprocess
    calls = []
    killed = []

    class _FakeProc:
        def __init__(self, argv, **kwargs):
            calls.append((argv, kwargs))
            self.pid = 4242

        def poll(self):
            return None  # 进程建出来了但脚本没跑（被拦形态）

        def kill(self):
            killed.append(True)

    monkeypatch.setattr(_subprocess, "Popen", _FakeProc)
    module.apply_pending_update(tmp_path)

    assert len(calls) == 2, calls
    argv, kwargs = calls[1]
    assert argv[0] == str(pkg)
    assert kwargs["creationflags"] & 0x8  # DETACHED_PROCESS
    assert killed  # 迟起的残余 runner 被杀，避免与直连安装器双装
    runner_log = tmp_path / "installer-runner.log"  # 暂存目录＝pkg 同级（apply 的 updates_dir）
    assert "runner_fallback=direct" in runner_log.read_text("utf-8")
    startup = (tmp_path / "logs" / "startup.log").read_text("utf-8")
    assert "fallback to direct installer" in startup
    assert _pending_body(module)["attempts"] == 1


# ── c-update-fail-safe 批二：安装目录指针 / 快照清理 / 失败可见开关 ──────────


def test_install_dir_pointer_written_atomically(shell, tmp_path):
    r"""启动时原子写 {localappdata}\AwesomeNovel\install_dir.txt（安装器预填第一优先）。"""
    module = shell
    module._write_install_dir_pointer(tmp_path)
    pointer = module.__test_local_appdata / "install_dir.txt"
    assert pointer.read_text(encoding="utf-8") == str(module.__test_install_dir)
    assert not (module.__test_local_appdata / "install_dir.txt.tmp").exists()


def test_reconcile_cleans_rollback_snapshot_on_confirm(shell):
    """新版首次运行确认后清 rollback/<版本>（「装完但新版没起来」时快照保留）。"""
    module = shell
    snap = module.__test_local_appdata / "rollback" / "0.99.5"
    snap.mkdir(parents=True)
    (snap / "AwesomeNovel.exe").write_bytes(b"old")
    (module.__test_install_dir / "data" / "updates" / "pending.json").write_text(
        json.dumps({"version": "0.99.5"}), encoding="utf-8")
    module._reconcile_pending(module.__test_install_dir)
    assert not snap.exists()


def test_runner_script_carries_install_context(shell, tmp_path, monkeypatch):
    """脚本携带版本/安装目录/主程序名/headless 开关（快照与验收的输入）。"""
    module = shell
    monkeypatch.setattr(module.sys, "executable",
                        str(module.__test_install_dir / "AwesomeNovel.exe"))
    _write_pending(module, tmp_path, sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)

    script = _runner_script_of(calls)
    assert "$headless = 0" in script
    assert "$version = '0.99.5'" in script
    assert f"$installDir = '{module.__test_install_dir}'" in script
    assert "$exeName = 'AwesomeNovel.exe'" in script
    assert "$rollbackRoot" in script


def test_runner_script_headless_env_sets_flag(shell, tmp_path, monkeypatch):
    """AINOVEL_RUNNER_HEADLESS=1 → 失败只写桌面说明、不弹 MessageBox。"""
    module = shell
    monkeypatch.setattr(module.sys, "executable",
                        str(module.__test_install_dir / "AwesomeNovel.exe"))
    monkeypatch.setenv("AINOVEL_RUNNER_HEADLESS", "1")
    _write_pending(module, tmp_path, sha=hashlib.sha256(b"PKG-PAYLOAD").hexdigest())
    calls = _popens(monkeypatch)
    module.apply_pending_update(tmp_path)

    script = _runner_script_of(calls)
    assert "$headless = 1" in script
