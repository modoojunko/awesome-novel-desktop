"""build_info：构建信息自报专项矩阵（c-version-build-info）。

覆盖 dev 总闸 / env 成对与半配置 / env 清洗 / git 打桩（含 `/` 分支与长 commit）/
frozen 跳过 / 缓存复位。git 一律打桩——真读仓库会让结果随检出状态漂。
"""

import subprocess

import pytest

import build_info as bi


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    """缓存复位＋新 env 删除，用例间互不污染。"""
    monkeypatch.delenv("CLIENT_BUILD_BRANCH", raising=False)
    monkeypatch.delenv("CLIENT_BUILD_COMMIT", raising=False)
    monkeypatch.setattr(bi, "_git_build", bi._UNSET)
    yield


def _stub_git(monkeypatch, result):
    monkeypatch.setattr(bi, "_git_build", result)


# ── dev 总闸 ─────────────────────────────────────────────────────────────


def test_tag_build_returns_none_even_with_env(monkeypatch):
    monkeypatch.setenv("CLIENT_BUILD_BRANCH", "main")
    monkeypatch.setenv("CLIENT_BUILD_COMMIT", "f456e")
    assert bi.get_build_info("0.24") is None


def test_tag_build_returns_none_even_with_git(monkeypatch):
    _stub_git(monkeypatch, ("main", "f456e"))
    assert bi.get_build_info("0.24.1") is None


# ── env 路径 ─────────────────────────────────────────────────────────────


def test_env_pair_used_and_cleaned(monkeypatch):
    monkeypatch.setenv("CLIENT_BUILD_BRANCH", "release/1.0 实验")
    monkeypatch.setenv("CLIENT_BUILD_COMMIT", "F456E8FA9B")
    got = bi.get_build_info("dev")
    assert got == {"branch": "release-1.0---", "commit": "f456e8fa9b"}


def test_env_half_config_falls_to_git(monkeypatch):
    """只设一个键按缺失处理（展示格式需要成对，有意为之）。"""
    monkeypatch.setenv("CLIENT_BUILD_BRANCH", "main")
    _stub_git(monkeypatch, ("dev-branch", "abc12"))
    assert bi.get_build_info("dev") == {"branch": "dev-branch", "commit": "abc12"}


def test_env_bad_commit_falls_to_git(monkeypatch):
    monkeypatch.setenv("CLIENT_BUILD_BRANCH", "main")
    monkeypatch.setenv("CLIENT_BUILD_COMMIT", "zzzzz")  # 非 hex
    _stub_git(monkeypatch, ("gitb", "f456e"))
    assert bi.get_build_info("dev") == {"branch": "gitb", "commit": "f456e"}


def test_env_blank_branch_falls_to_git(monkeypatch):
    """空白分支 env strip 后为空 → env 对不可用，落 git。"""
    monkeypatch.setenv("CLIENT_BUILD_BRANCH", "   ")
    monkeypatch.setenv("CLIENT_BUILD_COMMIT", "f456e")
    _stub_git(monkeypatch, ("gitb", "f456e"))
    assert bi.get_build_info("dev") == {"branch": "gitb", "commit": "f456e"}


# ── git 路径（打桩，不清洗 `/`）──────────────────────────────────────────


def test_git_branch_with_slash_not_mangled(monkeypatch):
    _stub_git(monkeypatch, ("feature/long-name", "f456e8f"))
    got = bi.get_build_info("dev")
    assert got == {"branch": "feature/long-name", "commit": "f456e8f"}  # 展示端再截 5


def test_git_none(monkeypatch):
    _stub_git(monkeypatch, None)
    assert bi.get_build_info("dev") is None


def test_git_read_once_real_logic(monkeypatch):
    """_read_git_build_once 的 subprocess 分支：打桩 subprocess 验证解析与静默。"""
    def fake_run_ok(args, **kw):
        out = "f456e8fa9b\n" if "--short=5" in args else "feature/foo\n"
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(bi.subprocess, "run", fake_run_ok)
    assert bi._read_git_build_once() == ("feature/foo", "f456e8fa9b")


def test_git_read_once_silent_on_missing_git(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(bi.subprocess, "run", boom)
    assert bi._read_git_build_once() is None


def test_git_read_once_silent_on_timeout(monkeypatch):
    def slow(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="git", timeout=2)

    monkeypatch.setattr(bi.subprocess, "run", slow)
    assert bi._read_git_build_once() is None


def test_git_read_once_rejects_dirty_commit(monkeypatch):
    def fake_run(args, **kw):
        out = "zzzzz\n" if "--short=5" in args else "main\n"
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(bi.subprocess, "run", fake_run)
    assert bi._read_git_build_once() is None


def test_git_read_once_skipped_when_frozen(monkeypatch):
    monkeypatch.setattr(bi.sys, "frozen", True, raising=False)

    def must_not_call(*a, **kw):  # pragma: no cover - 到这里即失败
        raise AssertionError("frozen 包不应尝试读 git")

    monkeypatch.setattr(bi.subprocess, "run", must_not_call)
    assert bi._read_git_build_once() is None


# ── 缓存 ────────────────────────────────────────────────────────────────


def test_git_cache_read_once(monkeypatch):
    """缓存生效：第二次读取不再走 _read_git_build_once。"""
    calls = []

    def fake_once():
        calls.append(1)
        return ("main", "f456e")

    monkeypatch.setattr(bi, "_read_git_build_once", fake_once)
    assert bi._read_git_build() == ("main", "f456e")
    assert bi._read_git_build() == ("main", "f456e")
    assert len(calls) == 1
