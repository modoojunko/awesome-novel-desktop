"""书级知识副本测试（c-kb-book-scope 批A/B）：复制范围/幂等/隔离/基线落 KV/选择器切源/指纹。"""

import asyncio
import json
import uuid

from sqlalchemy import select as sel

from db import async_session
from kb.book_scope import book_scope_fingerprint, import_genre_knowledge
from kb.match import select_block
from kb.service import create_entry
from models.chapter import Chapter
from models.kb import KbBookEntry, KbBookEntryTag, KbEntry, KbLibrary, KbPref
from models.project import Novel
from models.user import User
from models.volume import Volume
from write.write_block import extract_signals


def _run(coro):
    return asyncio.run(coro)


async def _seed_master(uid: str, entries: list[dict], genre_lib: str | None = None):
    """作家库母本：条目＋可选题材默认库。调用方先建 User。"""
    async with async_session() as db:
        for e in entries:
            entry, _g, err = await create_entry(
                db, user_id=uid, genre=e.get("genre", ""), concept=e["concept"],
                title=e["title"], payload=e["payload"], instruction=e.get("instruction", ""),
                when_json=e.get("when"),
            )
            assert entry is not None, str(err)
        if genre_lib is not None:
            db.add(KbLibrary(
                user_id=uid, genre=genre_lib, concept="文风", name="文风库",
                rule_kind="auto", enabled=True,
            ))
        await db.commit()


async def _seed_user(uid: str):
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="书域"))
        await db.commit()


async def _seed_book(uid: str) -> str:
    async with async_session() as db:
        novel = Novel(
            user_id=uid, name=f"书{uuid.uuid4().hex[:6]}", slug=uuid.uuid4().hex[:12],
            root_path=f"./data/{uuid.uuid4().hex[:12]}", source="manual", current_phase="write",
        )
        db.add(novel)
        await db.commit()
        return novel.id


async def _import(novel_id: str, uid: str):
    async with async_session() as db:
        return await import_genre_knowledge(
            db, novel_id=novel_id, user_id=uid, genre="玄幻"
        )


async def _copies(novel_id: str) -> list[str]:
    async with async_session() as db:
        rows = (await db.execute(
            sel(KbBookEntry).where(KbBookEntry.novel_id == novel_id)
        )).scalars().all()
        return [r.title for r in rows]


ENTRY_HIT = {"concept": "手法", "genre": "玄幻", "title": "玄幻命中手法",
             "payload": {"instruction": "玄幻交手先让三招。", "scene": "打斗"},
             "instruction": "玄幻交手先让三招。"}
ENTRY_OTHER = {"concept": "手法", "genre": "悬疑", "title": "悬疑手法",
               "payload": {"instruction": "悬疑先抛钩子。", "scene": "对峙"},
               "instruction": "悬疑先抛钩子。"}
ENTRY_COMMON = {"concept": "手法", "genre": "", "title": "通用手法",
                "payload": {"instruction": "对话不要每次说完。", "scene": "日常"},
                "instruction": "对话不要每次说完。"}
ENTRY_BASE = {"concept": "文笔", "genre": "玄幻", "title": "玄幻句式",
              "payload": {"slot": "rule", "rule": "玄幻句子要短。"},
              "instruction": "玄幻句子要短。"}
ENTRY_WORLD = {"concept": "世界设定", "genre": "玄幻", "title": "玄幻舞台",
               "payload": {"part": "stage", "content": "灵气以山脉为脉。"},
               "instruction": "灵气以山脉为脉。"}
ENTRY_FACTION = {"concept": "世界设定", "genre": "玄幻", "title": "玄幻势力",
                 "payload": {"part": "factions", "content": "青云宗为第一大派。"},
                 "instruction": "青云宗为第一大派。"}
ENTRY_QUANT = {"concept": "文笔", "genre": "玄幻", "title": "打斗句长",
               "payload": {"slot": "rule", "rule": "交手时句长不超过12字"},
               "instruction": "交手时句长不超过12字", "when": {"scene": "打斗"}}


