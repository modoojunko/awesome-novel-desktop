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

第二轮现场（2026-10-06 测试机 startup.log：后端就绪、导航已发出，60 秒内
WebView2 连 NavigationCompleted 都没发生）补的契约（shell-render-resilience）：

8. 调参文件 <appdata>/shell.json（webview_args / backend_timeout / app_load_timeout /
   safe_mode）：缺省＝行为不变；非法值回落默认且永不把启动打崩；
9. 装载挂死 → 落 render-hang.flag → 下次启动固定走安全模式（--disable-gpu，
   经 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS 追加注入）＋Windows 安装版自愈重启
   （仅非安全模式一轮，防死循环）；
10. 判据落盘：WebView2 版本、生效参数、pywebview 调试日志旁路、后端 access 日志
    （用来分辨「渲染进程的请求到没到后端」）。

pywebview_app.py 带模块级 `import webview`（GUI 框架在 Linux CI 上不可导入），
故经 stub 加载源码模块，只测启动链的纯逻辑分支。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
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
    monkeypatch.setattr(shell, "check_backend_and_navigate", lambda window, ad, cfg=None: None)
    armed: list = []
    monkeypatch.setattr(shell, "arm_hang_dump", lambda ad, period=60.0: armed.append(ad))
    contained: list = []
    monkeypatch.setattr(
        shell, "contain_webview_children", lambda ad, note="": contained.append(note) or 0
    )
    # main() 末尾会强制下线（os._exit）——必须替换，否则把 pytest 一起带走
    exited: list = []
    monkeypatch.setattr(shell, "_force_exit", lambda code=0: exited.append(code))
    monkeypatch.setattr(shell, "stop_server_gracefully", lambda timeout=3.0: True)

    shell.main()

    assert not (appdata / "port.json").exists(), "陈旧 port.json 必须先清掉"
    assert started == [True]
    assert created and created[0]["js_api"] is shell.bridge
    assert len(windows[0].events.shown.handlers) == 1, "shown 事件必须挂日志钩子"
    assert armed == [appdata], "C 层 hang dump 必须在上窗口前架上"
    assert contained == ["（建窗后）"], "建窗后必须把 WebView2 子树收进 job（第一拍）"
    assert exited == [0], "窗口关闭后必须强制下线（不留残留进程）"
    text = _log_text(appdata)
    assert "shell main() entered" in text
    assert "server thread started" in text
    # 顺序：先 GUI 退出 → 再有界收尾 → 再强退
    assert text.index("GUI loop exited") < text.index("backend shutdown")
    assert "backend shutdown: graceful=True" in text


# ── 7. 运行目录换名（AI Novel → AwesomeNovel）＋无痛迁移 ───────────────────


def _seed_legacy_appdata(base: Path) -> Path:
    legacy = base / "AI Novel"
    (legacy / "data").mkdir(parents=True)
    (legacy / "data" / "novel.db").write_text("books", encoding="utf-8")
    (legacy / "startup.log").write_text("old log", encoding="utf-8")
    return legacy


@pytest.mark.skipif(sys.platform == "win32", reason="符号链接需开发者模式；仓库 pytest 只在非 Windows 跑")
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


# ── 8. 调参文件 shell.json ────────────────────────────────────────────────


def test_shell_config_missing_means_defaults(shell, tmp_path):
    assert shell.load_shell_config(tmp_path) == {}


def test_shell_config_reads_valid_values(shell, tmp_path):
    (tmp_path / shell.SHELL_CONFIG_NAME).write_text(
        json.dumps({
            "webview_args": "--disable-gpu",
            "backend_timeout": 120,
            "app_load_timeout": 90,
            "safe_mode": True,
        }),
        encoding="utf-8",
    )

    cfg = shell.load_shell_config(tmp_path)

    assert cfg == {
        "webview_args": "--disable-gpu",
        "backend_timeout": 120,
        "app_load_timeout": 90,
        "safe_mode": True,
    }


def test_shell_config_bad_json_never_crashes(shell, tmp_path):
    (tmp_path / shell.SHELL_CONFIG_NAME).write_text("{not json", encoding="utf-8")

    assert shell.load_shell_config(tmp_path) == {}
    assert "shell.json 读取失败" in _log_text(tmp_path)


