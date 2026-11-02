"""merged 视图测试（c-kb-baseline 批B）：选择器并入/列表分页/计数/详情/覆盖动作面/备份/冷启动。

基线层是设备级共享表（同一 pytest 进程内所有用例共用），本模块每个用例先清空
只读层与覆盖表，再按自己的包数据播种。
"""

import asyncio
import json
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy import select as sel

from auth_local.middleware import get_current_user
from db import async_session
from kb.baseline import VERSION_KEY, content_sha, proxy_id
from main import app
from models.app_meta import AppMeta
from models.kb import (
    KbBaselineEntry,
    KbBaselineOverlay,
    KbBaselineTag,
    KbEntry,
    KbEntryTag,
)
from models.user import User

CONCEPTS = ("手法", "文风", "文笔")


def _run(coro):
    return asyncio.run(coro)


def _b(src_key: str, title: str, *, concept: str = "手法", genre: str = "",
       instruction: str | None = None, when: dict | None = None,
       slot: str = "打斗-节奏") -> dict:
    return {
        "src_key": src_key, "title": title, "concept": concept, "genre": genre,
        "instruction": instruction or f"{title}：交手先守后攻，招式收在第三拍。",
        "payload": {"slot": slot, "scene": (when or {}).get("scene", "打斗")},
        "when": when if when is not None else {"scene": "打斗"},
    }


async def _reset_baseline() -> None:
    async with async_session() as db:
        await db.execute(delete(KbBaselineTag))
        await db.execute(delete(KbBaselineEntry))
        await db.execute(delete(KbBaselineOverlay))
        meta = await db.get(AppMeta, VERSION_KEY)
        if meta:
            await db.delete(meta)
        await db.commit()


async def _seed_pack(entries: list[dict], *, version: int = 1) -> list[str]:
    from kb.baseline import _tags_for

    ids: list[str] = []
    async with async_session() as db:
        for e in entries:
            eid = proxy_id(e["src_key"])
            ids.append(eid)
            when = e.get("when") or {}
            db.add(KbBaselineEntry(
                entry_id=eid, src_key=e["src_key"], pack_version=version,
                genre=e.get("genre") or "", concept=e.get("concept") or "",
                title=(e.get("title") or "")[:40], instruction=e["instruction"],
                when_json=json.dumps(when, ensure_ascii=False),
                payload_json=json.dumps(e.get("payload") or {}, ensure_ascii=False),
                scope="scene" if when else "base",
                slot=str((e.get("payload") or {}).get("slot") or ""),
                content_sha256=content_sha(e["instruction"]),
                published_at=datetime(2026, 11, 1),
            ))
            for dim, value in _tags_for(e):
                db.add(KbBaselineTag(entry_id=eid, dim=dim, value=value))
        meta = await db.get(AppMeta, VERSION_KEY)
        if meta is None:
            db.add(AppMeta(key=VERSION_KEY, value=str(version)))
        else:
            meta.value = str(version)
        await db.commit()
    return ids


async def _seed_user(*, uid: str | None = None, entries: int = 1,
                     genre: str = "", concept: str = "手法") -> tuple[str, list[str]]:
    uid = uid or f"mg-{uuid.uuid4().hex[:8]}"
    ids: list[str] = []
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
        await db.flush()
        for i in range(entries):
            e = KbEntry(
                user_id=uid, genre=genre, concept=concept, concept_id=f"{genre}:{concept}",
                title=f"用户手法{i}", payload_json=json.dumps(
                    {"slot": "打斗-节奏", "scene": "打斗"}, ensure_ascii=False),
                instruction=f"用户条目{i}：交手先守后攻，招式收在第三拍。",
                when_json=json.dumps({"scene": "打斗"}, ensure_ascii=False),
                src_kind="manual",
            )
            db.add(e)
            await db.flush()
            ids.append(e.id)
            tags = [
                KbEntryTag(entry_id=e.id, user_id=uid, dim="concept", value=concept),
                KbEntryTag(entry_id=e.id, user_id=uid, dim="scope", value="scene"),
                KbEntryTag(entry_id=e.id, user_id=uid, dim="scene", value="打斗"),
                KbEntryTag(entry_id=e.id, user_id=uid, dim="slot", value="打斗-节奏"),
            ]
            if genre:
                tags.append(KbEntryTag(entry_id=e.id, user_id=uid, dim="genre", value=genre))
            db.add_all(tags)
        await db.commit()
    return uid, ids