def test_复制范围_幂等_隔离():
    uid = f"bs{uuid.uuid4().hex[:8]}"
    _run(_seed_user(uid))
    _run(_seed_master(uid, [ENTRY_HIT, ENTRY_OTHER, ENTRY_COMMON]))
    novel_id = _run(_seed_book(uid))
    r1 = _run(_import(novel_id, uid))
    assert r1["imported"] == 2  # 玄幻命中＋通用；悬疑不进
    assert r1["skipped"] == 0

    r2 = _run(_import(novel_id, uid))
    assert r2["imported"] == 0 and r2["skipped"] == 2  # 幂等

    # 隔离：删源条目，副本不动
    async def _del_src():
        async with async_session() as db:
            src = (await db.execute(
                sel(KbEntry).where(KbEntry.title == "玄幻命中手法")
            )).scalars().first()
            await db.delete(src)
            await db.commit()
    _run(_del_src())
    assert "玄幻命中手法" in _run(_copies(novel_id))


def test_基线落KV_world白名单_来源标记():
    uid = f"bs{uuid.uuid4().hex[:8]}"
    _run(_seed_user(uid))
    _run(_seed_master(uid, [ENTRY_BASE, ENTRY_WORLD, ENTRY_FACTION]))
    novel_id = _run(_seed_book(uid))
    r = _run(_import(novel_id, uid))
    assert r["imported"] >= 2

    async def _kv():
        from filesystem.storage import get_storage
        async with async_session() as db:
            novel = (await db.execute(
                sel(Novel).where(Novel.id == novel_id)
            )).scalar_one()
            style = await get_storage().read_yaml(
                novel.root_path, "settings/writing-style.yaml") or {}
            world = await get_storage().read_yaml(
                novel.root_path, "settings/world-setting.yaml") or {}
            return style, world
    style, world = _run(_kv())
    assert "玄幻句子要短。" in (style.get("rules") or [])
    assert (style.get("style_meta") or {}).get("source") == "kb-genre"
    assert "灵气以山脉为脉。" in (world.get("stage") or "")
    assert "青云宗" not in json.dumps(world, ensure_ascii=False)  # F-2 白名单


def test_写法块选择器切书副本_账号新增不混入():
    uid = f"bs{uuid.uuid4().hex[:8]}"
    _run(_seed_user(uid))
    _run(_seed_master(uid, [ENTRY_HIT, ENTRY_COMMON]))
    novel_id = _run(_seed_book(uid))
    _run(_import(novel_id, uid))
    # 开书后作家库新增一条——不得混入本书
    _run(_seed_master(uid, [{"concept": "手法", "genre": "玄幻", "title": "开书后新增",
                             "payload": {"instruction": "新招：以攻代守。", "scene": "打斗"},
                             "instruction": "新招：以攻代守。"}]))

    async def _mk_chapter():
        async with async_session() as db:
            vol = Volume(project_id=novel_id, volume_no=1, title="卷")
            db.add(vol)
            await db.flush()
            db.add(Chapter(
                project_id=novel_id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
                title="第一章", summary="与老祖正面交锋", primary_mood="燃",
                plot_stage="高潮爆发",
            ))
            await db.commit()
    _run(_mk_chapter())

    async def _select():
        async with async_session() as db:
            signals = await extract_signals(
                db, novel_id=novel_id, chapter_ref="vol-1-ch-1", genre="玄幻")
            return await select_block(
                db, user_id=uid, signals=signals, genre="玄幻", book_scope=novel_id)
    selr = _run(_select())
    async def _dbg():
        async with async_session() as db:
            copies = (await db.execute(sel(KbBookEntry).where(KbBookEntry.novel_id == novel_id))).scalars().all()
            tags = (await db.execute(sel(KbBookEntryTag).where(KbBookEntryTag.novel_id == novel_id))).scalars().all()
            chs = (await db.execute(sel(Chapter).where(Chapter.project_id == novel_id))).scalars().all()
            return ([(c.title, c.status) for c in copies],
                    [(t.entry_id[:6], t.dim, t.value) for t in tags],
                    [(c.ref, c.summary) for c in chs])
    copies, tags, chs = _run(_dbg())
    print("COPIES:", copies)
    print("TAGS:", tags)
    print("CHAPTERS:", chs)
    assert selr is not None, f"selr None; copies={copies}; tags={tags}; chs={chs}"
    titles = [i.entry.title for i in selr.items]
    assert "开书后新增" not in titles  # 账号库新增不混入本书（书域隔离）
    assert any("交手先让三招" in i.entry.instruction for i in selr.items)