def test_shell_config_non_object_ignored(shell, tmp_path):
    (tmp_path / shell.SHELL_CONFIG_NAME).write_text("[1, 2]", encoding="utf-8")

    assert shell.load_shell_config(tmp_path) == {}
    assert "shell.json 不是对象" in _log_text(tmp_path)


def test_shell_config_clamps_and_rejects_bad_types(shell, tmp_path):
    (tmp_path / shell.SHELL_CONFIG_NAME).write_text(
        json.dumps({
            "backend_timeout": 99999,
            "app_load_timeout": 1,
            "webview_args": "  --disable-gpu --use-angle=swiftshader  ",
            "safe_mode": "yes",
        }),
        encoding="utf-8",
    )

    cfg = shell.load_shell_config(tmp_path)

    assert cfg["backend_timeout"] == 600, "超时上限 600 秒"
    assert cfg["app_load_timeout"] == 5, "超时下限 5 秒"
    assert cfg["webview_args"] == "--disable-gpu --use-angle=swiftshader"
    assert "safe_mode" not in cfg, "非布尔 safe_mode 必须忽略（回落标记自动判定）"


def test_shell_config_logs_rejected_and_clamped_values(shell, tmp_path):
    """回落必须留痕：现场调参最怕"写了却没生效"（spec：类型不符/越界 SHALL 回落并留日志）。"""
    (tmp_path / shell.SHELL_CONFIG_NAME).write_text(
        json.dumps({
            "backend_timeout": "abc",
            "app_load_timeout": 99999,
            "webview_args": [1],
            "safe_mode": "yes",
        }),
        encoding="utf-8",
    )

    cfg = shell.load_shell_config(tmp_path)
    text = _log_text(tmp_path)

    assert cfg["backend_timeout"] == shell.DEFAULT_BACKEND_TIMEOUT and cfg["app_load_timeout"] == 600
    for key in ("backend_timeout", "app_load_timeout", "webview_args", "safe_mode"):
        assert key in text, f"{key} 回落必须留日志"
    assert "99999" in text, "越界原值要原样可见，便于现场对照自己写了什么"


def test_config_timeouts_flow_into_wait_and_watchdog(shell, tmp_path, monkeypatch):
    (tmp_path / shell.SHELL_CONFIG_NAME).write_text(
        json.dumps({"backend_timeout": 120, "app_load_timeout": 7}), encoding="utf-8"
    )
    seen: dict = {}

    def _wait(appdata, timeout=60):
        seen["backend"] = timeout
        return 18127

    monkeypatch.setattr(shell, "wait_for_server", _wait)
    monkeypatch.setattr(shell, "should_auto_relaunch", lambda *a, **k: False)
    monkeypatch.setattr("webbrowser.open", lambda url: True)

    shell.check_backend_and_navigate(_FakeWindow(loaded=False), tmp_path)

    assert seen["backend"] == 120, "后端超时必须吃 shell.json"
    assert "app page NOT loaded in 7s" in _log_text(tmp_path), "装载看门狗必须吃 shell.json"


# ── 9. 安全模式：标记、判定、参数注入 ─────────────────────────────────────


def test_webview_args_combine_config_and_safe_mode(shell):
    assert shell.webview_browser_args({}, False) == ""
    assert shell.webview_browser_args({"webview_args": "--foo"}, True) == "--foo --disable-gpu"
    assert shell.webview_browser_args({"webview_args": "--foo"}, False) == "--foo"
    assert shell.webview_browser_args({}, True) == "--disable-gpu"


def test_apply_webview_args_appends_never_clobbers(shell, monkeypatch):
    monkeypatch.setenv("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--disable-features=ElasticOverscroll")

    shell.apply_webview_args("--disable-gpu")

    assert (
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"]
        == "--disable-features=ElasticOverscroll --disable-gpu"
    ), "WebView2 该环境变量是追加语义——绝不许覆盖用户/框架已设的值"

    shell.apply_webview_args("")
    assert os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"].endswith("--disable-gpu")


