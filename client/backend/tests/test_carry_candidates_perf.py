"""c-carry-candidates-perf —候选盘点去阻塞＋多槽缓存＋链上溯源归档 单测。

口径（db-generation delta，specs 场景逐一对应）：
- 候选扫描不得阻塞请求面：盘点在 Worker 线程执行，进行中事件循环照常调度
- 指纹/探活多槽缓存：数据件未变不重算、变化即重算、并发一致、容量封顶
- 链上带回溯源：沿 migration.last 逐跳回溯，每跳完整性单源判定；
  断链/链外/源复写/缺证不标（少归档优于误归档）
- 归档＝移动不删除；白名单外拒绝；归档件退出盘点；immutable 读零痕迹
"""

import asyncio
import json
import sqlite3
import threading
from pathlib import Path

import db_lifecycle
import schema_version
from db_lifecycle import (
    ARCHIVE_DIRNAME,
    archive_candidate,
    migration_last_cached,
    probe_library_cached,
    scan_migration_candidates,
    trace_carry_chain,
)
from migration import router
from schema_version import candidate_stamp_hash, db_filename_for

CUR = db_filename_for("0.25")  # 活跃槽名（同 test_db_lifecycle 口径）


def _write_db(path: Path, *, books: int = 0, migration_last: dict | None = None) -> None:
    """造一个最小槽位库：app_meta（可带 migration.last）＋novels 计数。"""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS novels (id TEXT PRIMARY KEY, name TEXT)")
    for i in range(books):
        con.execute("INSERT OR IGNORE INTO novels VALUES (?, ?)", (f"b{i}", f"书{i}"))
    if migration_last is not None:
        con.execute("INSERT INTO app_meta VALUES ('migration.last', ?)",
                    (json.dumps(migration_last, ensure_ascii=False),))
    con.commit()
    con.close()


def _complete_report(n: int = 3) -> dict:
    return {"status": "ok", "tables_skipped": [], "tables": [],
            "book_count_source": n, "book_count_present": n, "fk_violations": []}


def _make_slot(root: Path, name: str, *, source: str | None = None,
               books: int = 1) -> None:
    """造一个链上槽：migration.last 指向 source（stamp 按源文件实算，三形态可对拍）。"""
    if source is not None:
        src = root / source
        stamp = candidate_stamp_hash(source, src)
        _write_db(root / name, books=books,
                  migration_last={"source_filename": source, "source_stamp": stamp,
                                  "report": _complete_report(books)})
    else:
        _write_db(root / name, books=books)


# ── 2.1 指纹多槽缓存 ──────────────────────────────────────────────────────


class TestStampHashMultiSlotCache:
    def test_same_key_no_rehash(self, tmp_path, monkeypatch):
        """数据件未变：第二次起复用缓存，不重读字节。"""
        p = tmp_path / "novel-v0.24.db"
        _write_db(p, books=1)
        calls = {"n": 0}
        real = schema_version._hash_data_files

        def counting(db_path, wal):
            calls["n"] += 1
            return real(db_path, wal)

        monkeypatch.setattr(schema_version, "_hash_data_files", counting)
        s1 = candidate_stamp_hash("novel-v0.24.db", p)
        s2 = candidate_stamp_hash("novel-v0.24.db", p)
        assert s1 == s2 and calls["n"] == 1

    def test_bytes_change_rehashes(self, tmp_path):
        """数据件被写（size/mtime 变）→ 重算，结论与从无缓存重算一致。"""
        p = tmp_path / "novel-v0.24.db"
        _write_db(p, books=1)
        s1 = candidate_stamp_hash("novel-v0.24.db", p)
        _write_db(p, books=2)  # 同路径重写：字节变了
        s2 = candidate_stamp_hash("novel-v0.24.db", p)
        assert s1 != s2
        assert s2 == candidate_stamp_hash("novel-v0.24.db", p)

    def test_concurrent_calls_consistent(self, tmp_path):
        """Worker 线程并发首扫：全部拿到同一指纹（一致性，不要求单次计算）。"""
        p = tmp_path / "novel-v0.24.db"
        _write_db(p, books=1)
        results: list[str] = []
        lock = threading.Lock()
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            s = candidate_stamp_hash("novel-v0.24.db", p)
            with lock:
                results.append(s)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(results)) == 1

    def test_cache_cap_bounded(self, tmp_path):
        """容量封顶：漂移 FS 上键增长有界（真机 43 槽 < 容量，封顶只防无界）。"""
        assert schema_version._STAMP_HASH_CACHE_CAP <= 64
        for i in range(schema_version._STAMP_HASH_CACHE_CAP + 8):
            p = tmp_path / f"novel-v0.{i}.db"
            _write_db(p, books=1)
            candidate_stamp_hash(p.name, p)
        assert len(schema_version._stamp_hash_cache) <= schema_version._STAMP_HASH_CACHE_CAP