def test_指纹随副本变化_pref标记不刷():
    uid = f"fp{uuid.uuid4().hex[:8]}"
    _run(_seed_user(uid))
    _run(_seed_master(uid, [ENTRY_HIT, ENTRY_COMMON]))
    novel_id = _run(_seed_book(uid))

    async def _fp():
        async with async_session() as db:
            return await book_scope_fingerprint(db, novel_id=novel_id)
    fp1 = _run(_fp())  # 空副本
    _run(_import(novel_id, uid))
    fp2 = _run(_fp())
    assert fp1 != fp2  # 导入改变指纹（触发重选）

    # pref 标记（kb_prefs 不触副本 updated_at）→ 指纹不变
    async def _mark():
        async with async_session() as db:
            row = (await db.execute(
                sel(KbBookEntry).where(KbBookEntry.novel_id == novel_id)
            )).scalars().first()
            db.add(KbPref(user_id=uid, entry_id=row.id, weight=0.5,
                          adopt_count=0, drop_count=2))
            await db.commit()
    _run(_mark())
    assert _run(_fp()) == fp2  # pref 不刷新指纹（重试字节一致守卫）


def test_量化合成保守基线():
    """书级量化未蒸馏：导入时按维度合成 conf=40 基线（F-3）；作者蒸馏后覆盖。"""
    from filesystem.paths import STYLE_QUANT_PATH
    from filesystem.storage import get_storage
    from settings.style_quant_model import quant_doc

    uid = f"qs{uuid.uuid4().hex[:8]}"
    _run(_seed_user(uid))
    _run(_seed_master(uid, [ENTRY_QUANT, ENTRY_HIT, ENTRY_COMMON]))
    novel_id = _run(_seed_book(uid))
    r = _run(_import(novel_id, uid))
    assert r["imported"] >= 1

    async def _read():
        async with async_session() as db:
            novel = (await db.execute(sel(Novel).where(Novel.id == novel_id))).scalar_one()
            doc = quant_doc(await get_storage().read_yaml(novel.root_path, STYLE_QUANT_PATH))
            return doc
    doc = _run(_read())
    assert doc["confidence"] == 40
    assert doc.get("source") == "kb-synthesized"
    # 下限型（不少于）不进约框架——句长条目是上限型，进 syntax 维
    assert doc["baseline"]["syntax"]["value"].endswith("字")

    # 作者蒸馏覆盖合成值
    async def _distill():
        from filesystem.storage import get_storage
        async with async_session() as db:
            novel = (await db.execute(sel(Novel).where(Novel.id == novel_id))).scalar_one()
            await get_storage().write_yaml(
                novel.root_path, STYLE_QUANT_PATH,
                {"confidence": 85, "baseline": {"syntax": {"value": "约20字", "tolerance": 10}}},
            )
    _run(_distill())
    _run(_import(novel_id, uid))  # 重复导入不覆盖作者蒸馏
    doc2 = _run(_read())
    assert doc2["confidence"] == 85  # 蒸馏资产保留