def test_safe_mode_follows_flag_and_config(shell, tmp_path):
    assert shell.safe_mode_enabled(tmp_path, {}) is False, "无标记无配置＝默认渲染模式"

    shell.flag_render_hang(tmp_path, "app page NOT loaded")
    assert shell.render_hang_flagged(tmp_path) is True
    assert shell.safe_mode_enabled(tmp_path, {}) is True, "挂死标记＝安全模式"

    assert shell.safe_mode_enabled(tmp_path, {"safe_mode": False}) is False, "shell.json 可强制退出安全模式"
    assert shell.safe_mode_enabled(tmp_path, {"safe_mode": True}) is True


def test_should_auto_relaunch_guards(shell):
    base = {
        "safe_mode": False,
        "frozen": True,
        "platform": "win32",
        "already_relaunched": False,
        "safe_mode_opted_out": False,
    }

    assert shell.should_auto_relaunch(**base) is True
    assert shell.should_auto_relaunch(**{**base, "safe_mode": True}) is False, "已在安全模式不重启"
    assert shell.should_auto_relaunch(**{**base, "frozen": False}) is False, "dev（非冻结）不重启"
    assert shell.should_auto_relaunch(**{**base, "platform": "darwin"}) is False
    assert shell.should_auto_relaunch(**{**base, "already_relaunched": True}) is False, (
        "本进程已是重启代＝不许再重启（不看标记是否写成功，从根上断掉重启环）"
    )
    assert shell.should_auto_relaunch(**{**base, "safe_mode_opted_out": True}) is False, (
        "用户 shell.json 显式关安全模式＝不自愈重启"
    )


def test_webview2_version_never_raises(shell, monkeypatch):
    monkeypatch.setattr(shell.sys, "platform", "darwin")
    assert shell.webview2_version() is None

    monkeypatch.setattr(shell.sys, "platform", "win32")
    # 非 Windows 环境没有 winreg：必须静默回落 None，绝不把启动打崩
    assert shell.webview2_version() is None


def test_watchdog_success_keeps_safe_mode_until_manual_exit(shell, tmp_path, monkeypatch):
    """安全模式一旦生效就保持（同机同运行时默认渲染路径已被证明会挂）。"""
    shell.flag_render_hang(tmp_path, "previous run hung")
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: 18128)

    shell.check_backend_and_navigate(_FakeWindow(loaded=True), tmp_path)

    text = _log_text(tmp_path)
    assert "app page loaded" in text
    assert "safe mode 生效" in text
    assert (tmp_path / shell.RENDER_HANG_MARKER).exists(), "成功一次不代表默认模式已修好——标记保留"


# ── 10. 装载挂死：落标记 → 自愈重启（Windows 安装版）／浏览器兜底 ────────────


def test_watchdog_hang_flags_marker_and_relaunches_when_allowed(shell, tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: 18126)
    monkeypatch.setattr(shell, "_app_load_timeout", lambda: 1)
    monkeypatch.setattr(shell, "should_auto_relaunch", lambda *a, **k: True)
    relaunched: list = []
    exited: list = []
    opened: list = []
    monkeypatch.setattr(shell, "relaunch_in_safe_mode", lambda ad: relaunched.append(ad) or True)
    monkeypatch.setattr(shell, "_exit_soon", lambda delay=1.5: exited.append(delay))
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    window = _FakeWindow(loaded=False)

    shell.check_backend_and_navigate(window, tmp_path)

    text = _log_text(tmp_path)
    assert "app page NOT loaded" in text
    assert (tmp_path / shell.RENDER_HANG_MARKER).exists(), "挂死必须落标记（新实例据此进安全模式）"
    assert relaunched == [tmp_path]
    assert exited, "窗口已挂死，必须走强制退出（正常退出路径走不了）"
    assert opened == [], "自愈重启路径不再叠开浏览器"
    assert all(not u.endswith("error.html") for u in window.urls)


