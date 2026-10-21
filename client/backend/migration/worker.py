"""迁移搬运子进程（c-migration-hardening）：独立进程执行 run_migration。

为什么不在服务进程里跑：迁移是低频、重 I/O、可能撞环境抖动（VirtioFS ATTACH 等）的
一次性作业——放服务线程会继承服务进程的长龄态与已打开连接（demo 10-21 事故：同代码
新进程稳定成功、服务进程必败）；拉起一次性子进程天然免疫，且进程退出即回收全部资源。
报告经 JSON 文件回传父进程（stdout 只留 progress 行，防管道阻塞）。

用法（router 内部调用，非用户口）：
  python -m migration.worker <data_root> <source_filename> <active_db_path> <report_json_path>
退出码：0＝报告已写出（报告 status 可能是 ok/error，以 JSON 为准）；非 0＝子进程自身崩溃。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print("usage: python -m migration.worker <data_root> <source> <active_db> <report_out>",
              file=sys.stderr)
        return 2
    data_root, source_filename, active_db, report_out = argv[1:5]
    from migration.engine import run_migration

    report = run_migration(Path(data_root), source_filename, Path(active_db))
    Path(report_out).write_text(
        json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
    # 报告即事实：完成与否由 report.status/complete 表达，退出码只表示交付成功
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