# ── 2.2 探活缓存 ──────────────────────────────────────────────────────────


class TestProbeCache:
    def test_same_key_no_reprobe(self, tmp_path, monkeypatch):
        """数据件未变：探活结果复用，不开库。"""
        p = tmp_path / "novel-v0.24.db"
        _write_db(p, books=2)
        calls = {"n": 0}
        real = db_lifecycle.probe_library

        def counting(db_path):
            calls["n"] += 1
            return real(db_path)

        monkeypatch.setattr(db_lifecycle, "probe_library", counting)
        i1 = probe_library_cached(p)
        i2 = probe_library_cached(p)
        assert i1 == i2 and i1["book_count"] == 2 and calls["n"] == 1

    def test_reprobe_after_change(self, tmp_path):
        """数据件被写 → 重探（书数变化可见）。"""
        p = tmp_path / "novel-v0.24.db"
        _write_db(p, books=1)
        assert probe_library_cached(p)["book_count"] == 1
        _write_db(p, books=5)
        assert probe_library_cached(p)["book_count"] == 5

    def test_missing_file_not_cached(self, tmp_path, monkeypatch):
        """不存在件不进缓存（建出来的那一刻要能被看见）。"""
        p = tmp_path / "novel-v0.24.db"
        calls = {"n": 0}
        real = db_lifecycle.probe_library

        def counting(db_path):
            calls["n"] += 1
            return real(db_path)

        monkeypatch.setattr(db_lifecycle, "probe_library", counting)
        assert probe_library_cached(p)["exists"] is False
        _write_db(p, books=1)
        assert probe_library_cached(p)["book_count"] == 1
        assert calls["n"] == 2

    def test_scan_uses_cached_probe(self, tmp_path, monkeypatch):
        """候选盘点走缓存皮：同盘重复扫描不重复开库探活。"""
        root = tmp_path
        (root / "novel-v0.24.db").write_bytes(b"")  # 后面 _write_db 覆盖
        _write_db(root / "novel-v0.24.db", books=3)
        active = root / CUR
        _write_db(active, books=0)
        calls = {"n": 0}
        real = db_lifecycle.probe_library

        def counting(db_path):
            calls["n"] += 1
            return real(db_path)

        monkeypatch.setattr(db_lifecycle, "probe_library", counting)
        first = scan_migration_candidates(root, "0.25", active)
        second = scan_migration_candidates(root, "0.25", active)
        assert calls["n"] == 1  # 第二次盘点全命中缓存
        assert [it["filename"] for it in first] == [it["filename"] for it in second]
        assert first[0]["book_count"] == 3


# ── 4.1 链上溯源 ──────────────────────────────────────────────────────────


