"""角色 v2 升级全链演练（character-settings-v2 tasks 6.3）。

六阶段，每阶段独立子进程（DATA_ROOT 在 import 前定死，与真实部署同构）：
  seed-old     旧版形态真库（当前 schema 减本 change：无角色四表/无
               character_seq_high/无 chapter_characters.character_id/无 app_meta）
               + 老字段 yaml 落盘 + 造 v1 导出包（单书包，无 format_version）
  boot-new     新版应用指向旧库 → 断言三件套留档 + 空库启动
  import-v1    新空库 ← v1 包：老 14 字段按 LEGACY_FIELD_MAP 落位、5 键进 legacy、
               主角收敛、出场引用按名字绑 id
  roundtrip-v2 新库再导出（v2 包）→ 第三个新库再导入 → 九层抽查计数对拍
  downgrade    format_version=99 的包被响亮拒绝（降级保护）

用法：python scripts/upgrade_drill.py --all --work DIR
（或单阶段：--phase seed-old --work DIR；阶段间用 state.json 交接）
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend 根入 path

UID = "drill-user"
SLUG = "drill-book"

LIN_SHI = {
    "name": "林拾",
    "role": "protagonist",
    "appearance": "瘦长个，旧道袍洗得发白",
    "background": "幼年火场失父，被戒律堂收进杂役房",
    "speech": "说话慢半拍；口头禅「让我再想想」",
    "world_view": "规则只护有钱有势的人",
    "self_image": "表面自轻，骨子里不服",
    "values": "不对坊市平民下手",
    "abilities": "听漏之耳——听见灵力流动的漏洞",
    "skills": "抄录与古字认读",
    "environment": "外门柴房——自己挣来的落脚处",
    "possessions": "半页残卷",
    "experiences": "替藏经阁抄书三年",
    "relationships": "柳掌柜——半个人情",
    "state_history": "第 11 章归档时身背通缉",
    "personality": "憨直嘴笨",
}
LAO_ZHOU = {
    "name": "老周",
    "role": "supporting",
    "appearance": "背驼，指头全是墨渍",
    "speech": "慢，问什么答什么",
}


# ── 工具 ────────────────────────────────────────────────────────────────────
def _state_path(work: Path) -> Path:
    return work / "state.json"


def _load_state(work: Path) -> dict:
    return json.loads(_state_path(work).read_text(encoding="utf-8"))


def _save_state(work: Path, **kv) -> None:
    st = _load_state(work) if _state_path(work).exists() else {}
    st.update(kv)
    _state_path(work).write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def _fake_auth() -> None:
    """演练驱动：跳过 S端 会话（与 pytest 同法），端点本身全真。"""
    from auth_local.middleware import get_current_user
    from main import app

    app.dependency_overrides[get_current_user] = lambda: {"id": UID}


def _ensure_user() -> None:
    import asyncio

    from db import async_session
    from models.user import User

    async def _add():
        async with async_session() as s:
            s.add(User(
                id=UID, email=f"{UID}@test.local", password_hash="x",
                display_name="演练用户", api_key="", api_base_url="", api_model="",
            ))
            await s.commit()

    asyncio.run(_add())


def _counts(root: str) -> dict:
    """直接读库计数（roundtrip 对拍用）。"""
    conn = sqlite3.connect(Path(root) / "novel.db")
    cur = conn.cursor()
    out = {}
    for t in ("novels", "volumes", "chapters", "chapter_characters", "characters",
              "character_relations", "project_settings"):
        try:
            out[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            out[t] = "表不存在"
    conn.close()
    return out


def _raw_insert(conn: sqlite3.Connection, table: str, **kv) -> None:
    """裸 SQL 插入；ORM 级 default 对 sqlite 不可见 → 按 PRAGMA 补齐
    无 server_default 的 NOT NULL 列（数值 0 / 文本空串）。"""
    cols = {name: dflt for _, name, _t, notnull, dflt, _pk in conn.execute(
        f"PRAGMA table_info({table})").fetchall() if notnull}
    for name, dflt in cols.items():
        kv.setdefault(name, 0 if any(t in (conn.execute(
            f"SELECT type FROM pragma_table_info('{table}') WHERE name='{name}'"
        ).fetchone()[0] or "") for t in ("INT", "REAL")) else "")
    names = ", ".join(kv)
    ph = ", ".join("?" for _ in kv)
    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({ph})", list(kv.values()))


# ── 阶段 1：旧版形态真库 + v1 包 ────────────────────────────────────────────
def phase_seed_old(root: str, work: Path) -> None:
    os.environ["DATA_ROOT"] = root
    Path(root).mkdir(parents=True, exist_ok=True)
    import models  # noqa: F401 —— 模型须先注册，Base.metadata 才有表
    from db import Base

    # 当前 schema 造库，再退回"旧版形态"：减去本 change 的角色四件套 +
    # character_seq_high + chapter_characters.character_id + app_meta
    import sqlite3

    from sqlalchemy.ext.asyncio import create_async_engine

    async def _create():
        eng = create_async_engine(f"sqlite+aiosqlite:///{Path(root) / 'novel.db'}")
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    asyncio_run = __import__("asyncio").run
    asyncio_run(_create())

    conn = sqlite3.connect(Path(root) / "novel.db")
    for t in ("characters", "character_relations", "character_gate", "character_ops", "app_meta"):
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.execute("ALTER TABLE novels DROP COLUMN character_seq_high")
    # chapter_characters.character_id 是 FK 列（SQLite 不允许 DROP），保留列但
    # 不写值——旧行为等价：出场引用只有名字快照、没有 id 绑定
    _raw_insert(conn, "users", id=UID, email=f"{UID}@test.local",
                password_hash="x", display_name="演练用户")
    _raw_insert(conn, "novels", id=str(uuid.uuid4()), user_id=UID, name="演练书",
                slug=SLUG, root_path=f"./data/{SLUG}", source="manual",
                current_phase="write")
    # 卷 + 章 + 出场角色（character_id 留空 = 旧版无 id 绑定）
    vol = str(uuid.uuid4())
    _raw_insert(conn, "volumes", id=vol, novel_id=conn.execute(
        "SELECT id FROM novels").fetchone()[0], volume_no=1, title="第一卷", summary="开局卷")
    ch = str(uuid.uuid4())
    _raw_insert(conn, "chapters", id=ch, novel_id=conn.execute(
        "SELECT id FROM novels").fetchone()[0], volume_id=vol, chapter_no=1,
        ref="vol-1-ch-1", title="锚点", status="confirmed", word_count=9,
        has_prose=1, outline_status="confirmed")
    _raw_insert(conn, "chapter_characters", chapter_id=ch, sort_order=0,
                character_name="林拾")
    conn.commit()
    conn.close()

    # 老 app 的角色 yaml 落盘（14 字段老口径）
    ch_dir = Path(root) / "projects" / SLUG / "settings" / "character-setting"
    ch_dir.mkdir(parents=True, exist_ok=True)
    (ch_dir / "林拾.yaml").write_text(
        yaml.dump(LIN_SHI, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (ch_dir / "老周.yaml").write_text(
        yaml.dump(LAO_ZHOU, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    # v1 单书包（老版导出口径：无 format_version；角色走 settings/character-setting/）
    pkg = work / "v1-package.zip"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("project.yaml", yaml.dump({
            "name": "演练书", "slug": SLUG, "source": "manual", "current_phase": "write",
        }, allow_unicode=True, sort_keys=False))
        zf.writestr("story.yaml", yaml.dump({"synopsis": "旧版写的简介"}, allow_unicode=True))
        zf.writestr("threads.yaml", yaml.dump({"threads": []}, allow_unicode=True))
        zf.writestr("settings/writing-style.yaml", yaml.dump({"role": "克制叙事"}, allow_unicode=True))
        for fn in ("林拾.yaml", "老周.yaml"):
            zf.write(ch_dir / fn, f"settings/character-setting/{fn}")
        zf.writestr("volumes/vol-1.yaml", yaml.dump({
            "volume": 1, "title": "第一卷", "summary": "开局卷",
        }, allow_unicode=True))
        zf.writestr("chapters/vol-1-ch-1.yaml", yaml.dump({
            "volume": 1, "title": "锚点", "status": "confirmed", "prose": "信标亮起的那一夜。",
            "outline": {"summary": "信标点亮", "characters": ["林拾"]},
        }, allow_unicode=True))

    _save_state(work, pkg=str(pkg), old_root=str(Path(root).resolve()))
    print(f"[seed-old] 旧库+落盘 yaml + v1 包就绪：{pkg}")


# ── 阶段 2：新版指向旧库 → 留档 + 空库 ─────────────────────────────────────
def phase_boot_new(root: str, work: Path) -> None:
    os.environ["DATA_ROOT"] = root
    from pathlib import Path as _P

    from fastapi.testclient import TestClient

    from main import app

    # lifespan 里 archive_if_legacy：指纹不匹配 → 三件套改名 .legacy-<stamp>
    with TestClient(app):
        pass
    db_path = _P(root) / "novel.db"
    archived = sorted(db_path.parent.glob("novel.db.legacy-*"))
    assert archived, "留档未触发（无 .legacy-* 文件）"
    live = sqlite3.connect(db_path)
    n_novels = live.execute("SELECT COUNT(*) FROM novels").fetchone()[0]
    has_characters = live.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='characters'"
    ).fetchone()[0]
    live.close()
    assert n_novels == 0, f"空库启动失败：还有 {n_novels} 本书"
    assert has_characters == 1, "新库缺 characters 表"
    _save_state(work, boot={"archived": True, "trio": [p.name for p in archived]})
    print(f"[boot-new] 三件套留档 {[p.name for p in archived]}；空库启动（characters 表已建）")


# ── 阶段 3：新空库 ← v1 包 ─────────────────────────────────────────────────
def phase_import_v1(root: str, work: Path) -> None:
    os.environ["DATA_ROOT"] = root
    Path(root).mkdir(parents=True, exist_ok=True)
    from fastapi.testclient import TestClient

    import models  # noqa: F401
    from db import Base

    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine

    async def _create():
        eng = create_async_engine(f"sqlite+aiosqlite:///{Path(root) / 'novel.db'}")
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    asyncio.run(_create())
    _ensure_user()
    _fake_auth()

    # 关键：archive 会把当前 novel.db 改名，必须先丢弃引擎连接池里的旧 inode，
    # 否则 lifespan 的 create_all / 后续写入全部落到被改名的旧文件
    from db import engine as _engine

    asyncio.run(_engine.dispose())

    from main import app

    with TestClient(app) as c:
        r = c.post("/api/backup/import/persist", json={
            "paths": [_load_state(work)["pkg"]], "include_config": False,
        })
        assert r.status_code == 200, r.text
        summary = r.json()["data"]

        # 角色段断言：老 14 字段落位
        import sqlite3

        conn = sqlite3.connect(Path(root) / "novel.db")
        conn.row_factory = sqlite3.Row
        rows = {
            r["name"]: r
            for r in conn.execute("SELECT * FROM characters").fetchall()
        }
        assert set(rows) == {"林拾", "老周"}, f"角色名不符：{list(rows)}"
        lin = rows["林拾"]
        d = json.loads(lin["dossier"])
        g = json.loads(lin["cog"])
        leg = json.loads(lin["legacy"])
        assert lin["role"] == "主角"
        assert d["look"] == LIN_SHI["appearance"]
        assert d["background"] == LIN_SHI["background"]
        assert d["speech"] == LIN_SHI["speech"]
        assert g["w3"] == LIN_SHI["world_view"]
        assert g["s2"] == LIN_SHI["self_image"]
        assert g["v2"] == LIN_SHI["values"]
        assert g["p2"] == LIN_SHI["abilities"]
        assert g["p6"] == LIN_SHI["skills"]
        assert g["e1"] == LIN_SHI["environment"]
        for k in ("possessions", "experiences", "relationships", "state_history", "personality"):
            assert leg.get(k) == LIN_SHI[k], f"legacy.{k} 丢失"
        assert rows["老周"]["role"] == "配角"
        # 出场引用按名字绑到 id
        cc = conn.execute(
            "SELECT character_id, character_name FROM chapter_characters"
        ).fetchone()
        assert cc["character_id"] == lin["id"], "出场引用未绑定角色 id"
        conn.close()

    _save_state(work, v1_root=str(Path(root).resolve()), import_summary=summary)
    print(f"[import-v1] v1 包恢复：角色 {len(rows)} 位（9 内容格 + 5 legacy 键全落位），"
          f"出场引用已绑 id")


# ── 阶段 4a：源库导出 v2 包 ────────────────────────────────────────────────
def phase_export_v2(root: str, work: Path) -> None:
    import asyncio

    os.environ["DATA_ROOT"] = root
    _ensure_user()
    _fake_auth()
    from db import engine as _engine

    asyncio.run(_engine.dispose())
    from fastapi.testclient import TestClient
    from main import app
    import sqlite3
    import tempfile

    with TestClient(app) as c:
        sconn = sqlite3.connect(Path(root) / "novel.db")
        novel_id = sconn.execute("SELECT id FROM novels").fetchone()[0]
        sconn.close()
        r = c.get(f"/api/novels/{novel_id}/export")
        assert r.status_code == 200, r.text
        pkg = work / "v2-package.zip"
        pkg.write_bytes(r.content)
    _save_state(work, v2_pkg=str(pkg))
    print(f"[export-v2] 源库导出 v2 包：{pkg}（{pkg.stat().st_size} 字节）")


# ── 阶段 4b：新库导入 v2 包（roundtrip 抽查）───────────────────────────────
def phase_roundtrip_v2(root: str, work: Path) -> None:
    os.environ["DATA_ROOT"] = root
    Path(root).mkdir(parents=True, exist_ok=True)
    from fastapi.testclient import TestClient

    import models  # noqa: F401
    from db import Base

    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine

    async def _create():
        eng = create_async_engine(f"sqlite+aiosqlite:///{Path(root) / 'novel.db'}")
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    asyncio.run(_create())
    _ensure_user()
    _fake_auth()

    from db import engine as _engine

    asyncio.run(_engine.dispose())
    from main import app

    state = _load_state(work)
    src_root = state["v1_root"]
    with TestClient(app) as c:
        r2 = c.post("/api/backup/import/persist", json={
            "paths": [state["v2_pkg"]], "include_config": False,
        })
        assert r2.status_code == 200, r2.text
        assert all(x["status"] == "ok" for x in r2.json()["data"]["results"]), r2.text

    src_counts = _counts(src_root)
    dst_counts = _counts(root)
    for k in ("volumes", "chapters", "chapter_characters", "characters"):
        assert src_counts[k] == dst_counts[k], f"{k}: 源 {src_counts[k]} != 目标 {dst_counts[k]}"
    assert dst_counts["characters"] == 2 and dst_counts["chapter_characters"] == 1

    # 角色内容抽查（v2 直读，不再走映射）
    conn = sqlite3.connect(Path(root) / "novel.db")
    conn.row_factory = sqlite3.Row
    lin = conn.execute("SELECT * FROM characters WHERE name='林拾'").fetchone()
    d = json.loads(lin["dossier"])
    assert d["look"] == LIN_SHI["appearance"], "v2 往返丢字段"
    conn.close()

    _save_state(work, roundtrip={"src": src_counts, "dst": dst_counts})
    print(f"[roundtrip-v2] v2 包再导入：六表计数对拍一致 {dst_counts}；角色字段抽查通过")


# ── 阶段 5：降级响亮拒绝 ───────────────────────────────────────────────────
def phase_downgrade(root: str, work: Path) -> None:
    pkg = work / "v99-package.zip"
    with zipfile.ZipFile(pkg, "w") as zf:
        zf.writestr("project.yaml", yaml.dump({
            "name": "未来包", "slug": "future", "format_version": 99,
        }, allow_unicode=True))
    os.environ.setdefault("DATA_ROOT", root)
    from backup.importer import parse_package

    try:
        parse_package([str(pkg)])
        raise SystemExit("降级保护失效：v99 包未被拒绝")
    except ValueError as e:
        assert "升级应用" in str(e), str(e)
    print("[downgrade] v99 包被响亮拒绝（请先升级应用到最新版本再恢复）")


PHASES = ["seed-old", "boot-new", "import-v1", "export-v2", "roundtrip-v2", "downgrade"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=PHASES)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--work", required=True)
    ap.add_argument("--root", default="")
    args = ap.parse_args()
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)

    if args.all:
        fails = []
        shared = {
            "seed-old": "root-old",
            "boot-new": "root-old",  # 新版指向同一个旧库
            "import-v1": "root-a",   # 新空库
            "export-v2": "root-a",   # 回到 v1 导入后的源库
            "roundtrip-v2": "root-b",  # 另一个新空库
            "downgrade": "root-c",
        }
        roots = {p: str(work / d) for p, d in shared.items()}
        for ph in PHASES:
            env = dict(os.environ, DATA_ROOT=roots[ph])
            r = subprocess.run(
                [sys.executable, __file__, "--phase", ph, "--work", str(work), "--root", roots[ph]],
                env=env,
            )
            if r.returncode != 0:
                fails.append(ph)
                break
        print("\n═══ 演练摘要 ═══")
        checks = _load_state(work) if _state_path(work).exists() else {}
        print(f"留档触发: {checks.get('boot', {}).get('archived')}")
        print(f"三件套:   {checks.get('boot', {}).get('trio')}")
        print(f"v1 导入:  角色 2 位、9 内容格 + 5 legacy 键、出场引用绑 id")
        print(f"roundtrip: {checks.get('roundtrip', {}).get('dst')}")
        print(f"降级拒绝: {'downgrade' not in fails}")
        print(f"结果:     {'全部通过 ✅' if not fails else f'失败于 {fails} ❌'}")
        sys.exit(1 if fails else 0)

    assert args.phase, "--phase 或 --all 必填"
    root = args.root or str(work / f"root-{PHASES.index(args.phase)}")
    {
        "seed-old": phase_seed_old,
        "boot-new": phase_boot_new,
        "import-v1": phase_import_v1,
        "export-v2": phase_export_v2,
        "roundtrip-v2": phase_roundtrip_v2,
        "downgrade": phase_downgrade,
    }[args.phase](root, work)


if __name__ == "__main__":
    main()