def test_watchdog_hang_never_relaunches_twice(shell, tmp_path, monkeypatch):
    """重启代再挂：只走兜底——标记写失败/被忽略也不会成重启环。"""
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: 18130)
    monkeypatch.setattr(shell, "_app_load_timeout", lambda: 1)
    monkeypatch.setattr(shell, "relaunch_depth_exceeded", lambda: True)
    monkeypatch.setattr(shell, "sys", types.SimpleNamespace(platform="win32", frozen=True))
    spawned: list = []
    monkeypatch.setattr(shell, "relaunch_in_safe_mode", lambda ad: spawned.append(ad) or True)
    opened: list = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)

    shell.check_backend_and_navigate(_FakeWindow(loaded=False), tmp_path)

    assert spawned == [], "本进程已是重启代：不许再拉起新实例"
    assert opened == ["http://127.0.0.1:18130"], "必须走浏览器兜底"
    assert "auto relaunch 跳过" in _log_text(tmp_path)


def test_watchdog_hang_no_relaunch_when_safe_mode_opted_out(shell, tmp_path, monkeypatch):
    """shell.json 显式 safe_mode:false：连冻结版也不自愈重启（用户已明确不要安全模式）。"""
    (tmp_path / shell.SHELL_CONFIG_NAME).write_text(
        json.dumps({"safe_mode": False}), encoding="utf-8"
    )
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: 18131)
    monkeypatch.setattr(shell, "_app_load_timeout", lambda: 1)
    monkeypatch.setattr(shell, "sys", types.SimpleNamespace(platform="win32", frozen=True))
    spawned: list = []
    monkeypatch.setattr(shell, "relaunch_in_safe_mode", lambda ad: spawned.append(ad) or True)
    monkeypatch.setattr("webbrowser.open", lambda url: True)

    shell.check_backend_and_navigate(_FakeWindow(loaded=False), tmp_path)

    assert spawned == [], "重启进的是用户已拒绝的安全模式——重启毫无意义，还会成环"
    assert "auto relaunch 跳过" in _log_text(tmp_path)


def test_relaunch_child_gets_preexisting_env_only(shell, tmp_path, monkeypatch):
    """孩子进程不许继承父进程叠加后的参数（否则二次叠加，还会盖掉用户原值）。"""
    monkeypatch.setenv("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--user-flag")
    shell.apply_webview_args("--disable-gpu")
    assert os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] == "--user-flag --disable-gpu"
    captured: dict = {}

    class _Popen:
        def __init__(self, argv, **kwargs):
            captured["argv"] = argv
            captured.update(kwargs)

    monkeypatch.setattr("subprocess.Popen", _Popen)

    assert shell.relaunch_in_safe_mode(tmp_path) is True
    assert captured["argv"] == [sys.executable]
    assert captured["env"]["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] == "--user-flag"
    assert captured["env"][shell.RELAUNCH_ENV_KEY] == "1", "孩子进程必须带上重启深度标记（最多一轮）"


def test_watchdog_hang_falls_back_when_relaunch_disallowed(shell, tmp_path, monkeypatch):
    """已在安全模式/非 Windows/非冻结：不重启，落标记＋浏览器兜底＋错误页。"""
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: 18125)
    monkeypatch.setattr(shell, "_app_load_timeout", lambda: 1)
    monkeypatch.setattr(shell, "should_auto_relaunch", lambda *a, **k: False)
    opened: list = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    window = _FakeWindow(loaded=False)

    shell.check_backend_and_navigate(window, tmp_path)

    text = _log_text(tmp_path)
    assert "app page NOT loaded" in text
    assert (tmp_path / shell.RENDER_HANG_MARKER).exists()
    assert opened == ["http://127.0.0.1:18125"]
    assert window.urls[-1].endswith("error.html")


# ── 11. 运行目录选择（shell-runtime-dir）：安装目录可写优先，appdata 兜底 ────────


def test_install_dir_writable_probe(shell, tmp_path):
    ok = tmp_path / "install"
    assert shell._install_dir_writable(ok) is True
    assert not (ok / shell.RUNTIME_PROBE_NAME).exists(), "探针文件必须写完即删"

    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")  # 当目录用必然建不出来
    assert shell._install_dir_writable(blocker / "sub") is False


def test_runtime_dir_prefers_writable_install_dir_when_frozen(shell, tmp_path, monkeypatch):
    install, appdata = tmp_path / "install", tmp_path / "appdata"
    install.mkdir()
    monkeypatch.setattr(shell, "sys", types.SimpleNamespace(platform="win32", frozen=True))
    monkeypatch.setattr(shell, "get_install_dir", lambda: install)
    monkeypatch.setattr(shell, "get_appdata", lambda: appdata)

    assert shell.get_runtime_dir() == install, "安装目录可写＝运行目录（日志/调参跟 data 在一起）"


