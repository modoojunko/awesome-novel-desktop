"""从 ORM 元数据生成缺失项的 PG DDL（部署门禁拦截后的恢复路径，s-db-migrate-pipeline）。

pg_gate 拦下部署后，用本脚本按「表.列」或表名产出可直接经 MCP applyMigration
应用的语句——DDL 以元数据为单源，不再手写等价 SQL。

用法：
    python3 server/scripts/gen_missing_ddl.py orders.attach_sent users.agreement_version
    python3 server/scripts/gen_missing_ddl.py device_outdated_marks      # 整表缺失
    python3 server/scripts/gen_missing_ddl.py --all-tables               # 全量建表语句
"""
from __future__ import annotations

import sys
from pathlib import Path

_server_dir = Path(__file__).parent.parent
if str(_server_dir) not in sys.path:
    sys.path.insert(0, str(_server_dir))

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateColumn, CreateTable

from app.models import Base


def _table_ddl(table_name: str) -> str:
    table = Base.metadata.tables[table_name]
    return str(CreateTable(table).compile(dialect=postgresql.dialect())).strip() + ";"


def _column_ddl(table_name: str, column_name: str) -> str:
    table = Base.metadata.tables[table_name]
    column = table.columns[column_name]
    compiled = str(CreateColumn(column).compile(dialect=postgresql.dialect())).strip()
    return f"ALTER TABLE {table_name} ADD COLUMN {compiled};"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for arg in argv:
        if arg == "--all-tables":
            for table_name in sorted(Base.metadata.tables):
                print(f"-- table: {table_name}")
                print(_table_ddl(table_name))
            continue
        try:
            if "." in arg:
                table_name, column_name = arg.split(".", 1)
                print(_column_ddl(table_name, column_name) + "\n")
            else:
                print(f"-- table: {arg}")
                print(_table_ddl(arg) + "\n")
        except KeyError as exc:
            print(f"-- 未找到 {arg}（ORM 元数据无此表/列）：{exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
