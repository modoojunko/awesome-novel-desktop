"""迁移子进程 CLI 契约（c-migration-hardening）：spawn／报告文件／退出码。

测试套件默认走进程内（conftest MIGRATION_WORKER_INPROCESS=1，避免共享库跨进程写）；
生产子进程路径在此用独立临时目录做真 spawn 验证——引擎搬运正确性由
test_migration_engine 的 44 例（进程内同引擎）覆盖，本文件只钉「拉起→报告→退出码」胶水。
"""

import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_worker_writes_report_for_missing_source(tmp_path: Path):
    """源缺失：worker 仍交付报告（precheck_failed），exit 0——父进程以报告为事实。"""
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, "-m", "migration.worker", str(tmp_path), "novel.db",
         str(tmp_path / "target.db"), str(out)],
        cwd=str(BACKEND_ROOT), capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["source"] == "novel.db"
    assert report["status"] in ("precheck_failed", "error")


def test_worker_usage_guard(tmp_path: Path):
    """参数不足：exit 2＋usage 到 stderr（父进程据此报「未产出报告」）。"""
    proc = subprocess.run(
        [sys.executable, "-m", "migration.worker", "only-one-arg"],
        cwd=str(BACKEND_ROOT), capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 2
    assert "usage:" in proc.stderr