@pytest.fixture
def base_env():
    _run(_reset_baseline())
    yield
    _run(_reset_baseline())


def test_选择器_基线并入_副本遮蔽_隐藏排除(base_env):
    from kb.match import MatchSignals, select_block

    uid = f"mg-{uuid.uuid4().hex[:8]}"

    async def _go():
        u = (await _seed_user(uid=uid, entries=1))[0]
        ids = await _seed_pack([
            _b("baseline:玄幻:tech-a", "官方手法A"),
            _b("baseline:玄幻:tech-b", "官方手法B"),
        ])
        async with async_session() as db:
            from models.kb import KbEntry as _E

            user_id = (await db.execute(sel(_E.id).where(_E.user_id == u))).scalar_one()
            signals = MatchSignals(scene="打斗", genre="")
            first = await select_block(db, user_id=u, signals=signals, genre="")
            got1 = {i.entry.id for i in first.items}

            from kb.merged import set_overlay

            await set_overlay(db, user_id=u, entry_id=ids[0], action="edit",
                              instruction="用户的改写版本：先让三招再还手。")
            await set_overlay(db, user_id=u, entry_id=ids[1], action="hide")
            second = await select_block(db, user_id=u, signals=signals, genre="")
            by_id = {i.entry.id: i.entry for i in second.items}
            return got1, ids, user_id, by_id

    got1, ids, user_id, by_id = _run(_go())
    # 首轮：用户条目＋两条基线同池
    assert user_id in got1 and set(ids) <= got1
    # edit 副本遮蔽原件文本；hide 条目不再出现
    assert by_id[ids[0]].instruction == "用户的改写版本：先让三招再还手。"
    assert ids[1] not in by_id
    assert user_id in by_id


def test_列表_merged分页不漏不重(base_env):
    from kb.service import list_entries

    async def _go():
        uid, user_ids = await _seed_user(entries=6, genre="都市")
        base_ids = await _seed_pack([
            _b(f"baseline:都市:tech-{i}", f"官方手法{i}", genre="都市") for i in range(6)
        ])
        async with async_session() as db:
            seen: list[str] = []
            cursor = ""
            pages = 0
            while True:
                rows, cursor = await list_entries(
                    db, user_id=uid, genre="都市", cursor=cursor, limit=3)
                pages += 1
                seen += [e.id for e in rows]
                if not cursor:
                    break
                assert pages < 10
            return seen, set(user_ids) | set(base_ids), pages

    seen, expected, pages = _run(_go())
    assert pages > 1                      # 真跨页
    assert len(seen) == len(set(seen))    # 不重
    assert set(seen) == expected          # 不漏


def test_来源筛选与题材计数(base_env):
    from kb.service import genre_counts, list_entries

    async def _go():
        uid, user_ids = await _seed_user(entries=2, genre="都市")
        base_ids = await _seed_pack([
            _b("baseline:都市:tech-0", "官方手法0", genre="都市"),
            _b("baseline:都市:tech-1", "官方手法1", genre="都市"),
        ])
        async with async_session() as db:
            only_base, _c = await list_entries(
                db, user_id=uid, genre="都市", src="官方精选", limit=50)
            only_user, _c2 = await list_entries(
                db, user_id=uid, genre="都市", src="手录", limit=50)
            counts = await genre_counts(db, user_id=uid)
            return (
                {e.id for e in only_base},
                {e.id for e in only_user},
                set(base_ids), set(user_ids),
                counts.get("都市"),
            )

    only_base, only_user, base_ids, user_ids, n = _run(_go())
    assert only_base == base_ids
    assert only_user == user_ids
    assert n == 4  # 用户 2 + 基线 2