def test_runtime_dir_falls_back_when_install_dir_unwritable(shell, tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    appdata = tmp_path / "appdata"
    monkeypatch.setattr(shell, "sys", types.SimpleNamespace(platform="win32", frozen=True))
    monkeypatch.setattr(shell, "get_install_dir", lambda: blocker / "AwesomeNovel")
    monkeypatch.setattr(shell, "get_appdata", lambda: appdata)

    assert shell.get_runtime_dir() == appdata, "装到不可写位置（Program Files）必须回落 appdata"


def test_runtime_dir_dev_and_macos_use_appdata(shell, tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    monkeypatch.setattr(shell, "get_install_dir", lambda: tmp_path / "install")
    monkeypatch.setattr(shell, "get_appdata", lambda: appdata)

    monkeypatch.setattr(shell, "sys", types.SimpleNamespace(platform="win32", frozen=False))
    assert shell.get_runtime_dir() == appdata, "dev（非冻结）不往项目目录写"

    monkeypatch.setattr(shell, "sys", types.SimpleNamespace(platform="darwin", frozen=True))
    assert shell.get_runtime_dir() == appdata, "macOS 上 appdata 目录同时是书稿数据目录"


def test_legacy_runtime_dir_only_when_different(shell, tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    monkeypatch.setattr(shell, "get_appdata", lambda: appdata)

    assert shell._legacy_runtime_dir(appdata) is None, "同一目录＝无兼容读取源"
    assert shell._legacy_runtime_dir(tmp_path / "install") == appdata


def test_shell_config_reads_legacy_appdata_location(shell, tmp_path):
    """v0.28.1 的指引把 shell.json 指向 %APPDATA%：升到本版后不许静默忽略。"""
    runtime, legacy = tmp_path / "install", tmp_path / "appdata"
    runtime.mkdir()
    legacy.mkdir()
    (legacy / shell.SHELL_CONFIG_NAME).write_text(
        json.dumps({"backend_timeout": 180}), encoding="utf-8"
    )

    cfg = shell.load_shell_config(runtime, legacy_dir=legacy)

    assert cfg["backend_timeout"] == 180
    assert "旧位置" in _log_text(runtime), "取旧位置调参必须留痕（提示挪到运行目录）"


def test_shell_config_runtime_dir_wins_over_legacy(shell, tmp_path):
    runtime, legacy = tmp_path / "install", tmp_path / "appdata"
    runtime.mkdir()
    legacy.mkdir()
    (runtime / shell.SHELL_CONFIG_NAME).write_text(json.dumps({"backend_timeout": 90}), encoding="utf-8")
    (legacy / shell.SHELL_CONFIG_NAME).write_text(json.dumps({"backend_timeout": 180}), encoding="utf-8")

    assert shell.load_shell_config(runtime, legacy_dir=legacy)["backend_timeout"] == 90


# ── 12. 后端就绪等待：心跳与判负文案（2026-10-06 现场两处误读的修复钉子）─────


def test_wait_for_server_logs_heartbeat_with_probe_class(shell, tmp_path, monkeypatch):
    """慢机器定位：等待期心跳必须带「探测分类」——下次现场能分清"慢"与"死"。"""
    (tmp_path / "port.json").write_text(json.dumps({"port": 18123}), encoding="utf-8")
    clock = {"t": 0.0}
    monkeypatch.setattr(shell.time, "time", lambda: clock["t"])
    monkeypatch.setattr(shell.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + 5.0))
    monkeypatch.setattr(shell, "_probe_backend", lambda port: (False, "连接被拒（uvicorn 尚未开始监听，多半还在导入 app）"))

    assert shell.wait_for_server(tmp_path, timeout=40) is None

    text = _log_text(tmp_path)
    assert "backend still starting" in text, "等待期必须有心跳行"
    assert "连接被拒" in text, "心跳必须带探测分类（判慢/判死就靠它）"


def test_probe_backend_classifies_refused_vs_unresponsive(shell, monkeypatch):
    import urllib.error

    def _refused(*_a, **_k):
        raise urllib.error.URLError(ConnectionRefusedError(10061, "refused"))

    monkeypatch.setattr("urllib.request.urlopen", _refused)
    ok, note = shell._probe_backend(18123)
    assert ok is False and "连接被拒" in note, "连接被拒＝uvicorn 还没监听（导入阶段）"

    def _timeout(*_a, **_k):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", _timeout)
    ok, note = shell._probe_backend(18123)
    assert ok is False and "已监听" in note, "连上但没响应＝lifespan/app 启动进行中"

    def _wrapped_timeout(*_a, **_k):
        # urllib 真实形态：socket 超时被包成 URLError(reason=TimeoutError)
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr("urllib.request.urlopen", _wrapped_timeout)
    ok, note = shell._probe_backend(18123)
    assert ok is False and "已监听" in note, "被包成 URLError 的超时同样要认出来"

    class _Resp:
        status = 200

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    assert shell._probe_backend(18123) == (True, "")


def test_backend_timeout_message_states_actual_cause(shell, tmp_path, monkeypatch):
    """线程活着时不许说它退了：旧文案被两次误读成"后端崩了"。"""
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: None)
    monkeypatch.setattr(shell, "_show_error", lambda *a, **k: None)

    shell.check_backend_and_navigate(_FakeWindow(), tmp_path)
    text = _log_text(tmp_path)
    assert "backend NOT ready" in text
    assert "时间不够" not in text
    assert "server thread exited" not in text, "线程未退就不许写它退了"
    assert "仍在活着" in text or "仍活着" in text


def test_backend_timeout_message_names_thread_exit(shell, tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: None)
    monkeypatch.setattr(shell, "_show_error", lambda *a, **k: None)
    shell._server_exited.set()

    shell.check_backend_and_navigate(_FakeWindow(), tmp_path)

    assert "server thread exited" in _log_text(tmp_path)
    shell._server_exited.clear()


# ── 13. js_api 暴露面 / 退出硬化 / hang dump（c-shell-hang-hardening）─────────


def test_bridge_public_surface_is_methods_only(shell):
    """pywebview 注入时**递归遍历** js_api 的公开非方法属性（util.py get_functions 只跳 `_` 前缀）：
    桥上挂公开对象＝把原生窗口整棵树拖进遍历 → 跨线程 COM 报错、甚至装载停摆（2026-10-06 白屏根因）。
    本守卫与打包 CI 的 check_bridge_surface.py（AST）双钉。"""
    public = [n for n in dir(shell.bridge) if not n.startswith("_")]
    assert public, "桥至少要有可暴露的方法"
    for name in public:
        assert callable(getattr(shell.bridge, name)), (
            f"js_api 公开成员 {name!r} 不是可调用——pywebview 会递归进它（必须改下划线前缀）"
        )


def test_bridge_surface_ast_gate_flags_public_attr_and_passes_real_file():
    import importlib.util

    gate_path = Path(__file__).resolve().parents[2] / "packaging" / "build" / "check_bridge_surface.py"
    spec = importlib.util.spec_from_file_location("check_bridge_surface_under_test", gate_path)
    gate = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(gate)

    assert gate.find_violations("class NativeBridge:\n    window_ref = None\n"), "公开类属性必须被抓出"
    assert gate.find_violations("bridge = NativeBridge()\nbridge.window = None\n"), "桥实例公开属性必须被抓出"
    real = Path(__file__).resolve().parents[2] / "packaging" / "build" / "pywebview_app.py"
    assert gate.find_violations(real.read_text(encoding="utf-8")) == [], "真实文件必须放行"


def test_watchdog_logs_heartbeat_while_waiting(shell, tmp_path, monkeypatch):
    """装载等待不许死等：每 10 秒落一行心跳（也是"进程还活着"的证据）。"""
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: 18140)
    monkeypatch.setattr(shell, "should_auto_relaunch", lambda *a, **k: False)
    monkeypatch.setattr("webbrowser.open", lambda url: True)

    shell.check_backend_and_navigate(_FakeWindow(loaded=False), tmp_path)

    text = _log_text(tmp_path)
    assert "app page still loading… 10s/60s" in text
    assert "app page still loading… 60s/60s" in text


