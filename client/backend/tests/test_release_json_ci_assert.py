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
                          capture_output=True, text=True, cwd=BACKEND)


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
    cwd_arg = re.search(r'cwd="([^"]+)"', step).group(1)
    resolved = (BACKEND.parent.parent / wd / cwd_arg).resolve()
    assert resolved.is_dir(), (
        f"生成步骤 cwd 解析失败：working-directory={wd} + cwd={cwd_arg} → {resolved}")
    assert (resolved / "scripts" / "release_components.py").is_file()