def test_详情与覆盖端点_动作矩阵(base_env):
    ids: list[str] = []

    async def _seed():
        ids.extend(await _seed_pack([_b("baseline:玄幻:tech-a", "官方手法A")]))

    _run(_seed())
    eid = ids[0]
    uid = f"mg-{uuid.uuid4().hex[:8]}"

    async def _setup():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            await db.commit()

    _run(_setup())

    def _override():
        return {"id": uid, "email": f"{uid}@t.local"}

    app.dependency_overrides[get_current_user] = _override
    try:
        with TestClient(app) as c:
            # 详情：层与来源标签随层派生
            r = c.get(f"/api/kb/entries/{eid}")
            assert r.status_code == 200, r.text
            d = r.json()["data"]
            assert d["layer"] == "baseline" and d["src_kind"] == "baseline"
            assert d["official_update"] is False

            # 编辑＝存副本（原件不变）
            r = c.put(f"/api/kb/entries/{eid}/baseline-override",
                      json={"action": "edit", "instruction": "用户改写：先守后攻，第三拍借力。"})
            assert r.status_code == 200, r.text
            r = c.get(f"/api/kb/entries/{eid}")
            d = r.json()["data"]
            assert d["instruction"].startswith("用户改写") and d["overlaid"] is True

            # 官方修订 → 「官方有新版」双哈希可判
            async def _official_update():
                async with async_session() as db:
                    row = await db.get(KbBaselineEntry, eid)
                    row.instruction = "官方第二版：先守后攻，再借力反打。"
                    row.content_sha256 = content_sha(row.instruction)
                    await db.commit()

            _run(_official_update())
            d = c.get(f"/api/kb/entries/{eid}").json()["data"]
            assert d["official_update"] is True
            assert d["instruction"].startswith("用户改写")  # 副本继续遮蔽

            # 恢复官方版＝删副本，透出新原件
            r = c.delete(f"/api/kb/entries/{eid}/baseline-override")
            assert r.status_code == 200, r.text
            d = c.get(f"/api/kb/entries/{eid}").json()["data"]
            assert d["instruction"].startswith("官方第二版")
            assert d["overlaid"] is False and d["official_update"] is False

            # 隐藏 → 详情 404、恢复后重见
            assert c.put(f"/api/kb/entries/{eid}/baseline-override",
                         json={"action": "hide"}).status_code == 200
            assert c.get(f"/api/kb/entries/{eid}").status_code == 404
            assert c.delete(f"/api/kb/entries/{eid}/baseline-override").status_code == 200
            assert c.get(f"/api/kb/entries/{eid}").status_code == 200

            # edit→hide 保留 content（还原素材），矩阵切换不丢文本
            c.put(f"/api/kb/entries/{eid}/baseline-override",
                  json={"action": "edit", "instruction": "保留这段副本。"})
            c.put(f"/api/kb/entries/{eid}/baseline-override", json={"action": "hide"})

            async def _ov():
                async with async_session() as db:
                    return (await db.execute(sel(KbBaselineOverlay).where(
                        KbBaselineOverlay.user_id == uid))).scalar_one()

            ov = _run(_ov())
            assert ov.action == "hide" and ov.content == "保留这段副本。"

            # 闸门：超长指令拒收；用户条目 id 走覆盖端点＝404
            r = c.put(f"/api/kb/entries/{eid}/baseline-override",
                      json={"action": "edit", "instruction": "长" * 241})
            assert r.status_code == 422
            r = c.put(f"/api/kb/entries/{uuid.uuid4()}/baseline-override",
                      json={"action": "hide"})
            assert r.status_code == 404

            # 基线原件全程未被修改
            async def _row():
                async with async_session() as db:
                    return await db.get(KbBaselineEntry, eid)

            row = _run(_row())
            assert row.instruction.startswith("官方第二版")
            assert row.content_sha256 == content_sha(row.instruction)
    finally:
        app.dependency_overrides.clear()


