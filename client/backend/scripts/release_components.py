"""发布组件清单纯源（c-db-per-version）：打包期取数用。

用法：`python scripts/release_components.py <version>`
输出：单行 JSON —— `{"db_filename": ..., "backup_format_version": ...}`

CI 在生成 `release.json` 时调用本脚本写入 `components`，并对产物做冒烟断言
（缺失或与单源不一致即失败）。**版本号显式传入**——不得从环境变量推断，否则
自检与产物会同源同错。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backup.format import FORMAT_VERSION  # noqa: E402
from schema_version import db_filename_for  # noqa: E402


def build_components(version: str) -> dict:
    """本版本实际使用的组件版本（全部由后端单源派生）。"""
    return {
        "db_filename": db_filename_for(version),
        "backup_format_version": FORMAT_VERSION,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: release_components.py <version>", file=sys.stderr)
        return 2
    print(json.dumps(build_components(argv[1]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