class TestTraceCarryChain:
    def test_chain_three_hops_marked(self, tmp_path):
        """A→B→C→活跃 全链完整：三源全标 True。"""
        root = tmp_path
        _make_slot(root, "novel-v0.22.db", books=1)                      # 链尾 C
        _make_slot(root, "novel-v0.23.db", source="novel-v0.22.db")      # B
        _make_slot(root, "novel-v0.24.db", source="novel-v0.23.db")      # A
        active = root / CUR
        _make_slot(root, CUR, source="novel-v0.24.db")
        chain = trace_carry_chain(root, active)
        assert chain["novel-v0.22.db"] is True
        assert chain["novel-v0.23.db"] is True
        assert chain["novel-v0.24.db"] is True

    def test_incomplete_hop_breaks_chain(self, tmp_path):
        """中间跳（A 对 B 的搬运）不完整：B 不标，更早的也不标（少归档优于误归档）。

        chain[X] 的语义＝「X 被它的后继完整带回」，证据在**后继**的 migration.last。"""
        root = tmp_path
        _make_slot(root, "novel-v0.22.db", books=1)                 # 链尾 C
        _make_slot(root, "novel-v0.23.db", source="novel-v0.22.db")  # B→C 完整
        # A 对 B 的搬运跳表（A 的 last 里 report 不完整）
        stamp_b = candidate_stamp_hash("novel-v0.23.db", root / "novel-v0.23.db")
        _write_db(root / "novel-v0.24.db", books=1,
                  migration_last={"source_filename": "novel-v0.23.db",
                                  "source_stamp": stamp_b,
                                  "report": {"status": "ok",
                                             "tables_skipped": [{"table": "x"}],
                                             "tables": [], "book_count_source": 3,
                                             "book_count_present": 2,
                                             "fk_violations": []}})
        active = root / CUR
        _make_slot(root, CUR, source="novel-v0.24.db")
        chain = trace_carry_chain(root, active)
        assert chain["novel-v0.24.db"] is True   # 活跃→A 跳完整，A 可归档
        assert chain["novel-v0.23.db"] is False  # A→B 跳不完整，B 断链
        assert not chain.get("novel-v0.22.db")   # 更早的 C 不再标

    def test_off_chain_slot_not_marked(self, tmp_path):
        """链外槽（dev 自用等，从未被任何链带回）不标。"""
        root = tmp_path
        _make_slot(root, "novel-dev.db", books=1)
        _make_slot(root, "novel-v0.24.db", books=1)
        active = root / CUR
        _make_slot(root, CUR, source="novel-v0.24.db")
        chain = trace_carry_chain(root, active)
        assert "novel-dev.db" not in chain
        assert chain["novel-v0.24.db"] is True

    def test_rewritten_source_breaks_chain(self, tmp_path):
        """源被复写（迁移后又写数据）→ 指纹对拍不命中，断链。"""
        root = tmp_path
        _make_slot(root, "novel-v0.22.db", books=1)                  # 链尾 C
        _make_slot(root, "novel-v0.23.db", source="novel-v0.22.db")  # B
        _make_slot(root, "novel-v0.24.db", source="novel-v0.23.db")  # A
        active = root / CUR
        _make_slot(root, CUR, source="novel-v0.24.db")
        # A 完成迁移后 B 又被写入（字节变化）→ A 记录的 stamp(B) 对不上现行 B
        _write_db(root / "novel-v0.23.db", books=99)
        chain = trace_carry_chain(root, active)
        assert chain["novel-v0.24.db"] is True
        assert chain["novel-v0.23.db"] is False
        assert not chain.get("novel-v0.22.db")

    def test_missing_report_breaks_chain(self, tmp_path):
        """缺证形态（migration.last 无 report）→ 保守断链。"""
        root = tmp_path
        _make_slot(root, "novel-v0.22.db", books=1)
        _make_slot(root, "novel-v0.23.db", source="novel-v0.22.db")
        # A 对 B 的搬运记录缺 report（老版本形态）＝缺证
        stamp_b = candidate_stamp_hash("novel-v0.23.db", root / "novel-v0.23.db")
        _write_db(root / "novel-v0.24.db", books=1,
                  migration_last={"source_filename": "novel-v0.23.db",
                                  "source_stamp": stamp_b})  # 无 report
        active = root / CUR
        _make_slot(root, CUR, source="novel-v0.24.db")
        chain = trace_carry_chain(root, active)
        assert chain["novel-v0.24.db"] is True
        assert chain["novel-v0.23.db"] is False

    def test_immutable_read_leaves_no_sidecar(self, tmp_path):
        """链证据读取零痕迹：不建 `-shm`、不动源件；`-wal` 未 checkpoint 的记录
        读不到＝None（保守断链，不假装读到了）。"""
        p = tmp_path / "w.db"
        con = sqlite3.connect(p)
        con.execute("PRAGMA journal_mode=wal")
        con.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO app_meta VALUES ('migration.last', '{}')")
        con.commit()
        con2 = sqlite3.connect(p)  # 第二连接挡住「最后连接关闭即删 -wal」
        before = {x.name for x in tmp_path.iterdir()}
        last = migration_last_cached(p)
        during = {x.name for x in tmp_path.iterdir()}  # 关闭前对拍（关连接会清 sidecar）
        con2.close()
        con.close()
        assert before == during  # 零痕迹：链证据读取不新建任何 sidecar
        assert last is None      # -wal 里的记录 immutable 口读不到＝证据缺失

    def test_migration_last_reads_main_file(self, tmp_path):
        """主文件已落盘的完成记录照常读到（immutable 口）。"""
        p = tmp_path / "s.db"
        _write_db(p, books=1, migration_last={"source_filename": "x.db"})
        assert migration_last_cached(p) == {"source_filename": "x.db"}

    def test_wal_aware_read_sees_uncheckpointed_record(self, tmp_path):
        """活跃槽走 WAL 可见口：未 checkpoint 的完成记录能读到（真机 0.49.2 实锤
        ——迁移记录躺 WAL、immutable 读不到）；缓存键按模式分域不互串。"""
        p = tmp_path / "active.db"
        con = sqlite3.connect(p)
        con.execute("PRAGMA journal_mode=wal")
        con.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO app_meta VALUES ('migration.last', ?)",
                    (json.dumps({"source_filename": "novel-v0.24.db"}),))
        con.commit()
        con2 = sqlite3.connect(p)  # 挡住「最后连接关闭即 checkpoint+删 -wal」
        try:
            # immutable 口：主文件里没有 → None（证据缺失）
            assert migration_last_cached(p) is None
            # WAL 可见口：读得到（真机第一跳的正确姿势）
            assert migration_last_cached(p, wal_aware=True) == {
                "source_filename": "novel-v0.24.db"}
            # 两口同文件不同键，互不串
            assert migration_last_cached(p) is None
            assert migration_last_cached(p, wal_aware=True) == {
                "source_filename": "novel-v0.24.db"}
        finally:
            con2.close()
            con.close()


