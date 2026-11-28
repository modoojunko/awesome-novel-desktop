"""Windows 更新 runner 端到端自检（c-update-fail-safe §5）：真 PowerShell＋假安装器。

用法（Windows，CI 的 windows-latest 上跑）：
    python client/packaging/build/runner_selftest.py

覆盖五臂：
1. 一次成功           → finished status=ok retry=0；快照已建；
2. 首败重试成功       → finished status=ok retry=1；安装器被调 2 次；
3. 两次失败→快照恢复  → finished status=rollback_restored；程序树被 /MIR 恢复
                        （假安装器删掉的 marker.txt 回来；data\\ 从未进快照）；
4. GUI 子系统一次成功 → runner 必须同步等它退出后再判读（不接管道时 PowerShell
                        把 GUI 程序丢后台、$LASTEXITCODE 是快照 robocopy 的旧值，
                        会把成功安装误判成失败）；
5. GUI 子系统首败重试 → 顺序重试（第二次成功），安装器计数 2。
并断言 headless 模式下的失败说明文件落在桌面。

非 Windows 平台直接跳过（exit 0）——脚本本体只对 PowerShell/robocopy 有意义。
"""

from __future__ import annotations

import base64
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 真 Inno 安装器是 GUI 子系统：PowerShell 对 GUI 程序不等（丢后台），
# 旧 runner 的 `& $installer` 因此读到上一条 robocopy 的旧退出码。
# 这个假安装器编译成 WindowsApplication（winexe），并故意睡 1.5s——
# 不等待的 runner 会在它退出前就判失败，等待的 runner 才能拿到真实退出码。
FAKE_GUI_SOURCE = r"""
using System;
using System.IO;
using System.Threading;

public class FakeGuiInstaller
{
    public static int Main(string[] args)
    {
        string mode = Environment.GetEnvironmentVariable("FAKE_MODE") ?? "";
        string dir = Environment.GetEnvironmentVariable("FAKE_DIR") ?? ".";
        string app = Environment.GetEnvironmentVariable("FAKE_APP_DIR") ?? "";
        Thread.Sleep(1500);
        string countPath = Path.Combine(dir, "gui-count.txt");
        int n = 0;
        if (File.Exists(countPath))
        {
            int.TryParse(File.ReadAllText(countPath).Trim(), out n);
        }
        n = n + 1;
        File.WriteAllText(countPath, n.ToString());
        if (app.Length > 0)
        {
            string marker = Path.Combine(app, "marker.txt");
            if (File.Exists(marker))
            {
                File.Delete(marker);
            }
        }
        if (mode == "gui_fail_twice")
        {
            return 1;
        }
        if (mode == "gui_fail_once" && n == 1)
        {
            return 1;
        }
        return 0;
    }
}
"""

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


def _build_gui_fake_installer(out_path: Path) -> None:
    """编译 GUI 子系统（winexe）假安装器，并核 PE Subsystem==2（否则测不到本 bug）。"""
    ps = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        "$src = @'",
        FAKE_GUI_SOURCE.strip(),
        "'@",
        ("Add-Type -TypeDefinition $src -OutputAssembly $env:FAKE_GUI_OUT "
         "-OutputType WindowsApplication"),
        "$bytes = [IO.File]::ReadAllBytes($env:FAKE_GUI_OUT)",
        "$pe = [BitConverter]::ToInt32($bytes, 0x3C)",
        "$subsystem = [BitConverter]::ToUInt16($bytes, $pe + 0x5C)",
        "if ($subsystem -ne 2) { throw \"fake installer not GUI subsystem: $subsystem\" }",
    ])
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-EncodedCommand", encoded],
        env={**os.environ, "FAKE_GUI_OUT": str(out_path)},
        capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise SystemExit("build GUI fake installer failed:\n"
                         + proc.stderr.decode("utf-8", errors="replace"))


def _run_gui_arm(shell, root: Path, mode: str):
    """GUI 子系统假安装器臂：与 _run_arm 同布局，换 winexe 安装器。"""
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
    gui = installer_dir / "fake-gui-installer.exe"
    _build_gui_fake_installer(gui)

    updates = root / "updates"
    updates.mkdir()
    runner_log = updates / "installer-runner.log"

    script = shell._install_runner_script(
        _dead_pid(), [str(gui), "/S"], runner_log,
        version="9.9.9", install_dir=app, rollback_root=root / "rollback",
        exe_name="AwesomeNovel.exe", headless=True)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-EncodedCommand", encoded],
        env={**os.environ, "FAKE_MODE": mode, "FAKE_DIR": str(installer_dir),
             "FAKE_APP_DIR": str(app)},
        capture_output=True, timeout=240)
    text = runner_log.read_text(encoding="utf-8", errors="replace")
    return proc, text, app, installer_dir


def _gui_count(installer_dir: Path) -> int:
    path = installer_dir / "gui-count.txt"
    return int(path.read_text().strip()) if path.is_file() else 0


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

        # ── 臂 4：GUI 子系统安装器（真 Inno 形态）一次成功 ─────────────
        # 拖管道前：PowerShell 把 GUI 程序丢后台，$LASTEXITCODE 还是快照
        # robocopy 的旧值（成功复制＝1）→ 成功安装被误判失败并重试/回滚。
        arm = "gui_success_first"
        proc, text, app, inst = _run_gui_arm(shell, root / arm, arm)
        _check(proc.returncode == 0, f"exit={proc.returncode}", text, arm)
        _check("finished (status=ok exit=0 retry=0" in text,
               "GUI 安装器未被同步等待（status/exit 不符）", text, arm)
        _check(_gui_count(inst) == 1,
               f"GUI 安装器应只被调 1 次，实得 {_gui_count(inst)}", text, arm)
        m = re.search(r"install_seconds=(\d+)", text)
        _check(bool(m) and int(m.group(1)) >= 1,
               f"install_seconds 应 >=1（证明在等安装器），实得 "
               f"{m.group(1) if m else '?'}", text, arm)
        _check(not (app / "marker.txt").exists(), "GUI 安装器未真正执行", text, arm)
        print(f"[{arm}] PASS")

        # ── 臂 5：GUI 子系统首败重试（顺序执行，第二次成功）─────────────
        arm = "gui_fail_once"
        proc, text, app, inst = _run_gui_arm(shell, root / arm, arm)
        _check(proc.returncode == 0, f"exit={proc.returncode}", text, arm)
        _check("finished (status=ok exit=0 retry=1" in text,
               "GUI 重试臂 status/retry 不符", text, arm)
        _check(_gui_count(inst) == 2,
               f"GUI 安装器应被顺序调 2 次，实得 {_gui_count(inst)}", text, arm)
        print(f"[{arm}] PASS")

    print(f"runner selftest: {5 - failures}/5 arms passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