def test_pref_基线可反馈(base_env):
    async def _seed():
        return await _seed_pack([_b("baseline:玄幻:tech-a", "官方手法A")])

    eid = _run(_seed())[0]
    uid = f"mg-{uuid.uuid4().hex[:8]}"

    async def _setup():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            await db.commit()

    _run(_setup())
    app.dependency_overrides[get_current_user] = lambda: {"id": uid, "email": f"{uid}@t.local"}
    try:
        with TestClient(app) as c:
            r = c.post(f"/api/kb/entries/{eid}/pref", json={"useful": True})
            assert r.status_code == 200, r.text
            assert r.json()["data"]["adopt_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_备份_覆盖记录roundtrip(base_env):
    import io
    import zipfile

    import yaml

    from backup.export import build_config_package_bytes
    from backup.importer import _restore_config

    uid, _ = _run(_seed_user(entries=0))
    ids = _run(_seed_pack([_b("baseline:玄幻:tech-a", "官方手法A")]))

    async def _seed_ov():
        async with async_session() as db:
            db.add(KbBaselineOverlay(
                user_id=uid, src_key="baseline:玄幻:tech-a", action="edit",
                content="我的副本。", base_content_sha256=content_sha("官方手法A：交手先守后攻，招式收在第三拍。")))
            await db.commit()

    _run(_seed_ov())

    async def _export():
        async with async_session() as db:
            return await build_config_package_bytes(db, uid)

    data, _name = _run(_export())
    zf = zipfile.ZipFile(io.BytesIO(data))
    cfg = yaml.safe_load(zf.read("config.yaml"))
    rows = cfg["knowledge_base"]["baseline_overlays"]
    assert len(rows) == 1 and rows[0]["src_key"] == "baseline:玄幻:tech-a"
    assert rows[0]["action"] == "edit" and rows[0]["content"] == "我的副本。"

    uid2 = f"mg2-{uuid.uuid4().hex[:8]}"

    async def _import():
        async with async_session() as db:
            db.add(User(id=uid2, email=f"{uid2}@t.local", password_hash="x"))
            await db.commit()
            s1 = await _restore_config(db, uid2, cfg)
            await db.commit()
            s2 = await _restore_config(db, uid2, cfg)
            await db.commit()
            rows2 = (await db.execute(sel(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == uid2))).scalars().all()
            return s1, s2, rows2

    s1, s2, rows2 = _run(_import())
    assert s1["knowledge_base"]["baseline_overlays"]["created"] == 1
    assert s2["knowledge_base"]["baseline_overlays"]["skipped"] == 1  # 幂等
    assert len(rows2) == 1 and rows2[0].content == "我的副本。"
    assert ids  # 基线层本身不进备份（只读层重同步重建）


def test_冷启动回退域_零绑定出块(base_env):
    """D0-3：零绑定账号 → 基线域出块；基线未就绪 → 无块。"""
    from models.chapter import Chapter
    from models.project import Novel
    from models.volume import Volume

    async def _go():
        uid = f"mg-{uuid.uuid4().hex[:8]}"
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            novel = Novel(
                user_id=uid, name="冷启动书", slug=uuid.uuid4().hex[:12],
                root_path=f"./data/{uuid.uuid4().hex[:12]}", source="manual",
                current_phase="write",
            )
            db.add(novel)
            await db.flush()
            vol = Volume(project_id=novel.id, volume_no=1, title="卷")
            db.add(vol)
            await db.flush()
            db.add(Chapter(
                project_id=novel.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
                title="第一章", summary="与老祖正面交锋，硬撼对方底牌",
                primary_mood="燃", plot_stage="高潮爆发",
            ))
            await db.commit()
            return uid, novel.id, novel.root_path

    uid, novel_id, root_path = _run(_go())

    # 书题材落 story KV（select 回退域必须按它收窄，不能把别题材的基线串进来）
    async def _story():
        from filesystem.storage import get_storage

        await get_storage().write_yaml(root_path, "story.yaml", {"genre": "玄幻"})

    _run(_story())

    # 基线层空 → 回退域不存在 → 无块
    block0, run0, _ = _run(_prepare(novel_id, "vol-1-ch-1", uid))
    assert block0 is None and run0 is None

    _run(_seed_pack([
        _b("baseline:玄幻:tech-a", "本题材手法", genre="玄幻",
           instruction="本题材专用：交手先守后攻，招式收在第三拍。"),
        _b("baseline:都市:tech-b", "别题材手法", genre="都市",
           instruction="别题材专用：交锋写成交谈，火气压在话里。"),
    ]))

    block, run_id, items = _run(_prepare(novel_id, "vol-1-ch-1", uid))
    assert block and run_id and items, "基线就绪＋零绑定应出块"
    assert "【本章写法指引】" in block
    assert "本题材专用" in block
    assert "别题材专用" not in block, "回退域必须按书题材收窄"

    async def _domain():
        from write.write_block import _binding_domain

        async with async_session() as db:
            return await _binding_domain(db, novel_id)

    genre, concepts, fp = _run(_domain())
    assert genre == "玄幻" and list(concepts) == ["手法", "文风", "文笔"]
    assert fp and len(fp) == 64


async def _prepare(novel_id, chapter_ref, uid):
    from write.write_block import prepare_write_block

    async with async_session() as db:
        return await prepare_write_block(
            db, novel_id=novel_id, chapter_ref=chapter_ref, user_id=uid)


def test_整理候选不含基线(base_env):
    """B7：AI 整理候选域恒为 kb_entries——基线 id 结构性不可达。"""
    import inspect

    import kb.organize as org

    src = inspect.getsource(org)
    assert "KbBaseline" not in src  # 整理模块不接触基线层（结构性回归钉）


def test_digest_基线短名单可重建(base_env):
    """kb_baseline_tags 同步物化：短名单只读标签列，不扫 payload_json。"""
    from kb.match import MatchSignals
    from kb.merged import digest_baseline_ids

    async def _go():
        ids = await _seed_pack([
            _b("baseline:玄幻:tech-a", "手法A"),
            _b("baseline:玄幻:style-a", "文风A", concept="文风", when={"scene": "打斗"},
               slot="tone"),
            _b("baseline:玄幻:style-b", "文笔B", concept="文笔", when={"scene": "打斗"},
               slot="rule"),
        ])
        async with async_session() as db:
            g = await digest_baseline_ids(
                db, user_id="anyone", genre="玄幻", concepts=CONCEPTS)
            return ids, g

    ids, g = _run(_go())
    assert ids[0] in g["tech"]
    assert ids[1] in g["style"] and ids[2] in g["style"]
    assert MatchSignals  # 占位使用，防 import 清理误删（短名单与信号同域）


def test_基线层种子未落_kb_entries(base_env):
    """delta 硬约束：kb_entries 里不存在 src_kind="baseline" 的行。"""
    async def _go():
        uid, _ = await _seed_user(entries=1)
        await _seed_pack([_b("baseline:玄幻:tech-a", "官方手法A")])
        async with async_session() as db:
            rows = (await db.execute(
                sel(KbEntry.id).where(KbEntry.user_id == uid, KbEntry.src_kind == "baseline")
            )).all()
            return rows

    assert _run(_go()) == []


def test_同步状态与手动重试端点(base_env):
    """规格「未同步完成不阻断」：状态可查、失败可重试（幂等）。"""
    from kb import baseline as bl

    eid = _run(_seed_pack([_b("baseline:玄幻:tech-a", "官方手法A")]))[0]
    uid = f"mg-{uuid.uuid4().hex[:8]}"

    async def _setup():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            await db.commit()

    _run(_setup())
    app.dependency_overrides[get_current_user] = lambda: {"id": uid, "email": f"{uid}@t.local"}

    calls: list[int] = []

    async def _fake_sync(db=None):
        calls.append(1)
        return {"status": "current", "version": 1}

    orig = bl.sync_baseline
    bl.sync_baseline = _fake_sync
    try:
        with TestClient(app) as c:
            # lifespan 的启动补偿也会调一次（A3 挂接实证）——从这里开始数
            calls.clear()
            r = c.get("/api/kb/baseline/status")
            assert r.status_code == 200, r.text
            assert r.json()["data"] == {"version": 1, "entries": 1}
            assert eid

            r = c.post("/api/kb/baseline/sync")
            assert r.status_code == 200, r.text
            assert r.json()["data"]["status"] == "current"
            assert calls == [1]
    finally:
        bl.sync_baseline = orig
        app.dependency_overrides.clear()


def test_已隐藏列表可回读_恢复默认回到精选(base_env):
    """P1 修复钉：hide 不能是单向门——「已隐藏」筛选必须能拿回 id 并恢复。"""
    eid = _run(_seed_pack([_b("baseline:玄幻:tech-a", "官方手法A")]))[0]
    uid = f"mg-{uuid.uuid4().hex[:8]}"

    async def _setup():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            await db.commit()

    _run(_setup())
    app.dependency_overrides[get_current_user] = lambda: {"id": uid, "email": f"{uid}@t.local"}
    try:
        with TestClient(app) as c:
            assert c.put(
                f"/api/kb/entries/{eid}/baseline-override", json={"action": "hide"}
            ).status_code == 200

            r = c.get("/api/kb/entries", params={"src": "已隐藏"})
            assert r.status_code == 200, r.text
            rows = r.json()["data"]["entries"]
            assert [x["id"] for x in rows] == [eid]
            assert rows[0]["hidden"] is True and rows[0]["instruction"].startswith("官方手法A")

            # 常规列表不再出现（隐藏语义不变）
            all_rows = c.get("/api/kb/entries").json()["data"]["entries"]
            assert eid not in {x["id"] for x in all_rows}

            # 恢复默认 → 回官方精选
            assert c.delete(f"/api/kb/entries/{eid}/baseline-override").status_code == 200
            r2 = c.get("/api/kb/entries", params={"src": "官方精选"})
            assert eid in {x["id"] for x in r2.json()["data"]["entries"]}
            assert c.get("/api/kb/entries", params={"src": "已隐藏"}).json()["data"]["entries"] == []
    finally:
        app.dependency_overrides.clear()


def test_图谱聚合含基线格子(base_env):
    """P2 修复钉：格子计数与题材栏/下钻同口径（纯基线账号图谱不再空白）。"""
    _run(_seed_pack([
        _b("baseline:玄幻:tech-a", "官方手法A", genre="玄幻"),
        _b("baseline:都市:tech-b", "官方手法B", genre="都市"),
    ]))
    uid = f"mg-{uuid.uuid4().hex[:8]}"

    async def _setup():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            await db.commit()

    _run(_setup())
    app.dependency_overrides[get_current_user] = lambda: {"id": uid, "email": f"{uid}@t.local"}
    try:
        with TestClient(app) as c:
            agg = c.get("/api/kb/graph/aggregate").json()["data"]
            cells = {n["id"]: n["count"] for n in agg["nodes"] if n["kind"] == "cell"}
            genres = {n["id"]: n["count"] for n in agg["nodes"] if n["kind"] == "genre"}
            assert cells == {"cell:玄幻:手法": 1, "cell:都市:手法": 1}
            assert genres == {"genre:玄幻": 1, "genre:都市": 1}
            # 下钻数量与格子计数一致（同一 merged 口径）
            cell = c.get("/api/kb/graph/cell", params={"genre": "玄幻", "concept": "手法"})
            assert len(cell.json()["data"]["nodes"]) == cells["cell:玄幻:手法"]
    finally:
        app.dependency_overrides.clear()


def test_set覆盖_并发撞唯一键_回滚后改写(base_env):
    """P3 修复钉：首次写入撞 (user_id, src_key) 唯一索引时不得 500——回滚后改更新赢家行。"""
    from sqlalchemy.exc import IntegrityError

    from kb.merged import set_overlay

    eid = _run(_seed_pack([_b("baseline:玄幻:tech-a", "官方手法A")]))[0]
    uid = f"mg-{uuid.uuid4().hex[:8]}"

    async def _go():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            await db.commit()

        async with async_session() as db:
            orig_commit = db.commit
            state = {"n": 0}

            async def _commit():
                state["n"] += 1
                if state["n"] == 1:
                    # 竞态窗口：并发赢家用另一连接先提交了同一 (user, src_key)
                    async with async_session() as other:
                        other.add(KbBaselineOverlay(
                            user_id=uid, src_key="baseline:玄幻:tech-a",
                            action="hide", content="", base_content_sha256=""))
                        await other.commit()
                    raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))
                return await orig_commit()

            db.commit = _commit  # type: ignore[method-assign]
            res = await set_overlay(
                db, user_id=uid, entry_id=eid, action="edit", instruction="我的副本内容。")

        async with async_session() as db:
            row = (await db.execute(sel(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == uid))).scalar_one()
            return res, state["n"], row.action, row.content

    res, commits, action, content = _run(_go())
    assert res.get("ok") is True
    assert commits == 2  # 第一次抛冲突→回滚重查→第二次成功
    assert action == "edit" and content == "我的副本内容。"


