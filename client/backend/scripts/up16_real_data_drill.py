"""UP-16 真数据演练（c-db-per-version）：真库拷贝 → 首启 → 候选 → 带回 → roundtrip。

**只读源、只操作拷贝**：把指定真实库的三件套拷进会话私有 DATA_ROOT，之后全部动作
都在拷贝上；每一步前后取源三件套 `sha256/mtime_ns/size` 对照，证明源零改动。

用法：
    python scripts/up16_real_data_drill.py --work /tmp/up16 \
        --lib /path/to/novel-v1.db --lib /path/to/novel.db --evidence out.md

默认源为本机两处真实库（开发检出 data/ 与本地栈 .docker-data/client/）；不存在则跳过。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parents[3]
DEFAULT_LIBS = [
    REPO / ".docker-data" / "client" / "novel-v1.db",
    REPO / "client" / "backend" / "data" / "novel.db",
]
COPY_SUFFIXES = ("", "-wal", "-shm")


def _sig(db_path: Path) -> dict:
    out = {}
    for suf in COPY_SUFFIXES:
        p = Path(f"{db_path}{suf}")
        if not p.exists():
            continue
        st = p.stat()
        out[p.name] = {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16],
            "mtime_ns": st.st_mtime_ns,
            "size": st.st_size,
        }
    return out


def _copy_set(src: Path, dst: Path) -> None:
    for suf in COPY_SUFFIXES:
        s = Path(f"{src}{suf}")
        if s.exists():
            shutil.copy2(s, Path(f"{dst}{suf}"))


def _count(con, table: str):
    try:
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.Error:
        return "表不存在"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--lib", action="append", default=[])
    ap.add_argument("--evidence", default="")
    ap.add_argument("--version", default="0.25")
    args = ap.parse_args(argv[1:])

    os.environ["CLIENT_VERSION"] = args.version
    work = Path(args.work).resolve()
    data_root = work / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    os.environ["DATA_ROOT"] = str(data_root)

    libs = [Path(p) for p in (args.lib or [str(p) for p in DEFAULT_LIBS])]
    lines: list[str] = []
    rows: list[dict] = []

    import models  # noqa: F401 —— 注册全表
    from db import Base
    from db_lifecycle import compute_schema_fingerprint, scan_migration_candidates
    from migration.engine import precheck, run_migration
    from schema_version import db_filename_for
    from sqlalchemy import create_engine

    # ── 拷贝真库（源零接触）＋快照 ─────────────────────────────────────────
    copied: list[Path] = []
    for src in libs:
        if not src.exists():
            lines.append(f"跳过（源不存在）：{src}")
            continue
        dst = data_root / src.name
        _copy_set(src, dst)
        copied.append(dst)
        rows.append({"source": str(src), "name": src.name, "before": _sig(src)})
        lines.append(f"拷入：{src} → {dst}（{_sig(src).get(src.name, {}).get('size', '?')} bytes）")

    # ── 首启：建自己版本的库（空库）────────────────────────────────────────
    active = data_root / db_filename_for(args.version)
    se = create_engine(f"sqlite:///{active}")
    Base.metadata.create_all(se)
    se.dispose()
    con = sqlite3.connect(f"file:{active}?mode=ro", uri=True)
    boot_books = _count(con, "novels")
    con.close()
    lines.append(f"首启：{active.name} 建库，novels={boot_books}（空库）")

    # ── 候选扫描 ───────────────────────────────────────────────────────────
    cands = scan_migration_candidates(data_root, args.version, active)
    lines.append("候选：" + json.dumps(
        [{k: c[k] for k in ("filename", "kind", "version", "legacy_generation",
                            "book_count", "recommended", "unreadable")} for c in cands],
        ensure_ascii=False))
    for c in cands:
        assert Path(data_root / c["filename"]).exists()

    # ── 逐候选：预检 → 预览 → 一键带回 → 计数对拍 ─────────────────────────
    for c in cands:
        name = c["filename"]
        pc = precheck(data_root, name, active)
        if not pc["ok"]:
            lines.append(f"带回 {name}：预检拒绝（{pc['reason']}）——见下方门禁说明")
            continue
        rep = run_migration(data_root, name, active)
        assert rep["status"] == "ok", rep
        lines.append(
            f"带回 {name}：source={rep['book_count_source']} migrated={rep['book_count_migrated']} "
            f"tables={len(rep['tables'])} skipped={[s['reason'] for s in rep['tables_skipped']]} "
            f"fk={len(rep['fk_violations'])}")
        assert rep["book_count_migrated"] == c["book_count"], (rep["book_count_migrated"], c)

    # ── 被排除的拷贝（如改名前世代）直接试一次，留门禁证据 ────────────────
    listed = {c["filename"] for c in cands}
    for dst in copied:
        if dst.name in listed:
            continue
        pc = precheck(data_root, dst.name, active)
        lines.append(f"未列入候选的拷贝 {dst.name}：precheck → ok={pc['ok']} reason={pc.get('reason')}")

    # ── 目标库最终计数 ＋ 搬后 roundtrip（导出）────────────────────────────
    con = sqlite3.connect(f"file:{active}?mode=ro", uri=True)
    final = {t: _count(con, t) for t in ("novels", "volumes", "chapters", "characters",
                                         "novel_hooks", "app_meta")}
    con.close()
    lines.append("目标库最终计数：" + json.dumps(final, ensure_ascii=False))

    os.environ["DATA_ROOT"] = str(data_root)
    from db import engine as _engine
    import asyncio

    from backup.export import job_status, start_backup_job
    from models.user import User

    # 属主分布：本机真库由数百次 e2e 跑出来，每跑一个 user_id——逐用户导出只覆盖其中
    # 一份，故 roundtrip 取**免登整库口径**（user_id=None，loginless-data-exit 路径）
    _con = sqlite3.connect(f"file:{active}?mode=ro", uri=True)
    owner_rows = _con.execute(
        "SELECT user_id, COUNT(*) c FROM novels GROUP BY user_id ORDER BY c DESC LIMIT 3").fetchall()
    _con.close()
    owner = "up16"

    async def _seed_user():
        from db import async_session
        from sqlalchemy import text as _sql

        async with async_session() as s:
            # 真库里 users 表会随带回归来（38 表之一）——已存在则不重复插
            exists = await s.execute(
                _sql("SELECT 1 FROM users WHERE id=:i"), {"i": owner})
            if exists.first():
                return
            s.add(User(id=owner, email=f"{owner}@test.local", password_hash="x",
                       display_name="UP-16", api_key="", api_base_url="", api_model=""))
            await s.commit()

    asyncio.run(_seed_user())
    asyncio.run(_engine.dispose())
    assert start_backup_job(str(work / "backup"), None, False) is not None  # 整库口径
    for _ in range(600):
        st = job_status()
        if st.get("state") in ("done", "error"):
            break
        import time

        time.sleep(0.05)
    assert st.get("state") == "done", st
    zips = sorted((work / "backup").glob("*.zip"))
    zsize = zips[-1].stat().st_size if zips else 0
    assert zips, "搬后导出未产出"
    # roundtrip 判据＝**包内作品段数 == 未删除书数**（导出按 `status != deleted` 取书：
    # 本机真库 1213 行里 1085 行是 e2e 软删除的残书，128 行才是活书）
    import zipfile as _zip

    with _zip.ZipFile(zips[-1]) as zf:
        book_segments = [n for n in zf.namelist() if n.endswith("project.yaml")]
    _con = sqlite3.connect(f"file:{active}?mode=ro", uri=True)
    live_books = _con.execute(
        "SELECT COUNT(*) FROM novels WHERE status != 'deleted'").fetchone()[0]
    _con.close()
    lines.append(f"搬后 roundtrip：导出 {zips[-1].name} {zsize} bytes（免登整库口径）；"
                 f"包内作品段 {len(book_segments)} == 活书数 {live_books}"
                 f"（库内总行 {final['novels']}，含 e2e 软删残书）；属主分布 top3={owner_rows}")
    assert len(book_segments) == live_books, (len(book_segments), live_books)

    # ── 源零改动断言（决定性判据）──────────────────────────────────────────
    for row in rows:
        after = _sig(Path(row["source"]))
        same = after == row["before"]
        lines.append(f"源不变 {row['name']}：{same}")
        assert same, f"源被改动：{row['name']} {row['before']} → {after}"

    report = "\n".join(lines)
    print(report)
    if args.evidence:
        out = Path(args.evidence)
        out.parent.mkdir(parents=True, exist_ok=True)
        table = "\n".join(
            f"| {r['source']} | {k} | {v['sha256']} | {v['mtime_ns']} | {v['size']} |"
            for r in rows for k, v in r["before"].items())
        out.write_text(
            "# UP-16 真数据演练证据（c-db-per-version）\n\n"
            f"命令：`python scripts/up16_real_data_drill.py --work {work} "
            f"--version {args.version}`\n\n## 运行输出\n\n```\n{report}\n```\n\n"
            "## 源三件套 sha256/mtime_ns/size（运行后逐项复测相等）\n\n"
            "| 源 | 文件 | sha256(前16) | mtime_ns | size |\n| --- | --- | --- | --- | --- |\n"
            + table + "\n", encoding="utf-8")
        print(f"\n证据写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
