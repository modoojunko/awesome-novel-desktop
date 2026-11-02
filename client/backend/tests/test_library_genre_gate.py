"""题材继承补课＋跨题材门禁（c-library-genre-gate）。

- normalize_theme 组件兜底：自由词序「灵异志怪」↔ 目录名「志怪/民俗灵异」
- ensure_genre_backfill：拆书/书来源的空题材卡补题材（读面触达、幂等自熄）
- apply_to_book 题材硬门：卡题材与目标书题材不同域拒落卡；任一侧空放行
"""

import asyncio
import json
import uuid

from fastapi.testclient import TestClient

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.deconstruct import DeconstructJob
from models.kb import KbEntry
from models.project import Novel
from models.user import User


def _run(coro):
    return asyncio.run(coro)


async def _seed(with_task: bool = True, with_story_genre: str = "") -> dict:
    uid = f"gateg-{uuid.uuid4().hex[:8]}"
    slug = f"gateg-{uuid.uuid4().hex[:8]}"
    tid = str(uuid.uuid4())
    async with async_session() as db:
        db.add(User(
            id=uid, email=f"{uid}@t.local", password_hash="x", display_name="题材门测试",
            api_key="", api_base_url="", api_model="",
        ))
        novel = Novel(
            user_id=uid, name="题材门测试书", slug=slug, root_path=f"./data/{slug}",
            source="manual", current_phase="write",
        )
        db.add(novel)
        if with_task:
            db.add(DeconstructJob(
                id=tid, user_id=uid, status="completed", queue_seq=1,
                source_name="13路末班车.txt", source_size=1000, book_name="13路末班车",
                total_chars=1000, chapter_count=5, volume_count=1,
                selected_dims_json=json.dumps(["characters", "genre"]),
                dims_json="{}",
                products_json=json.dumps(
                    {"genre": {"file": "题材.md", "data": {"genre": "灵异志怪"}}},
                    ensure_ascii=False,
                ),
            ))
        await db.commit()
    if with_story_genre:
        from filesystem.storage import get_storage

        await get_storage().write_yaml(
            novel.root_path, "story.yaml", {"genre": with_story_genre}
        )
    return {"uid": uid, "novel_id": novel.id, "task_id": tid}


def _entry(user_id: str, **over) -> KbEntry:
    row = {
        "id": str(uuid.uuid4()), "user_id": user_id, "genre": "", "concept": "角色设定",
        "concept_id": ":角色设定", "title": "刘望津", "payload_json": "{}",
        "instruction": "x。", "when_json": "{}", "evidence": "",
    }
    row.update(over)
    return KbEntry(**row)


# ─── ① normalize_theme 组件兜底 ──────────────────────────────


def test_归一组件兜底_自由词序映射目录名():
    from genres.theme_catalog import normalize_theme

    assert normalize_theme("灵异志怪") == "志怪/民俗灵异"  # 词序与目录名互不整含
    assert normalize_theme("仙侠修真") == "仙侠/修真"
    assert normalize_theme("修真") == "仙侠/修真"
    # 既有语义不动：精确/整名包含先命中
    assert normalize_theme("志怪/民俗灵异") == "志怪/民俗灵异"
    assert normalize_theme("都市修仙") == "都市"
    assert normalize_theme("不存在的题材") == ""


# ─── ② ensure_genre_backfill ────────────────────────────────


def test_回填_拆书来源的空题材卡从产物补题材():
    seed = _run(_seed(with_task=True))

    async def _go():
        async with async_session() as db:
            db.add(_entry(seed["uid"], src_kind="deconstruct", src_ref=seed["task_id"], src_key="k1"))
            await db.commit()
            from library.service import ensure_genre_backfill

            await ensure_genre_backfill(db, seed["uid"])
            rows = (await db.execute(
                KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"])
            )).mappings().all()
            return rows[0]

    e = _run(_go())
    assert e["genre"] == "志怪/民俗灵异"
    assert e["concept_id"] == "志怪/民俗灵异:角色设定"


def test_回填_书来源的空题材卡从story补题材():
    seed = _run(_seed(with_task=False, with_story_genre="西式奇幻"))

    async def _go():
        async with async_session() as db:
            db.add(_entry(seed["uid"], src_kind="book", src_ref=seed["novel_id"], src_key="c1"))
            await db.commit()
            from library.service import ensure_genre_backfill

            await ensure_genre_backfill(db, seed["uid"])
            rows = (await db.execute(
                KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"])
            )).mappings().all()
            return rows[0]

    e = _run(_go())
    assert e["genre"] == "西式奇幻"


def test_回填_手动卡与解不出的来源保持空():
    seed = _run(_seed(with_task=False))

    async def _go():
        async with async_session() as db:
            db.add(_entry(seed["uid"], src_kind="manual", src_ref="", src_key="m1"))
            # 来源书已不存在（解不出）→ 保持空
            db.add(_entry(seed["uid"], id=str(uuid.uuid4()), src_kind="book",
                          src_ref="no-such-novel", src_key="c2"))
            await db.commit()
            from library.service import ensure_genre_backfill

            await ensure_genre_backfill(db, seed["uid"])
            rows = (await db.execute(
                KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"])
            )).mappings().all()
            return {r["src_key"]: r["genre"] for r in rows}

    genres = _run(_go())
    assert genres == {"m1": "", "c2": ""}  # 跨题材通用语义不动


