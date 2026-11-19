"""mac 右键菜单恢复补丁（c-chat-copy）的契约测试。

pywebview 的 cocoa 实现在非 debug 态把上下文菜单整个清空（willOpenMenu_withEvent_
→ removeAllItems）——WebView 里选中文字后右键无任何菜单，复制入口断绝（Cmd+C
虽有壳层 keyDown 兜底但无可见入口）。壳层 restore_macos_context_menu() 运行时
替换该回调装配标准编辑项。本组测试钉住：

1. darwin ＋ cocoa 平台模块可用 → 'ok'，回调替换为装配「剪切/拷贝/粘贴/全选」；
2. 非 darwin → 'skip: not darwin'，平台模块零触碰；
3. cocoa/AppKit 不可导入（Linux CI、无 pyobjc）→ 'skip'，零副作用；
4. WebKitHost 类结构不符（上游改版）→ 'skip'，零副作用；
5. 替换失败（类冻结等异常）→ 'fail:' 带 traceback，绝不炸启动链。

pywebview_app.py 带模块级 import webview——与 test_packaging_shell_startup 同款
stub 加载（loader 必须自带守卫：pywebview 不在 backend requirements，单跑本
文件/字母序变动时不能指望别的文件先塞过 stub）；webview.platforms / AppKit
均 fake 注入 sys.modules（dev venv 里 pyobjc 真模块存在，不能让真 NSMenuItem
参与断言；Linux CI 两者皆缺，必须 stub 才可复现 ok 路径）。
"""
from __future__ import annotations

import importlib.util
import sys
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
    spec = importlib.util.spec_from_file_location("pywebview_app_under_test_cm", SHELL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _OriginalHost:
    """上游原行为：非 debug 态右键菜单整个清空。"""

    def willOpenMenu_withEvent_(self, menu, event):
        menu.removeAllItems()


class _NoHostBrowserView:
    """上游改版后 WebKitHost 缺位的形态。"""


class _FrozenMeta(type):
    """类属性赋值走 metaclass 的 __setattr__——冻结模拟必须冻在元类层。"""

    def __setattr__(cls, name, value):
        raise RuntimeError("frozen")


class _FrozenHost(metaclass=_FrozenMeta):
    """替换 willOpenMenu_withEvent_ 即抛错：模拟替换失败路径。"""


class _FakeNSMenuItem:
    created: ClassVar[list[tuple[str, str, str]]] = []

    @classmethod
    def alloc(cls):
        return cls()

    def initWithTitle_action_keyEquivalent_(self, title, action, key):
        self.title = title
        self.action = action
        self.key = key
        self.created.append((title, action, key))
        return self


class _FakeMenu:
    def __init__(self):
        self.items = []
        self.cleared = False

    def removeAllItems(self):
        self.items.clear()
        self.cleared = True

    def addItem_(self, item):
        self.items.append(item)


def _fake_env(host_cls):
    """webview.platforms.cocoa + AppKit fake 三件套：注册进 sys.modules 由
    monkeypatch 收尾还原；返回 (cocoa_mod, BrowserView) 供断言。"""
    cocoa_mod = types.ModuleType("webview.platforms.cocoa")
    platform_mod = types.ModuleType("webview.platforms")

    class _BrowserView:
        WebKitHost = host_cls

    cocoa_mod.BrowserView = _BrowserView
    platform_mod.cocoa = cocoa_mod

    appkit_mod = types.ModuleType("AppKit")
    appkit_mod.NSMenuItem = _FakeNSMenuItem

    return cocoa_mod, _BrowserView, appkit_mod, platform_mod


@pytest.fixture()
def shell():
    return _load_shell_module()


def test_ok_patches_callback_and_installs_edit_items(monkeypatch, shell):
    _FakeNSMenuItem.created.clear()
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    cocoa_mod, browser, appkit_mod, platform_mod = _fake_env(_OriginalHost)
    monkeypatch.setitem(sys.modules, "webview.platforms", platform_mod)
    monkeypatch.setitem(sys.modules, "webview.platforms.cocoa", cocoa_mod)
    monkeypatch.setitem(sys.modules, "AppKit", appkit_mod)

    result = shell.restore_macos_context_menu()

    assert result == "ok"
    menu = _FakeMenu()
    browser.WebKitHost().willOpenMenu_withEvent_(menu, None)
    assert menu.cleared
    assert _FakeNSMenuItem.created == [
        ("剪切", "cut:", "x"),
        ("拷贝", "copy:", "c"),
        ("粘贴", "paste:", "v"),
        ("全选", "selectAll:", "a"),
    ]
    assert [i.action for i in menu.items] == ["cut:", "copy:", "paste:", "selectAll:"]
    assert [i.key for i in menu.items] == ["x", "c", "v", "a"]


def test_non_darwin_skips_without_touching_platform(monkeypatch, shell):
    monkeypatch.setattr(sys, "platform", "win32")
    cocoa_mod, browser, appkit_mod, platform_mod = _fake_env(_OriginalHost)
    monkeypatch.setitem(sys.modules, "webview.platforms", platform_mod)
    monkeypatch.setitem(sys.modules, "webview.platforms.cocoa", cocoa_mod)
    monkeypatch.setitem(sys.modules, "AppKit", appkit_mod)

    original = browser.WebKitHost.willOpenMenu_withEvent_
    result = shell.restore_macos_context_menu()

    assert result == "skip: not darwin"
    assert browser.WebKitHost.willOpenMenu_withEvent_ is original


def test_missing_cocoa_module_skips(monkeypatch, shell):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    monkeypatch.delitem(sys.modules, "webview.platforms", raising=False)
    monkeypatch.delitem(sys.modules, "webview.platforms.cocoa", raising=False)

    result = shell.restore_macos_context_menu()

    assert result.startswith("skip: cocoa module unavailable")


def test_missing_webkithost_skips(monkeypatch, shell):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    cocoa_mod, _browser, appkit_mod, platform_mod = _fake_env(None)
    cocoa_mod.BrowserView = _NoHostBrowserView
    monkeypatch.setitem(sys.modules, "webview.platforms", platform_mod)
    monkeypatch.setitem(sys.modules, "webview.platforms.cocoa", cocoa_mod)
    monkeypatch.setitem(sys.modules, "AppKit", appkit_mod)

    result = shell.restore_macos_context_menu()

    assert result == "skip: WebKitHost not found"


def test_patch_failure_reports_fail_with_traceback(monkeypatch, shell):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    cocoa_mod, _browser, appkit_mod, platform_mod = _fake_env(_FrozenHost)
    monkeypatch.setitem(sys.modules, "webview.platforms", platform_mod)
    monkeypatch.setitem(sys.modules, "webview.platforms.cocoa", cocoa_mod)
    monkeypatch.setitem(sys.modules, "AppKit", appkit_mod)

    result = shell.restore_macos_context_menu()

    assert result.startswith("fail:")
    assert "frozen" in result
