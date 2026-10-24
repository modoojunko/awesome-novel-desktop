"""client-update-notify：版本自报、节流、出站校验、版本比较、关闭记忆、兜底切换。"""

import asyncio
import base64
import hashlib
import json
import threading
from typing import ClassVar

import pytest

import build_info as bi
import update_check as uc

MAIN_URL = "https://www.awesomenovel.com/download/latest.json"
FALLBACK_URL = "https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/download/latest.json"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """每用例独立：无版本 env（默认 dev 态）+ 干净状态文件 + 构建信息隔离。

    build_info 缓存复位为 None（读过且没有）：pytest 进程非 frozen 且仓库有
    .git，不复位则先跑的用例会把真实 git 信息带进后面用例（顺序依赖假绿假红）；
    构建信息专项用例在各自测试体内再覆盖打桩。
    """
    monkeypatch.delenv("CLIENT_VERSION", raising=False)
    monkeypatch.delenv("CLIENT_UPDATE_URL", raising=False)
    monkeypatch.delenv("CLIENT_UPDATE_URL_FALLBACK", raising=False)
    monkeypatch.delenv("CLIENT_BUILD_BRANCH", raising=False)
    monkeypatch.delenv("CLIENT_BUILD_COMMIT", raising=False)
    monkeypatch.setattr(uc, "_state_path", tmp_path / "update-check.json")
    monkeypatch.setattr(bi, "_git_build", None)
    yield


def _run(coro):
    return asyncio.run(coro)


# ── 版本自报 ─────────────────────────────────────────────────────────────


def test_dev_env_reports_dev_and_skips(monkeypatch):
    """无烘焙（本地开发）→ 版本 dev、不外呼；构建信息缺省为 None。"""
    calls = []

    async def fake_fetch():
        calls.append(1)
        return {"latest": "9.9", "notes": ""}

    monkeypatch.setattr(uc, "_fetch_latest", fake_fetch)
    st = _run(uc.get_update_state())
    assert st == {"current": "dev", "latest": None, "has_update": False,
                  "notes": "", "notes_url": "", "download_url": "",
                  "auto": {"state": "idle", "version": None}, "build": None}
    assert calls == []  # dev 跳过，零外呼


def test_baked_version_env_reports_real_version(monkeypatch):
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    monkeypatch.setattr(uc, "_fetch_latest",
                        _async_returns({"latest": "0.11", "notes": ""}))
    st = _run(uc.get_update_state())
    assert st["current"] == "0.11"
    assert st["has_update"] is False  # 线上相等不提示


# ── 节流 ─────────────────────────────────────────────────────────────────


def _async_returns(value):
    async def fake_fetch():
        return value
    return fake_fetch


def test_throttle_one_hour(monkeypatch):
    """1 小时内第二次检测吃缓存，不重复外呼；到期后重查。"""
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    calls = []

    async def fake_fetch():
        calls.append(1)
        return {"latest": "0.13", "notes": "摘要"}

    monkeypatch.setattr(uc, "_fetch_latest", fake_fetch)
    st1 = _run(uc.get_update_state())
    assert len(calls) == 1 and st1["has_update"] is True and st1["latest"] == "0.13"
    assert st1["notes"] == "摘要"
    assert st1["notes_url"].endswith("/download/v0.13/notes.html")
    assert st1["download_url"] == "https://www.awesomenovel.com"

    # 节流窗内：不外呼，直接回缓存
    st2 = _run(uc.get_update_state())
    assert len(calls) == 1 and st2["has_update"] is True

    # 把 last_check_at 拨回 2 小时前 → 重新外呼
    state = json.loads(uc._state_path.read_text(encoding="utf-8"))
    state["last_check_at"] -= 2 * 3600
    uc._state_path.write_text(json.dumps(state), encoding="utf-8")
    st3 = _run(uc.get_update_state())
    assert len(calls) == 2 and st3["has_update"] is True


def test_failure_is_silent_and_throttled(monkeypatch):
    """外呼失败静默降级（无提示、不抛错），且失败也占节流窗。"""
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    calls = []

    async def fake_fetch():
        calls.append(1)

    monkeypatch.setattr(uc, "_fetch_latest", fake_fetch)
    st = _run(uc.get_update_state())
    assert st["has_update"] is False and st["latest"] is None
    _run(uc.get_update_state())
    assert len(calls) == 1  # 失败也计入节流，弱网下 15 分钟轮询不连打


def test_corrupt_state_file_tolerated(monkeypatch):
    """状态文件损坏按首启处理。"""
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    uc._state_path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(uc, "_fetch_latest", _async_returns({"latest": "0.12", "notes": ""}))
    st = _run(uc.get_update_state())
    assert st["has_update"] is True


# ── 版本比较 ─────────────────────────────────────────────────────────────


def test_numeric_segment_compare():
    assert uc._has_newer("0.11", "0.10.1") is True   # 数值段：0.10.1 < 0.11
    assert uc._has_newer("0.11", "0.11") is False
    assert uc._has_newer("0.10", "0.11") is False    # 线上更低（人工回滚）不提示
    assert uc._has_newer("0.9.2", "0.10") is False
    assert uc._has_newer("1.0", "0.99.99") is True