def test_回填_读面挂点_角色库列表即触发():
    seed = _run(_seed(with_task=True))

    async def _go():
        async with async_session() as db:
            db.add(_entry(seed["uid"], src_kind="deconstruct", src_ref=seed["task_id"], src_key="k1"))
            await db.commit()
        async with async_session() as db:
            from library.service import list_cards

            return await list_cards(db, user_id=seed["uid"])

    r = _run(_go())
    assert r["count"] == 1
    assert r["items"][0]["genre"] == "志怪/民俗灵异"
    assert r["items"][0]["genre_norm"] == "志怪/民俗灵异"


def test_回填_迁移镜像形状经legacy卡反查来源():
    """升级用户的真实形状：条目 src_kind=character_library_migration，真实来源
    藏在 legacy 卡（src_key＝卡 id）里——快照真数据验证抓到过的坑。"""
    seed = _run(_seed(with_task=True))

    async def _go():
        from models.character_library import CharacterLibrary

        async with async_session() as db:
            card = CharacterLibrary(
                id=str(uuid.uuid4()), user_id=seed["uid"], name="刘望津", role="配角",
                genre="", src_kind="deconstruct", src_ref=seed["task_id"],
                src_novel_name="13路末班车",
            )
            db.add(card)
            await db.flush()
            db.add(_entry(
                seed["uid"], src_kind="character_library_migration",
                src_ref="character_library", src_key=card.id,
            ))
            await db.commit()
            from library.service import ensure_genre_backfill

            await ensure_genre_backfill(db, seed["uid"])
            rows = (await db.execute(
                KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"])
            )).mappings().all()
            return rows[0]

    e = _run(_go())
    assert e["genre"] == "志怪/民俗灵异"
    assert e["concept_id"] == "志怪/民俗灵异:角色设定"


def test_回填_迁移镜像卡自带题材优先_卡删保持空():
    seed = _run(_seed(with_task=False))

    async def _go():
        from models.character_library import CharacterLibrary

        async with async_session() as db:
            own = CharacterLibrary(
                id=str(uuid.uuid4()), user_id=seed["uid"], name="自带题材卡", role="配角",
                genre="玄幻", src_kind="manual", src_ref="",
            )
            db.add(own)
            await db.flush()
            own_id = own.id
            db.add(_entry(
                seed["uid"], src_kind="character_library_migration",
                src_ref="character_library", src_key=own_id,
            ))
            # legacy 卡已不存在（源已删）→ 保持空
            db.add(_entry(
                seed["uid"], id=str(uuid.uuid4()),
                src_kind="character_library_migration",
                src_ref="character_library", src_key="no-such-card",
            ))
            await db.commit()
            from library.service import ensure_genre_backfill

            await ensure_genre_backfill(db, seed["uid"])
            rows = (await db.execute(
                KbEntry.__table__.select().where(KbEntry.user_id == seed["uid"])
            )).mappings().all()
            return own_id, {r["src_key"]: r["genre"] for r in rows}

    own_id, genres = _run(_go())
    assert genres[own_id] == "玄幻"  # 卡自带题材归一后落
    assert genres["no-such-card"] == ""


# ─── ③ apply_to_book 题材硬门 ────────────────────────────────


def _client(seed: dict) -> TestClient:
    async def _override():
        return {"id": seed["uid"]}

    app.dependency_overrides[get_current_user] = _override
    return TestClient(app)


def _make_card(c: TestClient, genre: str) -> dict:
    body = {
        "name": "秦重霄", "aliases": [], "role": "配角", "genre": genre, "kind": "",
        "persona": "黑风寨大当家", "dossier": {"gender": "男", "age": "42"},
        "cog": {},
    }
    return c.post("/api/character-library", json=body).json()["data"]


def test_门禁_跨题材拒落卡():
    seed = _run(_seed(with_task=False, with_story_genre="西式奇幻"))
    c = _client(seed)
    try:
        with c:
            card = _make_card(c, "灵异志怪")
            r = c.post(f"/api/character-library/{card['id']}/apply-to-book",
                       json={"novel_id": seed["novel_id"]})
            assert r.status_code == 400
            assert r.json()["detail"]["code"] == "genre_mismatch"
            assert "西式奇幻" in r.json()["detail"]["message"]
            assert "志怪/民俗灵异" in r.json()["detail"]["message"]
    finally:
        app.dependency_overrides.clear()


def test_门禁_同题材与通用放行():
    seed = _run(_seed(with_task=False, with_story_genre="西式奇幻"))
    c = _client(seed)
    try:
        with c:
            same = _make_card(c, "西式奇幻")
            r = c.post(f"/api/character-library/{same['id']}/apply-to-book",
                       json={"novel_id": seed["novel_id"]})
            assert r.status_code == 200
            assert r.json()["data"]["name"] == "秦重霄"

            generic = _make_card(c, "")  # 跨题材通用卡
            r = c.post(f"/api/character-library/{generic['id']}/apply-to-book",
                       json={"novel_id": seed["novel_id"]})
            assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_门禁_书题材未设时放行():
    seed = _run(_seed(with_task=False))  # 不写 story.yaml → 书题材未设
    c = _client(seed)
    try:
        with c:
            card = _make_card(c, "灵异志怪")
            r = c.post(f"/api/character-library/{card['id']}/apply-to-book",
                       json={"novel_id": seed["novel_id"]})
            assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()