# ── 4.2/4.3 扫描标注＋归档 ────────────────────────────────────────────────


class TestScanChainAnnotationAndArchive:
    def _fixture(self, root: Path):
        _make_slot(root, "novel-v0.22.db", books=1)
        _make_slot(root, "novel-v0.23.db", source="novel-v0.22.db")
        _make_slot(root, "novel-dev.db", books=1)  # 链外
        active = root / CUR
        _make_slot(root, CUR, source="novel-v0.23.db")
        return active

    def test_scan_annotates_chain_carried(self, tmp_path):
        active = self._fixture(tmp_path)
        chain = trace_carry_chain(tmp_path, active)
        items = scan_migration_candidates(tmp_path, "0.25", active, chain_map=chain)
        by = {it["filename"]: it for it in items}
        assert by["novel-v0.22.db"]["chain_carried"] is True
        assert by["novel-v0.23.db"]["chain_carried"] is True
        assert by["novel-dev.db"]["chain_carried"] is False

    def test_scan_without_chain_map_defaults_false(self, tmp_path):
        active = self._fixture(tmp_path)
        items = scan_migration_candidates(tmp_path, "0.25", active)
        assert all(it["chain_carried"] is False for it in items)

    def test_scan_excludes_archive_dir(self, tmp_path):
        """归档件退出盘点；子目录本就进不了文件枚举，显式拒一点名防递归化回归。"""
        root = tmp_path
        active = self._fixture(root)
        assert {it["filename"] for it in scan_migration_candidates(root, "0.25", active)} \
            >= {"novel-v0.22.db", "novel-v0.23.db", "novel-dev.db"}
        assert archive_candidate(root, "novel-v0.22.db", active) is True
        archived = root / ARCHIVE_DIRNAME / "novel-v0.22.db"
        assert archived.exists() and archived.stat().st_size > 0
        assert not (root / "novel-v0.22.db").exists()
        names = {it["filename"] for it in scan_migration_candidates(root, "0.25", active)}
        assert "novel-v0.22.db" not in names

    def test_archive_is_move_not_delete(self, tmp_path):
        """归档＝移动：字节保留在 archive 子目录（可逆），绝不删除。"""
        root = tmp_path
        active = root / CUR
        _write_db(active, books=0)
        _write_db(root / "novel-v0.24.db", books=4)
        src = root / "novel-v0.24.db"
        before = src.read_bytes()
        assert archive_candidate(root, "novel-v0.24.db", active) is True
        moved = root / ARCHIVE_DIRNAME / "novel-v0.24.db"
        assert moved.read_bytes() == before

    def test_archive_rejects_off_chain_and_paths(self, tmp_path, monkeypatch):
        """端点收口：白名单外拒绝（链外件/带路径分隔/活跃库）。"""
        root = tmp_path
        active = root / CUR
        _write_db(active, books=0)
        _write_db(root / "novel-v0.24.db", books=1)
        _write_db(root / "novel-dev.db", books=1)
        monkeypatch.setattr(router, "_archivable_names", lambda r, a: {"novel-v0.24.db"})
        res = asyncio.run(router.archive(router.ArchiveBody(
            filenames=["novel-v0.24.db", "novel-dev.db",
                       f"{ARCHIVE_DIRNAME}/novel-v0.24.db", CUR])))
        assert res["data"]["archived"] == ["novel-v0.24.db"]
        assert set(res["data"]["refused"]) == {"novel-dev.db",
                                               f"{ARCHIVE_DIRNAME}/novel-v0.24.db", CUR}

    def test_archive_candidate_validates_paths(self, tmp_path):
        """归档与删除同源校验：带路径分隔/活跃库/不存在件一律 False。"""
        root = tmp_path
        active = root / CUR
        _write_db(active, books=0)
        (root / ARCHIVE_DIRNAME).mkdir(exist_ok=True)
        _write_db(root / ARCHIVE_DIRNAME / "novel-v0.24.db", books=1)
        assert archive_candidate(root, f"{ARCHIVE_DIRNAME}/novel-v0.24.db", active) is False
        assert archive_candidate(root, CUR, active) is False  # 活跃库不可归档


