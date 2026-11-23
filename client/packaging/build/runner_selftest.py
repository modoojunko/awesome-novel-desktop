"""Windows 更新 runner 端到端自检（c-update-fail-safe §5）：真 PowerShell＋假安装器。

用法（Windows，CI 的 windows-latest 上跑）：
    python client/packaging/build/runner_selftest.py

覆盖三臂：
1. 一次成功           → finished status=ok retry=0；快照已建；
2. 首败重试成功       → finished status=ok retry=1；安装器被调 2 次；
3. 两次失败→快照恢复  → finished status=rollback_restored；程序树被 /MIR 恢复
                        （假安装器删掉的 marker.txt 回来；data\\ 从未进快照）；
并断言 headless 模式下的失败说明文件落在桌面。

非 Windows 平台直接跳过（exit 0）——脚本本体只对 PowerShell/robocopy 有意义。
"""

from __future__ import annotations

import base64
import importlib.util
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent

FAKE_INSTALLER = r"""@echo off
set DIR=%~dp0
set /a N=0
if exist "%DIR%count.txt" set /p N=<"%DIR%count.txt"
set /a N=%N%+1
rem 前缀式重定向 + echo(：避免 `echo 1>...` 的 1 被 cmd 当成句柄重定向
> "%DIR%count.txt" echo(%N%
>> "%DIR%calls.txt" echo call %N%
rem 模拟「装到一半」：删掉程序树里的一个文件（回滚臂断言它被恢复）
del "%DIR%..\app\marker.txt" >nul 2>&1
if "%FAKE_MODE%"=="success_first" exit /b 0
if "%FAKE_MODE%"=="fail_twice" exit /b 1
rem 默认 fail_once：第一次失败、第二次成功（重试臂）
if %N%==1 exit /b 1
exit /b 0
"""


def _load_shell():
    if "webview" not in sys.modules:
        stub = types.ModuleType("webview")
        stub.screens = []
        sys.modules["webview"] = stub
    spec = importlib.util.spec_from_file_location(
        "pywebview_app_selftest", HERE / "pywebview_app.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dead_pid() -> int:
    """拿一个「曾经存在、现已退出」的 pid：runner 的 Wait-Process 立即放行。"""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    pid = proc.pid
    proc.wait(timeout=30)
    return pid


def _run_arm(shell, root: Path, mode: str):
    app = root / "app"
    app.mkdir(parents=True)
    (app / "AwesomeNovel.exe").write_bytes(b"OLD-EXE")
    (app / "marker.txt").write_bytes(b"must-survive-rollback")
    (app / "data").mkdir()
    (app / "data" / "novel.db").write_bytes(b"BOOKS")
    (app / "logs").mkdir()
    (app / "logs" / "startup.log").write_text("keep", encoding="utf-8")

    installer_dir = root / "installer"
    installer_dir.mkdir()
    fake = installer_dir / "fake-installer.cmd"
    fake.write_text(FAKE_INSTALLER, encoding="utf-8")

    updates = root / "updates"
    updates.mkdir()
    runner_log = updates / "installer-runner.log"

    script = shell._install_runner_script(
        _dead_pid(), [str(fake), "/S"], runner_log,
        version="9.9.9", install_dir=app, rollback_root=root / "rollback",
        exe_name="AwesomeNovel.exe", headless=True)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-EncodedCommand", encoded],
        env={**os.environ, "FAKE_MODE": mode},
        capture_output=True, timeout=240)
    text = runner_log.read_text(encoding="utf-8", errors="replace")
    return proc, text, app


def _check(cond: bool, what: str, log_text: str, arm: str) -> None:
    if not cond:
        raise SystemExit(f"[{arm}] FAIL: {what}\n---- runner log ----\n{log_text}")


def main() -> int:
    if sys.platform != "win32":
        print("runner selftest: skipped (non-Windows)")
        return 0

    shell = _load_shell()
    failures = 0
    with tempfile.TemporaryDirectory(prefix="runner-selftest-") as tmp:
        root = Path(tmp)

        # ── 臂 1：一次成功 ──────────────────────────────────────────────
        arm = "success_first"
        proc, text, app = _run_arm(shell, root / arm, arm)
        _check(proc.returncode == 0, f"exit={proc.returncode}", text, arm)
        _check("started (runner_pid=" in text, "缺启动痕", text, arm)
        _check("snapshot_ready" in text, "缺快照行", text, arm)
        _check("installer_start (attempt=1" in text, "缺安装开始行", text, arm)
        _check("finished (status=ok exit=0 retry=0" in text, "终局痕不符", text, arm)
        _check((root / arm / "rollback" / "9.9.9").is_dir(), "快照目录不在", text, arm)
        _check((app / "data" / "novel.db").read_bytes() == b"BOOKS", "data 被改动", text, arm)
        print(f"[{arm}] PASS")

        # ── 臂 2：首败重试成功 ─────────────────────────────────────────
        arm = "fail_once"
        proc, text, app = _run_arm(shell, root / arm, arm)
        calls = (root / arm / "installer" / "calls.txt").read_text().count("call")
        _check(proc.returncode == 0, f"exit={proc.returncode}", text, arm)
        _check(calls == 2, f"安装器应被调 2 次，实得 {calls}", text, arm)
        _check("finished (status=ok exit=0 retry=1" in text, "重试计数不符", text, arm)
        _check(not (app / "marker.txt").exists(), "成功路径不应做快照恢复", text, arm)
        print(f"[{arm}] PASS")

        # ── 臂 3：两次失败→快照恢复 ─────────────────────────────────────
        arm = "fail_twice"
        proc, text, app = _run_arm(shell, root / arm, arm)
        _check(proc.returncode != 0, "两次失败应返回非 0", text, arm)
        _check("finished (status=rollback_restored" in text, "回滚状态不符", text, arm)
        _check((app / "marker.txt").read_bytes() == b"must-survive-rollback",
               "程序树未被快照恢复", text, arm)
        _check((app / "data" / "novel.db").read_bytes() == b"BOOKS",
               "恢复过程动了 data\\", text, arm)
        desk = Path(os.path.expanduser("~")) / "Desktop"
        if desk.is_dir():
            found = sorted(desk.glob("爱小说更新失败-*.txt"))
            _check(bool(found), "缺桌面失败说明", text, arm)
            for f in found:
                f.unlink(missing_ok=True)
        print(f"[{arm}] PASS")

    print(f"runner selftest: {3 - failures}/3 arms passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