def test_书未设题材_不跨题材回退(base_env):
    """P2 修复钉：题材缺失时宁可不回退——空 genre 在 digest 里是「不过滤」，
    会把别题材的基线混进本书（跨题材串味）。"""
    from models.chapter import Chapter
    from models.project import Novel
    from models.volume import Volume

    async def _seed():
        uid = f"mg-{uuid.uuid4().hex[:8]}"
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            novel = Novel(
                user_id=uid, name="无题材书", slug=uuid.uuid4().hex[:12],
                root_path=f"./data/{uuid.uuid4().hex[:12]}", source="manual",
                current_phase="write",
            )
            db.add(novel)
            await db.flush()
            vol = Volume(project_id=novel.id, volume_no=1, title="卷")
            db.add(vol)
            await db.flush()
            db.add(Chapter(
                project_id=novel.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
                title="第一章", summary="与老祖正面交锋，硬撼对方底牌",
                primary_mood="燃", plot_stage="高潮爆发",
            ))
            await db.commit()
            return uid, novel.id

    uid, novel_id = _run(_seed())
    _run(_seed_pack([_b("baseline:都市:tech-b", "都市手法", genre="都市")]))

    # 基线就绪但书没设题材 → 不出块（不回退到全题材）
    block, run_id, _items = _run(_prepare(novel_id, "vol-1-ch-1", uid))
    assert block is None and run_id is None

    async def _domain():
        from write.write_block import _binding_domain

        async with async_session() as db:
            return await _binding_domain(db, novel_id)

    assert _run(_domain()) is None