def test_version_compare_never_raises():
    """c-db-per-version：比较**永不抛异常**（旧实现在非纯数字段抛 ValueError，
    调用点无保护 → 装 `0.11-beta` 的包点开更新检测即 500）。

    带后缀/非法串一律给出确定序：`0.11-beta < 0.11`、非法串降最低。
    """
    assert uc._has_newer("0.11", "0.11-beta") is True    # rc/beta 早于正式版
    assert uc._has_newer("0.11-beta", "0.11") is False
    assert uc._has_newer("0.11-beta", "0.11-alpha") is True
    assert uc._has_newer("abc", "0.11") is False          # 非法串不新于任何版本
    assert uc._has_newer("0.11", "abc") is True


def test_invalid_version_payload_rejected():
    """载荷校验边界（非比较路径）：非法串拒收，带后缀版本合法。"""
    assert uc.is_valid_version("abc") is False
    assert uc.is_valid_version("") is False
    assert uc.is_valid_version("0.11") is True
    assert uc.is_valid_version("0.11-beta") is True


# ── 出站安全校验（async：DNS 走事件循环，不再阻塞）─────────────────────


def test_non_https_rejected():
    assert _run(uc._validate_outbound_url("http://www.awesomenovel.com/download/latest.json")) is False


def test_untrusted_host_rejected():
    assert _run(uc._validate_outbound_url("https://evil.example.com/latest.json")) is False


def test_private_resolution_rejected(monkeypatch):
    """域名解析到私网地址同样拒绝。"""
    monkeypatch.setattr(
        uc.socket, "getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("192.168.1.5", port))],
    )
    assert _run(uc._validate_outbound_url(MAIN_URL)) is False


def test_loopback_rejected(monkeypatch):
    monkeypatch.setattr(
        uc.socket, "getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("127.0.0.1", port))],
    )
    assert _run(uc._validate_outbound_url(MAIN_URL)) is False


def test_public_resolution_accepted(monkeypatch):
    monkeypatch.setattr(
        uc.socket, "getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("106.55.209.168", port))],
    )
    assert _run(uc._validate_outbound_url(MAIN_URL)) is True


# ── 兜底切换 ─────────────────────────────────────────────────────────────


def test_fallback_switch_on_main_failure(monkeypatch):
    """主域失败 → 切兜底成功；兜底也失败才返回 None。"""
    async def always_ok(url):
        return True

    monkeypatch.setattr(uc, "_validate_outbound_url", always_ok)
    seen = []

    async def fake_fetch_one(url):
        seen.append(url)
        return None if url == MAIN_URL else {"latest": "0.14", "notes": "x"}

    monkeypatch.setattr(uc, "_fetch_one", fake_fetch_one)
    got = _run(uc._fetch_latest())
    assert seen == [MAIN_URL, FALLBACK_URL]
    assert got == {"latest": "0.14", "notes": "x", "source_url": FALLBACK_URL}

    async def all_fail(url):
        seen.append(url)

    monkeypatch.setattr(uc, "_fetch_one", all_fail)
    assert _run(uc._fetch_latest()) is None


def test_fallback_url_also_validated(monkeypatch):
    """兜底地址同样过安全校验：校验不过的直接跳过不发请求。"""
    checks = []

    async def fake_validate(url):
        checks.append(url)
        return False

    monkeypatch.setattr(uc, "_validate_outbound_url", fake_validate)

    async def must_not_call(url):  # pragma: no cover - 到这里即失败
        raise AssertionError("不应发出请求")

    monkeypatch.setattr(uc, "_fetch_one", must_not_call)
    assert _run(uc._fetch_latest()) is None
    assert checks == [MAIN_URL, FALLBACK_URL]


def test_derived_urls_follow_successful_source(monkeypatch):
    """主域配置坏（校验不过）靠兜底成功时，说明页/官网入口按兜底域推导。"""
    async def validate(url):
        return url == FALLBACK_URL

    async def fetch_one(url):
        assert url == FALLBACK_URL
        return {"latest": "0.14", "notes": ""}

    monkeypatch.setattr(uc, "_validate_outbound_url", validate)
    monkeypatch.setattr(uc, "_fetch_one", fetch_one)
    monkeypatch.setenv("CLIENT_VERSION", "0.11")

    st = _run(uc.get_update_state())
    assert st["has_update"] is True
    assert st["notes_url"].startswith(FALLBACK_URL[: -len("latest.json")] + "v0.14/")
    assert st["download_url"] == FALLBACK_URL[: -len("/download/latest.json")]


# ── 关闭记忆 ─────────────────────────────────────────────────────────────


def test_dismiss_version_remembers(monkeypatch):
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    monkeypatch.setattr(uc, "_fetch_latest", _async_returns({"latest": "0.13", "notes": ""}))
    assert _run(uc.get_update_state())["has_update"] is True

    state = json.loads(uc._state_path.read_text(encoding="utf-8"))
    state["dismissed_version"] = "0.13"
    uc._state_path.write_text(json.dumps(state), encoding="utf-8")
    assert _run(uc.get_update_state())["has_update"] is False

    # 新版本 0.14 上线 → 重新提示
    monkeypatch.setattr(uc, "_fetch_latest", _async_returns({"latest": "0.14", "notes": ""}))
    state["last_check_at"] -= 2 * 3600  # 出节流窗
    uc._state_path.write_text(json.dumps(state), encoding="utf-8")
    assert _run(uc.get_update_state())["has_update"] is True


# ── HTTP 端点 ────────────────────────────────────────────────────────────


def _client():
    from fastapi.testclient import TestClient

    from main import app
    return TestClient(app)


def test_endpoint_get_dev():
    with _client() as c:
        r = c.get("/api/update-check")
        assert r.status_code == 200
        assert r.json()["current"] == "dev"
        assert r.json()["has_update"] is False
        assert r.json()["build"] is None  # fixture 缓存复位为 None