def test_单书备份往返_书级段():
    """C3：_dump_kb_book 带书级知识段；_import_kb_book 重建（按 id 去重）。"""
    import io
    import zipfile

    uid = f"bk{uuid.uuid4().hex[:8]}"
    _run(_seed_user(uid))
    _run(_seed_master(uid, [ENTRY_HIT, ENTRY_COMMON, ENTRY_QUANT]))
    novel_id = _run(_seed_book(uid))
    _run(_import(novel_id, uid))

    async def _roundtrip():
        import yaml as _yaml
        from sqlalchemy import delete as _del

        from backup.export import _dump_kb_book
        from backup.importer import _import_kb_book
        from models.project import Novel as _Novel

        async with async_session() as db:
            project = await db.get(_Novel, novel_id)
            copy_ids = list(
                (
                    await db.execute(
                        sel(KbBookEntry.id).where(KbBookEntry.novel_id == novel_id)
                    )
                ).scalars()
            )
            # 副本反馈权重（书级心智）：随副本 id 落 KbPref
            db.add(KbPref(user_id=uid, entry_id=copy_ids[0], weight=0.3,
                          adopt_count=1, drop_count=2))
            await db.commit()
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                await _dump_kb_book(zf, db, project)
                doc = _yaml.safe_load(zf.read("kb/kb-book.yaml"))
                n_before = len(doc.get("book_entries") or [])
                n_tags_before = len(doc.get("book_entry_tags") or [])
                n_prefs_before = len(doc.get("book_prefs") or [])
                # 模拟换机恢复：清空本书副本/标签/权重后重建（标签是选择器候选域，
                # 只恢复条目不恢复标签＝写法块静默为空；权重丢了有用率归零）
                await db.execute(_del(KbBookEntry).where(KbBookEntry.novel_id == novel_id))
                await db.execute(
                    _del(KbBookEntryTag).where(KbBookEntryTag.novel_id == novel_id)
                )
                await db.execute(_del(KbPref).where(KbPref.entry_id.in_(copy_ids)))
                await db.commit()
                await _import_kb_book(db, zf, set(zf.namelist()), "", project, uid, [])
                await db.commit()
                rows = (await db.execute(
                    sel(KbBookEntry).where(KbBookEntry.novel_id == novel_id)
                )).scalars().all()
                tags = (await db.execute(
                    sel(KbBookEntryTag).where(KbBookEntryTag.novel_id == novel_id)
                )).scalars().all()
                prefs = (await db.execute(
                    sel(KbPref).where(KbPref.entry_id.in_(copy_ids))
                )).scalars().all()
            return (
                n_before, len(rows), n_tags_before, len(tags),
                n_prefs_before, len(prefs), [r.title for r in rows],
            )
    (
        n_before, n_after, n_tags_before, n_tags_after,
        n_prefs_before, n_prefs_after, titles,
    ) = _run(_roundtrip())
    assert n_before >= 3  # 命中＋通用＋量化
    assert n_after == n_before  # 段重建完整
    assert n_tags_before > 0 and n_tags_after == n_tags_before  # 标签索引随包往返
    assert n_prefs_before == 1 and n_prefs_after == 1  # 反馈权重随包往返
    assert "玄幻命中手法" in titles



async def _set_genre(novel_id: str, genre: str):
    """本书题材＝story KV 的 genre 键（Novel 无 genre 列；D19 关系化后目录仍在 KV）。"""
    from filesystem.storage import get_storage

    async with async_session() as db:
        novel = (await db.execute(sel(Novel).where(Novel.id == novel_id))).scalar_one()
    await get_storage().write_yaml(novel.root_path, "story.yaml", {"genre": genre})


def test_导入进度流_SSE与decline标记():
    """弹窗二选一后端契约：SSE 逐概念组进度＋done 汇总；decline 落标记；
    diff 返 declined；题材取自 story KV（不是 novel.genre）。"""
    from fastapi.testclient import TestClient

    from auth_local.middleware import get_current_user
    from main import app

    uid = f"st{uuid.uuid4().hex[:8]}"
    _run(_seed_user(uid))
    _run(_seed_master(uid, [ENTRY_HIT, ENTRY_OTHER, ENTRY_COMMON]))
    novel_id = _run(_seed_book(uid))
    _run(_set_genre(novel_id, "玄幻"))

    async def _override():
        return {"id": uid}

    app.dependency_overrides[get_current_user] = _override
    try:
        with TestClient(app) as c:
            r = c.post("/api/kb/book-scope/import/stream", json={"novel_id": novel_id})
            assert r.status_code == 200, r.text
            assert "text/event-stream" in r.headers.get("content-type", "")
            events = [
                json.loads(line[len("data: "):])
                for line in r.text.splitlines()
                if line.startswith("data: ")
            ]
            assert events[0] == {"type": "phase", "phase": "copy", "total": 2}
            phases = [e for e in events if e["type"] == "phase" and e.get("concept")]
            assert phases, events
            assert phases[-1]["done"] == 2 and phases[-1]["total"] == 2
            assert any(e["type"] == "phase" and e["phase"] == "baseline" for e in events)
            done = next(e for e in events if e["type"] == "done")
            assert done["imported"] == 2 and done["skipped"] == 0
            assert not [e for e in events if e["type"] == "error"], events

            d = c.get(f"/api/kb/book-scope/diff?novel_id={novel_id}").json()["data"]
            assert d == {"new_count": 0, "declined": False}

            r2 = c.post("/api/kb/book-scope/decline", json={"novel_id": novel_id})
            assert r2.status_code == 200 and r2.json()["data"]["declined"] is True
            d2 = c.get(f"/api/kb/book-scope/diff?novel_id={novel_id}").json()["data"]
            assert d2["declined"] is True

            r3 = c.post(
                "/api/kb/book-scope/decline",
                json={"novel_id": novel_id, "declined": False},
            )
            assert r3.json()["data"]["declined"] is False
    finally:
        app.dependency_overrides.clear()


