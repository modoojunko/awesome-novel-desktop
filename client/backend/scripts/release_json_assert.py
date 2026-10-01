"""release.json 产物断言（c-db-per-version）：CI 冒烟步骤的**唯一实现**。

用法：`python scripts/release_json_assert.py <dist 内 release.json 路径>`

判据（缺失/不一致即非零退出，流水线转红）：
1. 既有三键（S端 地址、版本、检测地址）形态不变；
2. **组件清单 `components` 必须存在**，且 `db_filename` 与后端单源逐字一致；
3. `backup_format_version` 等于后端单源当前值；
4. c-version-build-info：`client_build_branch`/`client_build_commit` **可选键**
   （tag 构建/旧产物不烘），存在则校验形态——分支安全字符集＋≤40、commit
   `[0-9a-f]{5,40}`（`--short=5` 是「至少 5 位」语义，宽容到 40）。

脚本化而非 workflow 内联：断言逻辑可被测试直接驱动（正/负例），避免「CI 里那条
断言其实没人跑过」。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backup.format import FORMAT_VERSION  # noqa: E402
from schema_version import db_filename_for  # noqa: E402


def check_release_json(path: str | Path) -> dict:
    """校验并返回 release.json 内容；任一断言失败抛 AssertionError。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert str(data.get("server_api_base", "")).startswith("https://"), data
    version = str(data.get("client_version", "")).strip()
    assert version, data
    assert str(data.get("client_update_url", "")).startswith("https://"), data
    assert str(data.get("client_update_url_fallback", "")).startswith("https://"), data
    comp = data.get("components")
    assert isinstance(comp, dict), ("release.json 缺 components 键（组件清单未烘入产物）", data)
    assert comp.get("db_filename") == db_filename_for(version), (
        "components.db_filename 与后端单源不一致", comp, version)
    assert comp.get("backup_format_version") == FORMAT_VERSION, (
        "components.backup_format_version 与后端单源不一致", comp, FORMAT_VERSION)
    branch = data.get("client_build_branch")
    commit = data.get("client_build_commit")
    if branch is not None or commit is not None:  # 可选键：缺省容忍，存在则成对校验
        assert isinstance(branch, str) and branch and len(branch) <= 40 \
            and re.fullmatch(r"[A-Za-z0-9._-]+", branch), ("client_build_branch 形态非法", branch)
        assert isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{5,40}", commit), (
            "client_build_commit 形态非法", commit)
    return data


def main(argv: list[str]) -> int:
    try:
        # Windows runner stdout 默认 cp1252，失败信息含中文时 print 即 UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(argv) != 2:
        print("usage: release_json_assert.py <release.json>", file=sys.stderr)
        return 2
    try:
        data = check_release_json(argv[1])
    except AssertionError as exc:
        print(f"::error::release.json 产物断言失败：{exc}", file=sys.stderr)
        return 1
    print("baked:", argv[1], "->", data["client_version"], data["client_update_url"],
          "components=", data["components"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