# ── 3.1 盘点不阻塞请求面 ──────────────────────────────────────────────────


class TestCandidatesOffload:
    def test_scan_runs_in_worker_thread(self, monkeypatch):
        """盘点在 Worker 线程执行；进行中事件循环照常调度（并发请求不被拖住）。"""
        main_ident = threading.get_ident()
        seen: dict = {}
        scan_started = threading.Event()
        release = threading.Event()

        def fake_scan(root, ver, active, chain_map=None):
            seen["ident"] = threading.get_ident()
            scan_started.set()
            release.wait(5)
            return []

        monkeypatch.setattr(router, "scan_migration_candidates", fake_scan)
        monkeypatch.setattr(router, "trace_carry_chain", lambda root, active: {})
        monkeypatch.setattr(router, "_app_meta_value", lambda key: None)
        monkeypatch.setattr(router, "list_quarantined", lambda root: [])

        async def main():
            task = asyncio.create_task(router.candidates())
            # 盘点已在 Worker 线程开跑（若误在事件循环线程同步跑，这里会整体卡死超时）
            await asyncio.wait_for(asyncio.to_thread(scan_started.wait, 5), 5)
            # 盘点进行中：循环心跳照常走＝其余请求不被拖住
            await asyncio.wait_for(asyncio.sleep(0), 0.2)
            release.set()
            await asyncio.wait_for(task, 5)

        asyncio.run(main())
        assert seen["ident"] != main_ident