def test_hang_dump_armed_and_cancelled(shell, tmp_path):
    shell.arm_hang_dump(tmp_path, period=600)
    try:
        assert (tmp_path / "hang-dump.txt").exists()
        assert shell._HANG_DUMP_FILE is not None
    finally:
        shell.cancel_hang_dump()
    assert shell._HANG_DUMP_FILE is None, "取消后必须关掉文件句柄（flush）"


def test_stop_server_gracefully_signals_then_reports_timeout(shell, monkeypatch):
    class _Srv:
        def __init__(self):
            self.should_exit = False

    srv = _Srv()
    monkeypatch.setattr(shell, "_server_handle", srv)
    monkeypatch.setattr(shell, "_server_exited", threading.Event())
    clock = {"t": 0.0}
    monkeypatch.setattr(shell.time, "time", lambda: clock["t"])
    monkeypatch.setattr(shell.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + 1.0))

    assert shell.stop_server_gracefully(timeout=3.0) is False, "未回收必须如实返回 False（调用方仍强退）"
    assert srv.should_exit is True, "必须先发退出信号"


# ── 14. WebView2 子树收口（Windows Job Object）＋兜底页文案 ─────────────────


@pytest.mark.skipif(sys.platform == "win32", reason="Windows 上该调用会真实建 job；仓库 pytest 只在非 Windows 跑")
def test_contain_webview_children_noop_off_windows(shell, tmp_path):
    """非 Windows 必须静默 no-op（dev/macOS 不产生任何副作用与日志）。"""
    assert shell.contain_webview_children(tmp_path, "（测试）") == 0
    assert shell._WEBVIEW_JOB is None
    assert not (tmp_path / "startup.log").exists() or "containment" not in _log_text(tmp_path)


