"""release.json 发布期注入的读取逻辑（config.load_release_overrides）。"""
from config import load_release_overrides


def _write(tmp_path, body):
    p = tmp_path / "release.json"
    p.write_text(body, encoding="utf-8")
    return str(tmp_path)


def test_missing_file_returns_empty(tmp_path):
    assert load_release_overrides(str(tmp_path / "nope")) == {}


def test_valid_file_reads_nonempty_values_only(tmp_path):
    d = _write(tmp_path, '{"server_api_base": " https://www.example.com/api ", '
                          '"server_api_fallback": "", "public_server_api": null}')
    assert load_release_overrides(d) == {"server_api_base": "https://www.example.com/api"}


def test_unknown_and_malformed_are_tolerated(tmp_path):
    d = _write(tmp_path, '{"weird_key": 1, "server_api_base": "https://a.com/api", "extra": [1]}')
    assert load_release_overrides(d) == {"server_api_base": "https://a.com/api"}
    bad = _write(tmp_path, "{not json")
    assert load_release_overrides(bad) == {}
    nonobj = _write(tmp_path, '["array"]')
    assert load_release_overrides(nonobj) == {}


def test_client_update_keys_roundtrip(tmp_path):
    """client-update-notify 三键随 release.json 读取，空值/缺失容忍（→ 应用侧回退 dev/默认域）。"""
    d = _write(tmp_path, '{"client_version": "0.13", '
                          '"client_update_url": "https://www.awesomenovel.com/download/latest.json", '
                          '"client_update_url_fallback": "  ", "other": 1}')
    assert load_release_overrides(d) == {
        "client_version": "0.13",
        "client_update_url": "https://www.awesomenovel.com/download/latest.json",
    }


def test_build_info_keys_roundtrip(tmp_path):
    """c-version-build-info：构建信息两键必须过白名单——漏登记=打包链静默断链（评审 P0）。"""
    d = _write(tmp_path, '{"client_build_branch": "pr-123", '
                          '"client_build_commit": "f456e", '
                          '"client_version": "dev", "components": {}}')
    assert load_release_overrides(d) == {
        "client_version": "dev",
        "client_build_branch": "pr-123",
        "client_build_commit": "f456e",
    }


def test_pywebview_injects_build_info_env(tmp_path, monkeypatch):
    """注入段实跑（必选，不留 code review 逃生门）：假 release.json →
    pywebview_app 注入段的**真源码行**把 CLIENT_BUILD_* 写进 env。"""
    import os
    import re as _re
    import textwrap
    from pathlib import Path

    d = _write(tmp_path, '{"client_build_branch": "main", "client_build_commit": "f456e"}')
    loaded = load_release_overrides(d)
    assert loaded["client_build_branch"] == "main"

    src = (Path(__file__).resolve().parent.parent.parent
           / "packaging" / "build" / "pywebview_app.py").read_text(encoding="utf-8")
    m = _re.search(r"( *def _env_with_release\(.*?\n)(?=        _env_with_release\()", src, _re.DOTALL)
    assert m, "pywebview_app.py 注入段结构变了——本测试须同批更新"
    injected = [_re.search(r'_env_with_release\("CLIENT_BUILD_BRANCH".*', src),
                _re.search(r'_env_with_release\("CLIENT_BUILD_COMMIT".*', src)]
    assert all(injected), "pywebview_app.py 缺 CLIENT_BUILD_* 注入行——打包链断链"

    for env in ("CLIENT_BUILD_BRANCH", "CLIENT_BUILD_COMMIT"):
        monkeypatch.delenv(env, raising=False)
    globs = {"os": os, "release": loaded}
    # 注入段实跑＝对 pywebview_app.py 真·源码行执行（S102 有意为之）
    exec(compile(textwrap.dedent(m.group(1)), "<injection-smoke>", "exec"), globs)  # noqa: S102
    for line in (injected[0].group(0).strip(), injected[1].group(0).strip()):
        exec(compile(line, "<injection-smoke>", "exec"), globs)  # noqa: S102
    assert os.environ.get("CLIENT_BUILD_BRANCH") == "main"
    assert os.environ.get("CLIENT_BUILD_COMMIT") == "f456e"