def test_改题材复位decline():
    """改题材＝新题材重新征询：settings genre PUT 清 declined 标记。"""
    from fastapi.testclient import TestClient

    from auth_local.middleware import get_current_user
    from kb.book_scope import read_import_declined, write_import_declined
    from main import app

    uid = f"gr{uuid.uuid4().hex[:8]}"
    _run(_seed_user(uid))
    novel_id = _run(_seed_book(uid))

    async def _root():
        async with async_session() as db:
            novel = (await db.execute(sel(Novel).where(Novel.id == novel_id))).scalar_one()
            return novel.root_path
    root = _run(_root())
    _run(write_import_declined(root, True))
    assert _run(read_import_declined(root)) is True

    async def _override():
        return {"id": uid}

    app.dependency_overrides[get_current_user] = _override

    def _put(body: dict):
        try:
            with TestClient(app) as c:
                r = c.put(f"/api/novels/{novel_id}/settings/genre", json=body)
                assert r.status_code == 200, r.text
        finally:
            app.dependency_overrides.clear()

    _put({"theme": "玄幻"})
    assert _run(read_import_declined(root)) is False  # 空→玄幻＝真改题材，复位

    # 同题材保存（只改 02 主要看什么）不清 declined：作家选的「我自己设定」保留
    _run(write_import_declined(root, True))
    app.dependency_overrides[get_current_user] = _override
    _put({"theme": "玄幻", "core_promise": "逆袭打脸"})
    assert _run(read_import_declined(root)) is True

    # 真改题材才重新征询
    app.dependency_overrides[get_current_user] = _override
    _put({"theme": "都市"})
    assert _run(read_import_declined(root)) is False


def test_并发双开导入_唯一索引冲突自动重算(monkeypatch):
    """两个标签页同时导入：对方抢先落库后，本请求回滚重算差集再来一次，
    不把 UNIQUE 冲突当错误丢给用户（对方已落库的条目按 skipped 计）。"""
    from kb import book_scope as bs

    uid = f"cc{uuid.uuid4().hex[:8]}"
    _run(_seed_user(uid))
    _run(_seed_master(uid, [ENTRY_HIT, ENTRY_COMMON]))
    novel_id = _run(_seed_book(uid))

    async def _winner():
        from models.kb import KbBookEntry

        async with async_session() as db:
            src = (await db.execute(
                sel(KbEntry).where(
                    KbEntry.user_id == uid, KbEntry.title == "玄幻命中手法"
                )
            )).scalars().one()
            db.add(KbBookEntry(
                novel_id=novel_id, user_id=uid, genre=src.genre,
                concept=src.concept, title=src.title,
                payload_json=src.payload_json, instruction=src.instruction,
                src_kind="book_copy", src_ref=novel_id, src_key=src.id,
            ))
            await db.commit()
    _run(_winner())  # 模拟对方已抢到一条

    real = bs._load_import_state
    calls = {"n": 0}

    async def _stale_then_real(db, *, novel_id, user_id, genre):
        calls["n"] += 1
        rows, todo = await real(db, novel_id=novel_id, user_id=user_id, genre=genre)
        return (rows, rows) if calls["n"] == 1 else (rows, todo)  # 首轮装作没看见

    monkeypatch.setattr(bs, "_load_import_state", _stale_then_real)

    async def _go():
        async with async_session() as db:
            return [
                ev async for ev in bs.stream_import_genre_knowledge(
                    db, novel_id=novel_id, user_id=uid, genre="玄幻"
                )
            ]
    events = _run(_go())
    assert not [e for e in events if e["type"] == "error"]
    done = next(e for e in events if e["type"] == "done")
    assert done["imported"] == 1 and done["skipped"] == 1
    assert sorted(_run(_copies(novel_id))) == sorted(["玄幻命中手法", "通用手法"])