def test_contain_webview_children_degrades_on_failure(shell, tmp_path, monkeypatch):
    """任一 API 失败只留日志、照常继续。注入失败而非依赖平台差异——否则本用例在真 Windows 上必红。"""
    monkeypatch.setattr(shell, "sys", types.SimpleNamespace(platform="win32"))

    def _boom():
        raise OSError("模拟装 job 失败")

    monkeypatch.setattr(shell, "_create_kill_on_close_job", _boom)

    assert shell.contain_webview_children(tmp_path, "（降级测试）") == 0
    text = _log_text(tmp_path)
    assert "webview containment" in text and "降级继续" in text


def test_containment_logs_are_segmented(shell, tmp_path, monkeypatch):
    """真机验收判据：分段留痕（job 已建／枚举 N／打开 M／纳入 K）——否则"枚举不到"与"纳入失败"
    在日志里长得一模一样，机制静默失效也看不出来（评审整改）。"""
    monkeypatch.setattr(shell, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(shell, "_create_kill_on_close_job", lambda: 12345)
    monkeypatch.setattr(shell, "_win_child_pids", lambda pid, exe: [])

    assert shell.contain_webview_children(tmp_path, "（分段）") == 0

    text = _log_text(tmp_path)
    assert "job 已建（KILL_ON_JOB_CLOSE）" in text
    assert "子进程 0 个，打开 0 个，纳入 0 个" in text


def test_containment_runs_again_after_app_page_loaded(shell, tmp_path, monkeypatch):
    """装载成功后要补扫一次（WebView2 浏览器进程异步起，建窗时那拍可能扫不到）。"""
    monkeypatch.setattr(shell, "wait_for_server", lambda appdata, timeout=60: 18150)
    contained: list = []
    monkeypatch.setattr(
        shell, "contain_webview_children", lambda ad, note="": contained.append(note) or 0
    )

    shell.check_backend_and_navigate(_FakeWindow(loaded=True), tmp_path)

    assert contained == ["（装载后）"]


def test_error_page_states_browser_fallback_dependency(shell, tmp_path):
    (tmp_path / "startup.log").write_text("[t] x", encoding="utf-8")
    (tmp_path / "uvicorn.log").write_text("[t] y", encoding="utf-8")

    html = shell.write_error_page(tmp_path, "后端启动超时").read_text(encoding="utf-8")

    assert "浏览器兜底说明" in html, "错误页必须写明兜底页随本程序失效（用户理解一致）"
