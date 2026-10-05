"""壳层启动链门禁（shell-startup-diagnostics）。

现场形态：Windows 包「长期停在启动页」，而 startup.log 空无一字——旧壳有两条
静默失败路径（server 线程死在 try 之外 / 轮询线程异常），事后只能靠猜。
本组测试钉住修复后的契约：

1. 后端线程一退出，健康轮询立即判负（不干等满 60 秒）；
2. 数据目录建不出来（典型：Program Files 无写权限）必须落 FATAL＋traceback；
3. 启动失败页必须同时带 startup.log 与 uvicorn.log 尾段（真实死因在后者的日子居多）；
4. 轮询线程任何异常都不得静默——落日志并尽力装错误页；
5. 应用页装载看门狗：超时→日志＋浏览器兜底＋错误页；
6. main() 启动即清陈旧 port.json（多开/上次崩半途时它会把轮询引到旧进程）；
7. 运行目录换名 AI Novel → AwesomeNovel：macOS 上该目录即书稿数据目录，迁移必须
   原子换名＋旧路径留软链（装回旧版仍能找到书），失败退回旧目录绝不丢数据。

pywebview_app.py 带模块级 `import webview`（GUI 框架在 Linux CI 上不可导入），
故经 stub 加载源码模块，只测启动链的纯逻辑分支。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
import types
from pathlib import Path
from typing import ClassVar

import pytest

SHELL_PATH = Path(__file__).resolve().parents[2] / "packaging" / "build" / "pywebview_app.py"


def _load_shell_module():
    """以 stub 的 webview 模块加载壳层源码（不触发任何 GUI 初始化）。"""
    if "webview" not in sys.modules:
        stub = types.ModuleType("webview")
        stub.screens = []
        stub.FOLDER_DIALOG = "folder"
        stub.SAVE_DIALOG = "save"
        stub.OPEN_DIALOG = "open"
        sys.modules["webview"] = stub
    spec = importlib.util.spec_from_file_location("pywebview_app_under_test", SHELL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def shell():
    module = _load_shell_module()
    module._server_exited.clear()
    yield module
    module._server_exited.clear()


class _FakeEvent:
    def __init__(self, flag: bool = True):
        self.flag = flag
        self.handlers: list = []

    def wait(self, timeout=None):
        return self.flag

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self


class _FakeEvents:
    def __init__(self, loaded: bool = True):
        self.loaded = _FakeEvent(loaded)
        self.shown = _FakeEvent(True)


class _FakeWindow:
    """记录 load_url 调用；可令其抛错模拟「窗口未 shown / UI 挂死」。"""

    def __init__(self, loaded: bool = True):
        self.events = _FakeEvents(loaded=loaded)
        self.urls: list[str] = []

    def load_url(self, url: str):
        self.urls.append(url)


def _log_text(appdata: Path) -> str:
    return (appdata / "startup.log").read_text(encoding="utf-8")


# ── 1. 早失败：后端线程死了就不再干等 ──────────────────────────────────────


def test_wait_for_server_fails_fast_when_server_thread_exited(shell, tmp_path):
    shell._server_exited.set()
    start = time.time()
    assert shell.wait_for_server(tmp_path, timeout=30) is None
    assert time.time() - start < 5, "后端线程已死仍干等——早失败契约破了"


def test_wait_for_server_returns_port_when_health_ok(shell, tmp_path, monkeypatch):
    (tmp_path / "port.json").write_text(json.dumps({"port": 18999}), encoding="utf-8")

    class _Resp:
        status = 200

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    assert shell.wait_for_server(tmp_path, timeout=5) == 18999


# ── 2. 数据目录建不出来必须留痕 ────────────────────────────────────────────


def test_start_server_logs_fatal_when_dirs_unwritable(shell, tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")  # 让 mkdir 必然失败
    monkeypatch.setattr(shell, "get_appdata", lambda: appdata)
    monkeypatch.setattr(shell, "get_install_dir", lambda: blocker / "AI Novel")

    shell.start_server()

    text = _log_text(appdata)
    assert "FATAL preparing dirs" in text
    assert "Traceback" in text
    assert shell._server_exited.is_set()


# ── 3. 错误页要带两份日志 ──────────────────────────────────────────────────


def test_error_page_carries_both_logs(shell, tmp_path):
    (tmp_path / "startup.log").write_text("[t] server thread FATAL: boom", encoding="utf-8")
    (tmp_path / "uvicorn.log").write_text("ERROR: lifespan crashed <x>", encoding="utf-8")

    err = shell.write_error_page(tmp_path, "后端启动超时")

    html = err.read_text(encoding="utf-8")
    assert "启动失败" in html
    assert "server thread FATAL: boom" in html
    assert "lifespan crashed" in html
    assert "&lt;x&gt;" in html, "日志内容必须转义"
    assert str(tmp_path) in html


# ── 4/5. 轮询线程：异常不静默、装载超时有兜底 ─────────────────────────────


def test_navigate_success_logs_app_loaded(shell, tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: 18123)
    window = _FakeWindow(loaded=True)

    shell.check_backend_and_navigate(window, tmp_path)

    text = _log_text(tmp_path)
    assert "backend ready (port 18123)" in text
    assert "app page loaded" in text
    assert window.urls == ["http://127.0.0.1:18123"]


def test_navigate_failure_is_logged_and_error_page_shown(shell, tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: 18124)

    class _WindowFirstLoadRaises(_FakeWindow):
        """首次 load_url（应用页）抛错，第二次（错误页）成功——模拟窗口未 shown。"""

        def load_url(self, url: str):
            if not self.urls:
                self.urls.append(url)
                raise RuntimeError("WebViewException: Main window failed to start")
            self.urls.append(url)

    window = _WindowFirstLoadRaises()
    shell.check_backend_and_navigate(window, tmp_path)

    text = _log_text(tmp_path)
    assert "check_backend_and_navigate FAILED" in text
    assert "WebViewException" in text
    assert len(window.urls) == 2 and window.urls[1].startswith("file://")
    assert window.urls[1].endswith("error.html")


def test_navigate_watchdog_falls_back_to_browser(shell, tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: 18125)
    monkeypatch.setattr(shell, "_app_load_timeout", lambda: 1)
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    window = _FakeWindow(loaded=False)  # 应用页永不装载

    shell.check_backend_and_navigate(window, tmp_path)

    text = _log_text(tmp_path)
    assert "app page NOT loaded" in text
    assert opened == ["http://127.0.0.1:18125"]
    assert window.urls[-1].endswith("error.html")


# ── 6. main()：清陈旧 port.json ＋ 启动留痕 ────────────────────────────────


def test_main_clears_stale_port_json_and_logs(shell, tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    (appdata / "port.json").write_text('{"port": 18001}', encoding="utf-8")

    created: list[dict] = []
    windows: list[_FakeWindow] = []
    started: list[bool] = []
    served: list[bool] = []

    class _StubWebview:
        screens: ClassVar[list] = []

        @staticmethod
        def create_window(**kwargs):
            created.append(kwargs)
            window = _FakeWindow()
            windows.append(window)
            return window

        @staticmethod
        def start(debug=False):
            started.append(True)

    monkeypatch.setattr(shell, "webview", _StubWebview)
    monkeypatch.setattr(shell, "get_appdata", lambda: appdata)
    monkeypatch.setattr(shell, "get_install_dir", lambda: tmp_path / "install")
    monkeypatch.setattr(shell, "ensure_loading_page", lambda ad: (ad / "loading.html").as_uri())
    monkeypatch.setattr(shell, "start_server", lambda: served.append(True))
    monkeypatch.setattr(shell, "check_backend_and_navigate", lambda window, ad: None)

    shell.main()

    assert not (appdata / "port.json").exists(), "陈旧 port.json 必须先清掉"
    assert started == [True]
    assert created and created[0]["js_api"] is shell.bridge
    assert len(windows[0].events.shown.handlers) == 1, "shown 事件必须挂日志钩子"
    text = _log_text(appdata)
    assert "shell main() entered" in text
    assert "server thread started" in text


# ── 7. 运行目录换名（AI Novel → AwesomeNovel）＋无痛迁移 ───────────────────


def _seed_legacy_appdata(base: Path) -> Path:
    legacy = base / "AI Novel"
    (legacy / "data").mkdir(parents=True)
    (legacy / "data" / "novel.db").write_text("books", encoding="utf-8")
    (legacy / "startup.log").write_text("old log", encoding="utf-8")
    return legacy


def test_migrate_appdata_renames_and_leaves_symlink(shell, tmp_path):
    """迁移＝同卷原子换名＋旧路径留软链：旧版本装回来照样看得到书。"""
    old = _seed_legacy_appdata(tmp_path)

    result = shell._migrate_legacy_appdata(tmp_path)

    assert result == tmp_path / shell.APP_DIR_NAME
    assert (result / "data" / "novel.db").read_text(encoding="utf-8") == "books"
    assert old.is_symlink(), "旧路径必须留符号链接（兼容回滚旧版本）"
    assert old.resolve() == result.resolve()


def test_migrate_appdata_skips_when_new_exists(shell, tmp_path):
    """新旧并存＝已经迁移过或用户在旧版本里新写过：两边都不许动。"""
    old = _seed_legacy_appdata(tmp_path)
    new = tmp_path / shell.APP_DIR_NAME
    new.mkdir()
    (new / "keep.txt").write_text("new", encoding="utf-8")

    assert shell._migrate_legacy_appdata(tmp_path) == new
    assert (new / "keep.txt").exists()
    assert not old.is_symlink() and (old / "data" / "novel.db").exists()


def test_migrate_appdata_falls_back_to_legacy_on_error(shell, tmp_path, monkeypatch):
    """改名失败（被占用/权限）→ 继续用旧目录：名字可以晚点换，书不能看不见。"""
    old = _seed_legacy_appdata(tmp_path)

    def _boom(self, target):
        raise OSError("locked")

    monkeypatch.setattr(Path, "rename", _boom)

    assert shell._migrate_legacy_appdata(tmp_path) == old
    assert (old / "data" / "novel.db").exists()


def test_get_appdata_macos_migrates_legacy(shell, tmp_path, monkeypatch):
    base = tmp_path / "support"
    base.mkdir()
    _seed_legacy_appdata(base)
    monkeypatch.setattr(shell, "_appdata_base", lambda: base)
    monkeypatch.setattr(shell, "sys", types.SimpleNamespace(platform="darwin"))

    assert shell.get_appdata() == base / shell.APP_DIR_NAME
    assert (base / shell.APP_DIR_NAME / "data" / "novel.db").exists()


def test_get_appdata_windows_uses_new_name_without_migration(shell, tmp_path, monkeypatch):
    """Windows 侧该目录只是日志：直接换名用新目录，旧目录（历史日志）不搬迁。"""
    legacy = _seed_legacy_appdata(tmp_path)
    monkeypatch.setattr(shell, "_appdata_base", lambda: tmp_path)
    monkeypatch.setattr(shell, "sys", types.SimpleNamespace(platform="win32"))

    assert shell.get_appdata() == tmp_path / shell.APP_DIR_NAME
    assert not (tmp_path / shell.APP_DIR_NAME).exists()
    assert (legacy / "data" / "novel.db").exists()
