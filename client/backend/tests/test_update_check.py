"""client-update-notify：版本自报、节流、出站校验、版本比较、关闭记忆、兜底切换。"""

import asyncio
import json

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
                  "notes": "", "notes_url": "", "download_url": "", "build": None}
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