def test_endpoint_dev_with_build(monkeypatch):
    """dev 态端点带出构建信息（_payload 路径）。"""
    monkeypatch.setattr(bi, "_git_build", ("main", "f456e"))
    with _client() as c:
        r = c.get("/api/update-check")
        assert r.json()["build"] == {"branch": "main", "commit": "f456e"}


def test_endpoint_tag_build_with_stray_env(monkeypatch):
    """tag 态（真实版本）即使环境残留构建信息 env，载荷 build 仍为 None（dev 总闸）。"""
    monkeypatch.setenv("CLIENT_VERSION", "0.24")
    monkeypatch.setenv("CLIENT_BUILD_BRANCH", "main")
    monkeypatch.setenv("CLIENT_BUILD_COMMIT", "f456e")
    monkeypatch.setattr(uc, "_fetch_latest", _async_returns({"latest": "0.24", "notes": ""}))
    with _client() as c:
        r = c.get("/api/update-check")
        assert r.json()["current"] == "0.24"
        assert r.json()["build"] is None


def test_endpoint_dismiss_roundtrip():
    with _client() as c:
        r = c.post("/api/update-check/dismiss", json={"version": "0.13"})
        assert r.status_code == 200 and r.json() == {"dismissed": "0.13"}
        state = json.loads(uc._state_path.read_text(encoding="utf-8"))
        assert state["dismissed_version"] == "0.13"


def test_endpoint_dismiss_invalid_version_422():
    with _client() as c:
        assert c.post("/api/update-check/dismiss", json={"version": "abc"}).status_code == 422


# ── 手动「检查更新」入口（silent-upgrade P1 首片）─────────────────────────


def test_refresh_bypasses_throttle_and_caches(monkeypatch):
    """节流窗内 fresh 的 last_check_at 拦不住 refresh：照外呼，且结果回写缓存。"""
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    import time as _t
    uc._state_path.write_text(
        json.dumps({"last_check_at": _t.time(), "cached": {"latest": "0.11", "notes": ""}}),
        encoding="utf-8",
    )
    calls = []

    async def fake_fetch():
        calls.append(1)
        return {"latest": "0.13", "notes": "修复", "source_url": MAIN_URL}

    monkeypatch.setattr(uc, "_fetch_latest", fake_fetch)
    r = _run(uc.refresh_update_check())
    assert calls == [1]
    assert r["checked"] is True and r["has_update"] is True and r["latest"] == "0.13"
    saved = json.loads(uc._state_path.read_text(encoding="utf-8"))
    assert saved["cached"]["latest"] == "0.13"


def test_refresh_dev_still_answers(monkeypatch):
    """dev 构建周期横幅照旧跳过，但手动点击照实返回（dev 序最低→任何官方版皆更新）。"""
    monkeypatch.setattr(
        uc, "_fetch_latest",
        _async_returns({"latest": "0.33", "notes": "", "source_url": MAIN_URL}),
    )
    r = _run(uc.refresh_update_check())
    assert r["current"] == "dev" and r["checked"] is True and r["has_update"] is True


def test_refresh_ignores_dismissed(monkeypatch):
    """两路语义分叉：refresh 不查 dismissed（手动＝要看真相）；周期 GET 照旧受其约束。"""
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    uc._state_path.write_text(json.dumps({"dismissed_version": "0.12"}), encoding="utf-8")
    monkeypatch.setattr(
        uc, "_fetch_latest",
        _async_returns({"latest": "0.12", "notes": "", "source_url": MAIN_URL}),
    )
    assert _run(uc.refresh_update_check())["has_update"] is True
    assert _run(uc.get_update_state())["has_update"] is False


