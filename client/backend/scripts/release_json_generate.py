"""release.json 生成单源（c-version-build-info 抽脚本化）：CI Generate 步骤与本地 dry-run 共用。

用法：`python scripts/release_json_generate.py <client_version> [-o release.json]`
- `<client_version>`：tag 构建传 tag 清洗后的版本（去 v 前缀，由 workflow 计算）；
  非 tag 构建传 `dev`。
- 构建信息（c-version-build-info）：**仅 dev** 从 `GITHUB_REF_NAME`/`GITHUB_SHA`
  烘 `client_build_branch`/`client_build_commit`；tag 构建不写——展示契约
  「tag 构建构建信息为空」从烘焙层就不给。分支映射：`pull_request` 事件的
  `GITHUB_REF_NAME` 形如 `123/merge` → `pr-123`；两键缺一不烘（运行时成对消费）。
- 环境变量：RELEASE_SERVER_API_BASE / RELEASE_SERVER_API_FALLBACK /
  RELEASE_DOWNLOAD_BASE / RELEASE_DOWNLOAD_FALLBACK_BASE（与 workflow step env 同名）。
- 本地 dry-run：`GITHUB_REF_NAME=main GITHUB_SHA=<sha> python scripts/release_json_generate.py dev -o /tmp/release.json`
  （不设 GITHUB_* 即模拟「无构建信息」形态）。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from release_components import build_components  # noqa: E402

_DEV = "dev"
_VERSION_SHAPE_RE = re.compile(r"[0-9]+(\.[0-9]+)+([-._][A-Za-z0-9._-]+)?")
_PR_REF_RE = re.compile(r"^(\d+)/merge$")
_BRANCH_BAD = re.compile(r"[^A-Za-z0-9._-]")
_MAX_BRANCH = 40


def version_shape_gate(version: str) -> None:
    """c-db-per-version：版本形态门禁——纯数字 tag 与遗留代数库名同形，禁用。"""
    if version == _DEV:
        return
    assert _VERSION_SHAPE_RE.fullmatch(version), f"tag 清洗后版本形态非法：{version!r}（需 0.x(.y) 形态，可带后缀）"
    assert not re.fullmatch(r"[0-9]+", version), f"纯数字 tag 禁用：v{version} 与遗留代数库名同形"


def bake_build_info(version: str) -> dict:
    """dev 构建从 GITHUB_* 烘构建信息；tag 构建恒空 dict（不写键）。"""
    if version != _DEV:
        return {}
    ref_name = (os.environ.get("GITHUB_REF_NAME") or "").strip()
    sha = (os.environ.get("GITHUB_SHA") or "").strip().lower()
    m = _PR_REF_RE.match(ref_name)
    branch = f"pr-{m.group(1)}" if m else ref_name
    branch = _BRANCH_BAD.sub("-", branch)[:_MAX_BRANCH]
    commit = sha[:5]
    if not branch or not re.fullmatch(r"[0-9a-f]{5}", commit):
        return {}
    return {"client_build_branch": branch, "client_build_commit": commit}


def generate(version: str) -> dict:
    version_shape_gate(version)
    comp = build_components(version)
    cfg = {
        "server_api_base": os.environ["RELEASE_SERVER_API_BASE"],
        "server_api_fallback": os.environ["RELEASE_SERVER_API_FALLBACK"],
        "client_version": version,
        "client_update_url": os.environ["RELEASE_DOWNLOAD_BASE"].rstrip("/") + "/latest.json",
        "client_update_url_fallback": os.environ["RELEASE_DOWNLOAD_FALLBACK_BASE"].rstrip("/") + "/latest.json",
        "components": comp,
        **bake_build_info(version),
    }
    for k in ("server_api_base", "client_update_url", "client_update_url_fallback"):
        assert str(cfg[k]).startswith("https://"), (k, cfg[k])
    assert comp.get("db_filename") == (f"novel-v{version}.db" if version != _DEV else "novel-dev.db"), comp
    assert isinstance(comp.get("backup_format_version"), int), comp
    return cfg


def main(argv: list[str]) -> int:
    try:
        # Windows runner stdout 默认 cp1252，print 含非 ASCII 时即 UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    version: str | None = None
    out_path = "release.json"
    rest = argv[1:]
    i = 0
    while i < len(rest):
        if rest[i] == "-o":
            if i + 1 >= len(rest):
                print("usage: release_json_generate.py <client_version> [-o release.json]", file=sys.stderr)
                return 2
            out_path = rest[i + 1]
            i += 2
        elif version is None:
            version = rest[i]
            i += 1
        else:
            print("usage: release_json_generate.py <client_version> [-o release.json]", file=sys.stderr)
            return 2
    if version is None:
        print("usage: release_json_generate.py <client_version> [-o release.json]", file=sys.stderr)
        return 2
    try:
        cfg = generate(version)
    except (AssertionError, KeyError) as exc:
        print(f"::error::release.json 生成失败：{exc!r}", file=sys.stderr)
        return 1
    Path(out_path).write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(cfg, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
