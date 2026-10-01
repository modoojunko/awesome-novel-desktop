"""UP-14 CI 产物侧断言（c-db-per-version）：release.json 组件清单正/负例。

CI 的冒烟断言已脚本化（`scripts/release_json_assert.py`），本测试直接驱动同一实现：

- 正例：模拟打包期烘入的产物（含 components）→ 断言通过；
- 负例：删掉 components / 改错 db_filename / 改错 backup_format_version → **必须转红**
  （规格：缺失或与后端单源不一致时冒烟断言 MUST 失败，不得静默发布）；
- 反断言：`components` MUST NOT 进运行时可覆盖键白名单（它只作断言与诊断锚）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backup.format import FORMAT_VERSION
from schema_version import db_filename_for
from scripts.release_components import build_components
from scripts.release_json_assert import check_release_json

BACKEND = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / "scripts" / "release_json_assert.py"


def _write_release_json(tmp_path: Path, version: str = "0.25", **overrides) -> Path:
    """模拟打包期产物：与 CI 生成步骤同构（components 由单源脚本产出）。"""
    cfg = {
        "server_api_base": "https://novel-s-server.example/api",
        "server_api_fallback": "https://novel-s-server.example/api",
        # S端 公开地址族（c-package-public-endpoints）：与 CI 生成步骤同构
        "public_server_api": "https://www.awesomenovel.com/api",
        "portal_url": "https://www.awesomenovel.com",
        "client_version": version,
        "client_update_url": "https://www.awesomenovel.com/download/latest.json",
        "client_update_url_fallback": (
            "https://ai-novel-test.example/download/latest.json"),
        "components": build_components(version),
    }
    cfg.update(overrides)
    path = tmp_path / "release.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), str(path)],
                          capture_output=True, text=True, cwd=BACKEND, check=False)


def test_up14_positive_baked_artifact(tmp_path):
    """正例：产物含 components 且与单源逐字一致 → 断言通过、输出含组件。"""
    path = _write_release_json(tmp_path)
    data = check_release_json(path)
    assert data["components"]["db_filename"] == db_filename_for("0.25") == "novel-v0.25.db"
    assert data["components"]["backup_format_version"] == FORMAT_VERSION
    proc = _run(path)
    assert proc.returncode == 0, proc.stderr
    assert "components=" in proc.stdout and "novel-v0.25.db" in proc.stdout
    print(f"[UP-14] baked ok: {proc.stdout.strip()}")


def test_up14_negative_missing_components(tmp_path):
    """负例：删掉 components → 断言必须转红且点名缺失键。"""
    path = _write_release_json(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["components"]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    proc = _run(path)
    assert proc.returncode != 0, "缺 components 必须失败（否则会静默发布）"
    assert "components" in proc.stderr
    print(f"[UP-14] 负例（缺键）: rc={proc.returncode} {proc.stderr.strip()[:90]}")


@pytest.mark.parametrize("bad", [
    {"db_filename": "novel-v0.24.db"},          # 与版本不符（错版名）
    {"backup_format_version": 999},             # 与单源不符
])
def test_up14_negative_wrong_component(tmp_path, bad):
    """负例：components 与后端单源不一致 → 转红。"""
    comp = build_components("0.25")
    comp.update(bad)
    path = _write_release_json(tmp_path, components=comp)
    proc = _run(path)
    assert proc.returncode != 0, f"不一致必须失败：{bad}"
    assert "单源不一致" in proc.stderr
    print(f"[UP-14] 负例 {bad}: rc={proc.returncode}")


def test_up14_components_not_runtime_override():
    """反断言：components MUST NOT 进 RELEASE_OVERRIDE_KEYS（运行时无消费方）。"""
    from config import RELEASE_OVERRIDE_KEYS

    assert "components" not in RELEASE_OVERRIDE_KEYS
    assert "db_filename" not in RELEASE_OVERRIDE_KEYS


@pytest.mark.parametrize("missing", ["public_server_api", "portal_url"])
def test_public_endpoint_family_missing_rejected(tmp_path, missing):
    """负例（c-package-public-endpoints）：地址族缺键 → 断言必须转红——
    public_server_api 缺烘曾致打包端授权页 404（v0.23–v0.25 实锤），冒烟必拦。"""
    path = _write_release_json(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data[missing]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    proc = _run(path)
    assert proc.returncode != 0, f"缺 {missing} 必须失败（否则授权页 404 复发）"
    assert missing in proc.stderr


@pytest.mark.parametrize("bad", [
    {"public_server_api": "http://www.awesomenovel.com/api"},   # 非 https
    {"portal_url": "novel-s-web-test.webapps.tcloudbase.com"},  # 裸域名无 scheme
])
def test_public_endpoint_family_non_https_rejected(tmp_path, bad):
    """负例：地址族非 https 形态 → 转红。"""
    path = _write_release_json(tmp_path, **bad)
    proc = _run(path)
    assert proc.returncode != 0, f"非 https 必须失败：{bad}"


def _run_generate(version: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """子进程驱动生成脚本（与 CI Generate 步骤同形；直 import 会缺脚本目录 sys.path）。"""
    out = tmp_path / "release.json"
    return subprocess.run(
        [sys.executable, str(BACKEND / "scripts" / "release_json_generate.py"), version, "-o", str(out)],
        capture_output=True, text=True, cwd=BACKEND, check=False,
    )


def test_generate_bakes_public_endpoint_family(tmp_path, monkeypatch):
    """正例（c-package-public-endpoints）：generate() 烘入地址族两新键且值来自 env。"""
    monkeypatch.setenv("RELEASE_SERVER_API_BASE", "https://novel-s-server.example/api")
    monkeypatch.setenv("RELEASE_SERVER_API_FALLBACK", "https://novel-s-server.example/api")
    monkeypatch.setenv("RELEASE_PUBLIC_SERVER_API", "https://www.awesomenovel.com/api")
    monkeypatch.setenv("RELEASE_PORTAL_URL", "https://www.awesomenovel.com")
    monkeypatch.setenv("RELEASE_DOWNLOAD_BASE", "https://www.awesomenovel.com/download")
    monkeypatch.setenv("RELEASE_DOWNLOAD_FALLBACK_BASE", "https://fallback.example/download")
    proc = _run_generate("0.25.1", tmp_path)
    assert proc.returncode == 0, proc.stderr
    cfg = json.loads((tmp_path / "release.json").read_text(encoding="utf-8"))
    assert cfg["public_server_api"] == "https://www.awesomenovel.com/api"
    assert cfg["portal_url"] == "https://www.awesomenovel.com"
    assert cfg["components"]["db_filename"] == "novel-v0.25.1.db"


def test_generate_missing_public_env_rejected(tmp_path, monkeypatch):
    """负例：地址族 env 缺失 → 生成即红，不得产出缺键产物。"""
    monkeypatch.setenv("RELEASE_SERVER_API_BASE", "https://novel-s-server.example/api")
    monkeypatch.setenv("RELEASE_SERVER_API_FALLBACK", "https://novel-s-server.example/api")
    monkeypatch.delenv("RELEASE_PUBLIC_SERVER_API", raising=False)
    monkeypatch.setenv("RELEASE_PORTAL_URL", "https://www.awesomenovel.com")
    monkeypatch.setenv("RELEASE_DOWNLOAD_BASE", "https://www.awesomenovel.com/download")
    monkeypatch.setenv("RELEASE_DOWNLOAD_FALLBACK_BASE", "https://fallback.example/download")
    proc = _run_generate("0.25.1", tmp_path)
    assert proc.returncode != 0, "缺 RELEASE_PUBLIC_SERVER_API 必须失败"
    assert "RELEASE_PUBLIC_SERVER_API" in proc.stderr


def test_ci_generate_step_sets_public_endpoint_env():
    """静态守卫（c-package-public-endpoints）：workflow 生成步骤必须注入地址族 env——
    防「白名单有键、烘焙缺行」的静默断链形态复发（v0.23–v0.25 实锤）。"""
    wf = (BACKEND.parent.parent / ".github" / "workflows" / "client-package.yml").read_text(
        encoding="utf-8")
    step_start = wf.index("- name: Generate release.json")
    step = wf[step_start: wf.index("\n      - name:", step_start)]
    assert "RELEASE_PUBLIC_SERVER_API:" in step, "生成步骤缺 RELEASE_PUBLIC_SERVER_API 注入"
    assert "RELEASE_PORTAL_URL:" in step, "生成步骤缺 RELEASE_PORTAL_URL 注入"


def test_ci_components_step_cwd_resolves():
    """静态守卫（检视 P0）：生成步骤的内联 `cwd="…"` 必须相对该步骤的
    `working-directory` 解析后存在。

    实锤过的挂法：步骤 `working-directory: client/packaging/build` 里写
    `cwd="client/backend"` → 解析成 `client/packaging/build/client/backend`（不存在）
    → 每个 tag/PR 构建都在 release.json 生成步 FileNotFoundError。
    """
    import re

    wf = (BACKEND.parent.parent / ".github" / "workflows" / "client-package.yml").read_text(
        encoding="utf-8")
    step_start = wf.index("- name: Generate release.json")
    step = wf[step_start: wf.index("\n      - name:", step_start)]
    wd = re.search(r"working-directory:\s*(\S+)", step).group(1)
    # c-version-build-info 抽脚本后守卫对象从内联 cwd= 换成脚本调用行——
    # 脚本路径仍相对该步骤 working-directory 解析，必须真实存在
    script_arg = re.search(r"python\s+(\S*release_json_generate\.py)", step)
    assert script_arg, "生成步骤未调用 release_json_generate.py——结构变了须同批更新本守卫"
    resolved = (BACKEND.parent.parent / wd / script_arg.group(1)).resolve()
    assert resolved.is_file(), (
        f"生成步骤脚本路径解析失败：working-directory={wd} + script={script_arg.group(1)} → {resolved}")
    assert (BACKEND / "scripts" / "release_components.py").is_file()


# ── c-version-build-info：构建信息可选键 ─────────────────────────────────


def test_build_info_keys_accepted(tmp_path):
    """正例：非 tag 产物烘构建信息两键 → 断言通过。"""
    path = _write_release_json(tmp_path, version="dev",
                               client_build_branch="pr-123", client_build_commit="f456e")
    assert check_release_json(path)["client_build_branch"] == "pr-123"
    assert _run(path).returncode == 0


def test_build_info_long_commit_accepted(tmp_path):
    """`--short=5` 是「至少 5 位」语义：碰撞仓库输出更长合法 sha 不得误杀。"""
    path = _write_release_json(tmp_path, version="dev",
                               client_build_branch="main",
                               client_build_commit="f456e8fa9b0123456789abcdef0123456789abcd")
    assert _run(path).returncode == 0


def test_build_info_dirty_branch_rejected(tmp_path):
    path = _write_release_json(tmp_path, version="dev",
                               client_build_branch="bad branch!", client_build_commit="f456e")
    assert _run(path).returncode == 1


def test_build_info_bad_commit_rejected(tmp_path):
    path = _write_release_json(tmp_path, version="dev",
                               client_build_branch="main", client_build_commit="zzzzz")
    assert _run(path).returncode == 1


def test_build_info_absent_tolerated(tmp_path):
    """tag 构建/旧产物不烘构建信息键 → 容忍通过。"""
    path = _write_release_json(tmp_path)  # version 0.25，无 build 键
    assert _run(path).returncode == 0
