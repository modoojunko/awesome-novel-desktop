"""release.json 发布期注入的读取逻辑（config.load_release_overrides）。"""
import json

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


def test_pack_pubkeys_roundtrip(tmp_path):
    """c-prompt-pack-delivery：验签公钥必须过白名单——漏登记=pywebview 注入静默断链
    → 打包端恒无钥可验（AI 永久未就绪）。值形态=JSON 串（各键统一字符串值）。"""
    raw = '{"pack-k1":"UaJFasM5PBIB3Tg1o03cjG6Opeq5CaKtPv2ooLyNPPM="}'
    d = _write(tmp_path, json.dumps({"pack_pubkeys": raw, "components": {}}))
    assert load_release_overrides(d) == {"pack_pubkeys": raw}


def test_pywebview_injects_pack_pubkeys_env(tmp_path, monkeypatch):
    """注入段实跑（同构建信息键判例）：假 release.json → pywebview_app 注入段的
    **真源码行**把 CLIENT_PACK_PUBKEYS 写进 env；release.json 缺烘焙时回落生产常量。"""
    import ast
    import os
    import re as _re
    import textwrap
    from pathlib import Path

    baked = '{"pack-k1":"AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="}'
    src = (Path(__file__).resolve().parent.parent.parent
           / "packaging" / "build" / "pywebview_app.py").read_text(encoding="utf-8")
    m = _re.search(r"( *def _env_with_release\(.*?\n)(?=        _env_with_release\()", src, _re.DOTALL)
    line = _re.search(r'_env_with_release\("CLIENT_PACK_PUBKEYS".*', src)
    const = _re.search(r"^PROD_PACK_PUBKEYS = (.+)$", src, _re.MULTILINE)
    assert m and line, "pywebview_app.py 缺 CLIENT_PACK_PUBKEYS 注入行——打包链断链"
    assert const, "pywebview_app.py 缺 PROD_PACK_PUBKEYS 常量"

    def _run_with(release_json: str) -> str:
        d = _write(tmp_path, release_json)
        globs = {"os": os, "release": load_release_overrides(d),
                 "PROD_PACK_PUBKEYS": ast.literal_eval(const.group(1))}
        monkeypatch.delenv("CLIENT_PACK_PUBKEYS", raising=False)
        # 注入段实跑＝对 pywebview_app.py 真·源码行执行（S102 有意为之）
        exec(compile(textwrap.dedent(m.group(1)), "<injection-smoke>", "exec"), globs)  # noqa: S102
        exec(compile(line.group(0).strip(), "<injection-smoke>", "exec"), globs)  # noqa: S102
        return os.environ.get("CLIENT_PACK_PUBKEYS", "")

    assert _run_with(json.dumps({"pack_pubkeys": baked})) == baked
    default = _run_with("{}")
    assert '"pack-k1"' in default, "无烘焙时必须回落生产发布钥（否则本地直打无钥可验）"


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


# ── c-shell-release-env-order：env 注入必须先于 config 首次导入 ──────────────
# 实锤判例（v0.30 用户现场 10-09）：壳层曾用 `from config import load_release_overrides`
# 读取 release.json——那次 import 让 config.DATABASE_URL 在 CLIENT_VERSION 注入
# **之前**求值，正式包全部落 dev 哨兵库 novel-dev.db（#464 起 v0.25–v0.30 真机全中；
# dev 环境 CLIENT_VERSION 本就空、CI 断言只验烘焙内容，两条测试路都测不出）。


def _shell_source() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parent.parent.parent
            / "packaging" / "build" / "pywebview_app.py").read_text(encoding="utf-8")


def test_pywebview_never_imports_config():
    """门禁一（源码级）：壳层永不得 import config——config 模块常量
    （DATABASE_URL/SERVER_API_BASE）在 import 期求值，顺序回潮＝正式包
    版本注入被旁路、恒落 novel-dev.db。"""
    import re as _re

    offenders = [ln.strip() for ln in _shell_source().splitlines()
                 if _re.match(r"\s*(from|import)\s+config\b", ln)]
    assert not offenders, (
        "pywebview_app.py 不得 import config（release.json 走壳内 _load_release_json）："
        f"发现 {offenders!r}——config.DATABASE_URL 在 import 期按 CLIENT_VERSION 定库名，"
        "先导入＝版本注入被旁路、正式包恒落 novel-dev.db（c-shell-release-env-order 判例）")


def test_database_url_follows_client_version_at_import(tmp_path):
    """门禁二（行为级）：env 先注 → config 后导 → DATABASE_URL 按版本定名。
    子进程实跑 import config（规避本进程已缓存的 config 模块求值次序污染）。"""
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parent.parent
    for ver, expect in (("9.9", "novel-v9.9.db"), (None, "novel-dev.db")):
        env = {k: v for k, v in os.environ.items()
               if k not in ("DATABASE_URL", "CLIENT_VERSION")}
        env["DATA_ROOT"] = str(tmp_path)
        if ver:
            env["CLIENT_VERSION"] = ver
        out = subprocess.run(
            [sys.executable, "-c", "import config; print(config.DATABASE_URL)"],
            cwd=backend_dir, env=env, capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert out.endswith(expect), f"CLIENT_VERSION={ver} → 应含 {expect}，实得 {out}"


def test_shell_load_release_json_semantics(tmp_path):
    """门禁三：壳内 _load_release_json 与 load_release_overrides 语义等价
    （缺/坏/非对象容忍、空值过滤、strip）——它替代了旧的 `from config import` 路径。"""
    import importlib.util
    import sys
    import types
    from pathlib import Path

    if "webview" not in sys.modules:
        stub = types.ModuleType("webview")
        stub.screens = []
        stub.FOLDER_DIALOG = "folder"
        stub.SAVE_DIALOG = "save"
        stub.OPEN_DIALOG = "open"
        sys.modules["webview"] = stub
    src_path = (Path(__file__).resolve().parent.parent.parent
                / "packaging" / "build" / "pywebview_app.py")
    spec = importlib.util.spec_from_file_location("pywebview_app_release_env_test", src_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._load_release_json(tmp_path / "nope") == {}

    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "release.json").write_text("{not json", encoding="utf-8")
    assert module._load_release_json(bad) == {}

    nonobj = tmp_path / "nonobj"
    nonobj.mkdir()
    (nonobj / "release.json").write_text('["array"]', encoding="utf-8")
    assert module._load_release_json(nonobj) == {}

    ok = tmp_path / "ok"
    ok.mkdir()
    (ok / "release.json").write_text(
        '{"client_version": " 9.9 ", "server_api_base": "", "components": {}}',
        encoding="utf-8")
    # 空串/空对象（falsy）一律过滤，字符串值 strip——与 load_release_overrides 的
    # 「非空值才回」口径一致
    assert module._load_release_json(ok) == {"client_version": "9.9"}