def test_refresh_failure_marks_checked_false_and_keeps_cache(monkeypatch):
    """外呼失败→checked=False 且不动缓存（横幅继续吃上一次好结果，失败零污染）。"""
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    uc._state_path.write_text(
        json.dumps({"last_check_at": 0.0, "cached": {"latest": "0.12", "notes": ""}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(uc, "_fetch_latest", _async_returns(None))
    r = _run(uc.refresh_update_check())
    assert r["checked"] is False and r["latest"] is None and r["has_update"] is False
    saved = json.loads(uc._state_path.read_text(encoding="utf-8"))
    assert saved["cached"]["latest"] == "0.12"


def test_endpoint_refresh_roundtrip(monkeypatch):
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    monkeypatch.setattr(
        uc, "_fetch_latest",
        _async_returns({"latest": "0.12", "notes": "", "source_url": MAIN_URL}),
    )
    with _client() as c:
        r = c.post("/api/update-check/refresh")
        assert r.status_code == 200 and r.json()["checked"] is True


# ── P1 第二片：自动下载状态机／触发闸／apply·skip ─────────────────────────


def _manifest(**over):
    base = {"latest": "0.33", "notes": "", "auto_enabled": True,
            "platforms": {"win": {"url": MAIN_URL.replace("latest.json", "pkg.exe"),
                                  "sha256": "", "size": 0}},
            "source_url": MAIN_URL}
    base.update(over)
    return base


def test_trigger_gates(monkeypatch):
    """闸＝is_newer × auto_enabled × 本平台包 × 未 skip × 未 staged 同版本；任一不过零线程。"""
    monkeypatch.setattr(uc, "_PLATFORM_KEY", "win")
    started = []
    done = threading.Event()

    def fake_worker(version, platform, epoch):
        started.append((version, platform, epoch))
        done.set()

    monkeypatch.setattr(uc, "_download_worker", fake_worker)

    def _state(**over):
        st = {"auto": {"state": "idle", "version": None}}
        st.update(over)
        uc._state_path.write_text(json.dumps(st), encoding="utf-8")

    uc.maybe_start_auto_download(_manifest(latest="0.11"), current="0.33")  # 不比当前新
    uc.maybe_start_auto_download(_manifest(auto_enabled=False), current="0.11")
    uc.maybe_start_auto_download(_manifest(platforms=None), current="0.11")
    uc.maybe_start_auto_download(_manifest(platforms={"mac": None}), current="0.11")
    _state(skipped_version="0.33")
    uc.maybe_start_auto_download(_manifest(), current="0.11")
    _state(auto={"state": "staged", "version": "0.33"})
    uc.maybe_start_auto_download(_manifest(), current="0.11")
    assert started == []

    _state()
    uc.maybe_start_auto_download(_manifest(), current="0.11")
    assert done.wait(timeout=5)
    version, platform, _epoch = started[0]
    assert version == "0.33" and platform["url"].endswith("pkg.exe")


def test_platform_keys_cover_windows_and_macos():
    """平台映射（c-mac-autoupdate）：darwin → "mac"（与发布清单 platforms.* 键名一致）；
    其余平台不在表内＝自动链关闭、手动链照旧。"""
    assert uc._PLATFORM_KEYS == {"win32": "win", "darwin": "mac"}
    assert "linux" not in uc._PLATFORM_KEYS


def test_trigger_gates_macos(monkeypatch):
    """macOS 键驱动同一触发闸：platforms.mac 在册即下载（包取 mac 键）。"""
    monkeypatch.setattr(uc, "_PLATFORM_KEY", "mac")
    started = []
    done = threading.Event()

    def fake_worker(version, platform, epoch):
        started.append((version, platform, epoch))
        done.set()

    monkeypatch.setattr(uc, "_download_worker", fake_worker)
    manifest = _manifest(platforms={"mac": {"url": MAIN_URL.replace(
        "latest.json", "AwesomeNovel_mac_v0.33.dmg"), "sha256": "", "size": 0}})
    uc.maybe_start_auto_download(manifest, current="0.11")
    assert done.wait(timeout=5)
    _version, platform, _epoch = started[0]
    assert platform["url"].endswith("AwesomeNovel_mac_v0.33.dmg")

    # mac 键不在册＝不触发（零线程）
    started.clear()
    uc.maybe_start_auto_download(_manifest(platforms={"win": {"url": "https://x/pkg.exe"}}),
                                 current="0.11")
    assert started == []


def test_download_worker_stages_verified_package(monkeypatch, tmp_path):
    """成功路径：.part→原子改名→sha 对上→staged；内容逐字节等于喂进来的流。"""
    payload = b"PKG-BYTES"
    want = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(uc, "_UPDATES_DIR", tmp_path)
    monkeypatch.setattr(uc, "_PENDING_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(uc, "_APPLIED_PATH", tmp_path / "applied.json")
    monkeypatch.setattr(uc, "_state_path", tmp_path / "update-check.json")
    # 直调 worker：把跨用例残留的取消位/代际号复位（worker 入口即查这两样）
    monkeypatch.setattr(uc, "_dl_cancel", threading.Event())
    monkeypatch.setattr(uc, "_dl_epoch", 1)

    class _Resp:
        status_code = 200
        headers: ClassVar[dict] = {"content-length": str(len(payload))}
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def iter_bytes(self, n):
            yield payload

    class _Client:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def stream(self, method, url):
            return _Resp()

    monkeypatch.setattr(uc.httpx, "Client", _Client)
    platform = {"url": "https://host.example/pkg.exe", "sha256": want, "size": len(payload)}
    uc._download_worker("0.33", platform, epoch=1)
    dest = tmp_path / "pkg.exe"
    assert dest.read_bytes() == payload
    state = json.loads((tmp_path / "update-check.json").read_text(encoding="utf-8"))
    assert state["auto"]["state"] == "staged"
    assert state["auto"]["version"] == "0.33"


def test_download_worker_quarantines_sha_mismatch(monkeypatch, tmp_path):
    """sha 不符＝隔离件＋退避重试；超限＝failed（attempts exhausted）。"""
    monkeypatch.setattr(uc, "_UPDATES_DIR", tmp_path)
    monkeypatch.setattr(uc, "_state_path", tmp_path / "update-check.json")
    monkeypatch.setattr(uc, "_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(uc.time, "sleep", lambda s: None)
    monkeypatch.setattr(uc, "_dl_cancel", threading.Event())
    monkeypatch.setattr(uc, "_dl_epoch", 1)

    class _Resp:
        status_code = 200
        headers: ClassVar[dict] = {"content-length": "8"}
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def iter_bytes(self, n):
            yield b"TAMPERED"

    class _Client:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def stream(self, method, url):
            return _Resp()

    monkeypatch.setattr(uc.httpx, "Client", _Client)
    platform = {"url": "https://host.example/pkg.exe", "sha256": "0" * 64, "size": 8}
    uc._download_worker("0.33", platform, epoch=1)
    state = json.loads((tmp_path / "update-check.json").read_text(encoding="utf-8"))
    assert state["auto"]["state"] == "failed"
    assert (tmp_path / "pkg.exe.quarantine").exists()


def test_apply_writes_pending_and_refuses_when_gate_closed(monkeypatch, tmp_path):
    """apply：staged＋manifest 对得上→pending 落盘（一次性＋TTL 字段）；渠道不可达→409。"""
    payload = b"PKG"
    pkg = tmp_path / "pkg.exe"
    pkg.write_bytes(payload)
    monkeypatch.setattr(uc, "_UPDATES_DIR", tmp_path)
    monkeypatch.setattr(uc, "_PENDING_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(uc, "_APPLIED_PATH", tmp_path / "applied.json")
    monkeypatch.setattr(uc, "_state_path", tmp_path / "update-check.json")
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    monkeypatch.setattr(uc, "_PLATFORM_KEY", "win")  # 测试机无关：钉平台键
    (tmp_path / "update-check.json").write_text(
        json.dumps({"auto": {"state": "staged", "version": "0.33"}}), encoding="utf-8")
    monkeypatch.setattr(
        uc, "_fetch_latest",
        _async_returns(_manifest(platforms={
            "win": {"url": "https://host.example/pkg.exe",
                    "sha256": hashlib.sha256(payload).hexdigest(), "size": 3}})),
    )
    r = _run(uc.apply_update())
    assert r == {"ok": True, "version": "0.33"}
    pending = json.loads((tmp_path / "pending.json").read_text(encoding="utf-8"))
    assert pending["relaunch"] is True and pending["version"] == "0.33"
    assert pending["file"] == str(pkg) and pending["issued_at"] > 0
    assert pending["sha256"] == hashlib.sha256(payload).hexdigest()

    monkeypatch.setattr(uc, "_fetch_latest", _async_returns(None))
    import pytest as _pytest
    with _pytest.raises(uc.HTTPException) as ei:
        _run(uc.apply_update())
    assert ei.value.status_code == 409


def test_auto_skip_cancels_and_cleans(monkeypatch, tmp_path):
    """「暂不」：记 skip＋auto 回 idle＋删暂存件（保留 applied 历史）。"""
    updates = tmp_path / "updates"  # 生产布局：暂存目录≠状态文件所在目录
    updates.mkdir()
    monkeypatch.setattr(uc, "_UPDATES_DIR", updates)
    monkeypatch.setattr(uc, "_PENDING_PATH", updates / "pending.json")
    monkeypatch.setattr(uc, "_APPLIED_PATH", updates / "applied.json")
    monkeypatch.setattr(uc, "_state_path", tmp_path / "update-check.json")
    (updates / "pkg.exe").write_bytes(b"x")
    (updates / "applied.json").write_text("{}", encoding="utf-8")
    (tmp_path / "update-check.json").write_text(
        json.dumps({"auto": {"state": "staged", "version": "0.33"}}), encoding="utf-8")
    r = _run(uc.auto_skip_update(uc.SkipIn(version="0.33")))
    assert r == {"skipped": "0.33"}
    state = json.loads((tmp_path / "update-check.json").read_text(encoding="utf-8"))
    assert state["skipped_version"] == "0.33" and state["auto"]["state"] == "idle"
    assert not (updates / "pkg.exe").exists()
    assert (updates / "applied.json").exists()


def test_auto_public_state_applied_marker_wins(monkeypatch, tmp_path):
    """applied 记账语义（10-15 真机实锤修正）：marker 只在「没有更新的 staged」时生效。

    反例即本次事故：0.99.1 的 marker 永久压住 staged 0.99.4 → 「已就绪」按钮永不可见。
    """
    monkeypatch.setattr(uc, "_UPDATES_DIR", tmp_path)
    monkeypatch.setattr(uc, "_PENDING_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(uc, "_APPLIED_PATH", tmp_path / "applied.json")
    monkeypatch.setattr(uc, "_state_path", tmp_path / "update-check.json")

    def _seed(auto):
        (tmp_path / "update-check.json").write_text(
            json.dumps({"auto": auto}), encoding="utf-8")

    _seed({"state": "staged", "version": "0.33"})
    assert uc.auto_public_state() == {"state": "staged", "version": "0.33"}
    (tmp_path / "applied.json").write_text(
        json.dumps({"version": "0.33"}), encoding="utf-8")
    assert uc.auto_public_state() == {"state": "applied", "version": "0.33"}

    # staged 比已记账版本新 → staged 优先（就绪按钮必须可见）
    _seed({"state": "staged", "version": "0.34"})
    assert uc.auto_public_state() == {"state": "staged", "version": "0.34"}


# ── 评审补臂（四路评审测试缺口清单）────────────────────────────────────────


def test_trigger_dev_build_vetoed(monkeypatch):
    """R7：dev/冒烟（无版本语义）即使清单含本平台包也一票否决自动链（真机击穿实锤）。"""
    monkeypatch.setattr(uc, "_PLATFORM_KEY", "win")
    started = []
    done = threading.Event()

    def fake_worker(version, platform, epoch):
        started.append(1)
        done.set()

    monkeypatch.setattr(uc, "_download_worker", fake_worker)
    uc.maybe_start_auto_download(_manifest(), current="dev")
    assert not done.wait(timeout=1)


def test_download_worker_disk_full_aborts(monkeypatch, tmp_path):
    """R1 环境类失败：磁盘不足直接 failed 等下窗，不进重试循环。"""
    monkeypatch.setattr(uc, "_UPDATES_DIR", tmp_path)
    monkeypatch.setattr(uc, "_state_path", tmp_path / "update-check.json")
    monkeypatch.setattr(uc, "_dl_cancel", threading.Event())
    monkeypatch.setattr(uc, "_dl_epoch", 1)

    class _FakeUsage:
        free = 1  # 1 字节可用 < 任何安全倍数

    monkeypatch.setattr(uc.shutil, "disk_usage", lambda _p: _FakeUsage())
    called = []

    def _fail_stream(*a, **k):
        called.append(1)
        raise AssertionError("磁盘不足必须终止，不得发起下载")

    class _Client:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def stream(self, method, url):
            return _fail_stream(method, url)

    monkeypatch.setattr(uc.httpx, "Client", _Client)
    platform = {"url": "https://host.example/pkg.exe", "sha256": "", "size": 10**9}
    uc._download_worker("0.33", platform, epoch=1)
    state = json.loads((tmp_path / "update-check.json").read_text(encoding="utf-8"))
    assert state["auto"]["state"] == "failed" and state["auto"]["last_error"] == "disk full"
    assert called == []


def test_apply_auto_enabled_false_is_hard_409(monkeypatch, tmp_path):
    """R2：发布侧总闸显式关闭＝硬拒绝（区别于渠道抖动的缓存降级）。"""
    pkg = tmp_path / "pkg.exe"
    pkg.write_bytes(b"x")
    monkeypatch.setattr(uc, "_UPDATES_DIR", tmp_path)
    monkeypatch.setattr(uc, "_PENDING_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(uc, "_APPLIED_PATH", tmp_path / "applied.json")
    monkeypatch.setattr(uc, "_state_path", tmp_path / "update-check.json")
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    monkeypatch.setattr(uc, "_PLATFORM_KEY", "win")
    (tmp_path / "update-check.json").write_text(
        json.dumps({"auto": {"state": "staged", "version": "0.33"},
                    "cached": {"latest": "0.33", "auto_enabled": False,
                               "platforms": {"win": {"url": "https://h/p.exe",
                                                     "sha256": "", "size": 0}}}}),
        encoding="utf-8")

    def _fetch_offline():
        return None

    monkeypatch.setattr(uc, "_fetch_latest", _fetch_offline)
    import pytest as _pytest
    # 渠道抖动（重取 None）＋缓存有清单 → 降级消费缓存而非拒绝
    monkeypatch.setattr(
        uc, "_fetch_latest",
        _async_returns(None))
    # 缓存里 auto_enabled=True 的情形
    (tmp_path / "update-check.json").write_text(
        json.dumps({"auto": {"state": "staged", "version": "0.33"},
                    "cached": {"latest": "0.33", "auto_enabled": True,
                               "notes": "", "source_url": MAIN_URL,
                               "platforms": {"win": {"url": "https://host.example/pkg.exe",
                                                     "sha256": "", "size": 1}}}}),
        encoding="utf-8")
    pkg.write_bytes(b"y")
    monkeypatch.setattr(
        uc, "_fetch_latest", _async_returns(None))
    r = _run(uc.apply_update())
    assert r == {"ok": True, "version": "0.33"}

    # 缓存里 auto_enabled=False → 硬 409
    (tmp_path / "update-check.json").write_text(
        json.dumps({"auto": {"state": "staged", "version": "0.33"},
                    "cached": {"latest": "0.33", "auto_enabled": False,
                               "platforms": {"win": {"url": "https://h/p.exe",
                                                     "sha256": "", "size": 0}}}}),
        encoding="utf-8")
    monkeypatch.setattr(uc, "_fetch_latest", _async_returns(None))
    with _pytest.raises(uc.HTTPException) as ei:
        _run(uc.apply_update())
    assert ei.value.status_code == 409


def test_channel_self_report_logs(monkeypatch, tmp_path, caplog):
    """渠道自报日志：成功行含渠道地址与版本；全不可达落警告。"""
    monkeypatch.setenv("CLIENT_VERSION", "0.11")
    monkeypatch.setattr(uc, "_state_path", tmp_path / "update-check.json")

    # 桩内层（_fetch_one/出站校验），让真 _fetch_latest 跑——日志行在它体内
    async def ok_one(url):
        return {"latest": "0.33", "notes": "", "platforms": None, "auto_enabled": True}

    async def ok_validate(url):
        return True

    monkeypatch.setattr(uc, "_fetch_one", ok_one)
    monkeypatch.setattr(uc, "_validate_outbound_url", ok_validate)
    import logging
    with caplog.at_level(logging.INFO, logger="update_check"):
        _run(uc.refresh_update_check())
    assert any("update-check: channel=" in r.message and "0.33" in r.message
               for r in caplog.records)

    async def none_one(url):
        return None

    monkeypatch.setattr(uc, "_fetch_one", none_one)
    with caplog.at_level(logging.WARNING, logger="update_check"):
        _run(uc.refresh_update_check())
    assert any("渠道全部不可达" in r.message for r in caplog.records)


def test_trigger_v1_manifest_logs_and_skips(monkeypatch, caplog):
    """旧代载荷（无 platforms）：自动链禁用且留日志，手动链不受影响。"""
    monkeypatch.setattr(uc, "_PLATFORM_KEY", "win")
    started = []
    done = threading.Event()

    def fake_worker(version, platform, epoch):
        started.append(1)
        done.set()

    monkeypatch.setattr(uc, "_download_worker", fake_worker)
    import logging
    with caplog.at_level(logging.INFO, logger="update_check"):
        uc.maybe_start_auto_download(_manifest(platforms=None), current="0.11")
    assert not done.wait(timeout=1)
    assert any("manifest v1" in r.message for r in caplog.records)


def test_stale_downloading_state_falls_back_to_idle(monkeypatch, tmp_path):
    """进程中断残留的 downloading：无存活执行体 → 查询回落 idle（不卡「下载 0%」）。"""
    monkeypatch.setattr(uc, "_UPDATES_DIR", tmp_path)
    monkeypatch.setattr(uc, "_PENDING_PATH", tmp_path / "pending.json")
    monkeypatch.setattr(uc, "_APPLIED_PATH", tmp_path / "applied.json")
    monkeypatch.setattr(uc, "_state_path", tmp_path / "update-check.json")
    (tmp_path / "update-check.json").write_text(
        json.dumps({"auto": {"state": "downloading", "version": "0.99.4",
                             "received": 1, "total": 100}}),
        encoding="utf-8")
    monkeypatch.setattr(uc, "_dl_thread", None)  # 无存活执行体（进程中断残留）
    assert uc.auto_public_state() == {"state": "idle", "version": None}

    block = threading.Event()
    fake_thread = threading.Thread(target=block.wait, daemon=True)
    fake_thread.start()
    try:
        monkeypatch.setattr(uc, "_dl_thread", fake_thread)
        assert uc.auto_public_state() == {"state": "downloading", "version": "0.99.4",
                                          "received": 1, "total": 100}
    finally:
        block.set()
        fake_thread.join(timeout=5)


def test_trigger_skips_redownload_while_pending_in_flight(monkeypatch):
    """pending 在场＝用户已确认在途：新一代检出 MUST NOT 覆盖暂存件（三轮检视实锤）。"""
    monkeypatch.setattr(uc, "_PLATFORM_KEY", "win")
    done = threading.Event()

    def fake_worker(version, platform, epoch):
        done.set()

    monkeypatch.setattr(uc, "_download_worker", fake_worker)
    uc._state_path.write_text(
        json.dumps({"auto": {"state": "staged", "version": "0.33"},
                    "pending": {"version": "0.33"}}),
        encoding="utf-8")
    uc._PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    uc._PENDING_PATH.write_text("{}", encoding="utf-8")
    uc.maybe_start_auto_download(_manifest(), current="0.11")
    assert not done.wait(timeout=1)


# ── 签名链（tasks 2.2/2.3）────────────────────────────────────────────────


def _signed_manifest(monkeypatch, *, auto_enabled=True, sign=True):
    import base64 as _b64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    priv_b64 = _b64.b64encode(key.private_bytes_raw()).decode()
    pub_b64 = _b64.b64encode(key.public_key().public_bytes_raw()).decode()
    monkeypatch.setenv("CLIENT_UPDATE_PUBKEYS",
                       json.dumps({"update-k1": pub_b64}))
    manifest = {"latest": "0.33", "notes": "", "auto_enabled": auto_enabled,
                "platforms": {"win": {"url": MAIN_URL.replace("latest.json", "pkg.exe"),
                                      "sha256": "", "size": 0}},
                "source_url": MAIN_URL}
    if sign:
        signed = dict(manifest)
        signed["signer_key_id"] = "update-k1"
        signed["signature"] = base64.b64encode(
            Ed25519PrivateKey.from_private_bytes(_b64.b64decode(priv_b64)).sign(
                __import__("json").dumps(
                    {k: v for k, v in signed.items() if k != "signature"},
                    sort_keys=True, separators=(",", ":")).encode("utf-8")
            )).decode()
        return manifest, signed
    return manifest, manifest


def _make_keys_and_signed(monkeypatch, *, sign=True):
    """生成钥对＋按客户端 canonical 规则签名的 v2 清单；注入 CLIENT_UPDATE_PUBKEYS。"""
    import base64 as _b64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    priv_b64 = _b64.b64encode(key.private_bytes_raw()).decode()
    pub_b64 = _b64.b64encode(key.public_key().public_bytes_raw()).decode()
    monkeypatch.setenv("CLIENT_UPDATE_PUBKEYS", json.dumps({"update-k1": pub_b64}))
    manifest = {"version": "0.33", "notes": "", "auto_enabled": True,
                "platforms": {"win": {"url": MAIN_URL.replace("latest.json", "pkg.exe"),
                                      "sha256": "", "size": 0}}}
    raw = dict(manifest)
    if sign:
        raw["signer_key_id"] = "update-k1"
        raw["signature"] = base64.b64encode(
            Ed25519PrivateKey.from_private_bytes(_b64.b64decode(priv_b64)).sign(
                json.dumps({k: v for k, v in raw.items() if k != "signature"},
                           sort_keys=True, separators=(",", ":")).encode("utf-8")
            )).decode()
    return raw


def _stub_http_json(monkeypatch, payload):
    """按真 _fetch_one 的调用形态打桩：build_async_client → await client.get → json()。"""
    class _Resp:
        status_code = 200
        def __init__(self, pl):
            self._pl = pl
        def json(self):
            return self._pl

    class _Client:
        def __init__(self, pl):
            self._pl = pl
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def get(self, url):
            return _Resp(self._pl)

    monkeypatch.setattr(uc, "build_async_client", lambda timeout=None, **k: _Client(payload))


def test_fetch_v2_unsigned_manifest_rejected(monkeypatch, caplog):
    """v2 清单（含平台包）无有效签名 → _fetch_one 返回 None（自动链硬停＋日志）。"""
    raw = _make_keys_and_signed(monkeypatch, sign=False)
    _stub_http_json(monkeypatch, raw)
    import logging
    with caplog.at_level(logging.WARNING, logger="update_check"):
        got = _run(uc._fetch_one(MAIN_URL))
    assert got is None
    assert any("SIGNATURE REJECT" in r.message for r in caplog.records)


def test_fetch_v2_signed_manifest_accepted(monkeypatch):
    """有效签名 → 正常解析（平台/总闸透传给自动链）。"""
    raw = _make_keys_and_signed(monkeypatch, sign=True)
    _stub_http_json(monkeypatch, raw)
    got = _run(uc._fetch_one(MAIN_URL))
    assert got["latest"] == "0.33" and got["auto_enabled"] is True
    assert got["platforms"]["win"]["url"].endswith("pkg.exe")
    assert got["_raw"]["signature"] == raw["signature"]


def test_fetch_v1_manifest_needs_no_signature(monkeypatch):
    """v1 清单（无 platforms）：不要求签名，照常解析（自动链由 platforms 缺失禁用）。"""
    _make_keys_and_signed(monkeypatch, sign=False)
    _stub_http_json(monkeypatch, {"version": "0.33", "notes": ""})
    got = _run(uc._fetch_one(MAIN_URL))
    assert got["latest"] == "0.33" and got["platforms"] is None


def test_update_pubkeys_env_parsing(monkeypatch):
    """信任集合 env：合法 JSON 解析为 {kid: bytes}；非法/缺失＝空集合（安全默认）。"""
    monkeypatch.setenv("CLIENT_UPDATE_PUBKEYS",
                       '{"update-k1":"Ktq81Y4Qf9cPapmfbLw2h4SGGo1E72X3HaGUxOBU/EU="}')
    keys = uc._update_pubkeys()
    assert set(keys) == {"update-k1"} and len(keys["update-k1"]) == 32
    monkeypatch.setenv("CLIENT_UPDATE_PUBKEYS", "not-json")
    assert uc._update_pubkeys() == {}
    monkeypatch.delenv("CLIENT_UPDATE_PUBKEYS")
    assert uc._update_pubkeys() == {}


def test_fetch_v2_empty_pubkeys_fail_closed(monkeypatch, caplog):
    """fail-closed：空钥集合（env 非法/缺失）时 v2 清单一律 REJECT，绝不 fail-open。"""
    raw = _make_keys_and_signed(monkeypatch, sign=True)  # 有签名的 v2 清单
    monkeypatch.setenv("CLIENT_UPDATE_PUBKEYS", "corrupted-not-json")  # 钥非法
    _stub_http_json(monkeypatch, raw)
    import logging
    with caplog.at_level(logging.WARNING, logger="update_check"):
        got = _run(uc._fetch_one(MAIN_URL))
    assert got is None
    assert any("SIGNATURE REJECT" in r.message for r in caplog.records)

    monkeypatch.delenv("CLIENT_UPDATE_PUBKEYS")  # 钥缺失
    got = _run(uc._fetch_one(MAIN_URL))
    assert got is None


# ── 换代清账：异源/过期 staged 残留清理（真机实证：lab E2E 残留 0.99.5 横幅不灭）──


def test_stale_staged_cleared_when_no_update(monkeypatch):
    """运行版≥检测版（无更新）时，残留 staged 状态必须清账——横幅不能永久挂异渠道版本。"""
    monkeypatch.setenv("CLIENT_VERSION", "0.34.2")
    monkeypatch.setattr(uc, "_CHECK_INTERVAL", 0)
    uc._state_path.parent.mkdir(parents=True, exist_ok=True)
    uc._state_path.write_text(
        json.dumps({"auto": {"state": "staged", "version": "0.99.5"}}),
        encoding="utf-8",
    )

    async def fake_fetch():
        return {"latest": "0.34.2", "notes": "", "source_url": MAIN_URL}

    monkeypatch.setattr(uc, "_fetch_latest", fake_fetch)
    got = _run(uc.get_update_state())
    assert got["auto"]["state"] == "idle"
    st = json.loads(uc._state_path.read_text(encoding="utf-8"))
    assert st["auto"]["state"] == "idle"


# ── c-update-detached-ps-fix：last_install_attempt 诊断字段 ──────────────────


def _bake_version_and_fetch(monkeypatch):
    monkeypatch.setenv("CLIENT_VERSION", "0.39")
    monkeypatch.setattr(uc, "_fetch_latest",
                        _async_returns({"latest": "0.39", "notes": ""}))


def test_state_merges_last_install_attempt(monkeypatch, tmp_path):
    """执行记录在场 → 状态并入 last_install_attempt 只读字段（形状原样透传）。"""
    _bake_version_and_fetch(monkeypatch)
    updates = tmp_path / "updates"
    updates.mkdir()
    (updates / "last-install-attempt.json").write_text(json.dumps(
        {"version": "0.39", "attempts": 1, "runner_started": False,
         "installer_exit": None, "recorded_at": 1.0}), encoding="utf-8")
    monkeypatch.setattr(uc, "_UPDATES_DIR", updates)
    st = _run(uc.get_update_state())
    assert st["last_install_attempt"]["runner_started"] is False
    assert st["last_install_attempt"]["attempts"] == 1


def test_state_omits_last_install_attempt_when_absent(monkeypatch, tmp_path):
    """文件缺失＝键不出现（非 null 占位）——存量状态形状全等断言依赖。"""
    _bake_version_and_fetch(monkeypatch)
    monkeypatch.setattr(uc, "_UPDATES_DIR", tmp_path / "updates")
    st = _run(uc.get_update_state())
    assert "last_install_attempt" not in st
