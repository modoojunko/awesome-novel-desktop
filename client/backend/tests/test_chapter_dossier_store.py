"""章档四域存取合同（c-chapter-dossier）：组装恒出四键、presence-gate 缺键保持、
显式替换、按名重绑 character_id、save/load 往返。

用法：
    cd client/backend
    python -m pytest tests/test_chapter_dossier_store.py -v
"""

import asyncio
import os
import tempfile

_tmp_db = tempfile.NamedTemporaryFile(suffix="_dossier_store.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_dossier_store_")


from conftest import seed_chapter_db  # noqa: E402
from sqlalchemy import select  # noqa: E402

from db import Base, async_session, engine  # noqa: E402

_SEED = {
    "volume": 1,
    "chapter": 1,
    "title": "第一章",
    "outline": {"summary": "主角来到边境城邦。", "characters": ["林野", "阿蓟"]},
    "prose": "煤气灯在雾里发脏黄的光。他攥紧了旧刀。",
}

_DOSSIER = {
    "settings": [
        {"area": "势力", "content": "守夜人接管了城门", "evidence": "守夜人接管了城门",
         "status": "accepted"},
    ],
    "relations": [
        {"owner": "林野", "other": "阿蓟", "rel_type": "盟友",
         "change_note": "从戒备转为并肩", "evidence": "两人背靠背站着", "status": "accepted"},
    ],
    "items": [
        {"name": "旧刀", "change_type": "obtain", "holder": "林野",
         "detail": "旧刀认主", "evidence": "他攥紧了旧刀", "status": "pending"},
    ],
    "knowledge": [
        {"character": "阿蓟", "fact": "林野的真实身份", "learned": False,
         "evidence": "她并不知道他是谁", "status": "pending", "flags": "unregistered"},
    ],
}


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _seed(root: str, with_dossier: bool = True) -> None:
    data = dict(_SEED)
    if with_dossier:
        data["dossier"] = _DOSSIER
    _run(seed_chapter_db(root, data))


async def _load(root: str) -> dict:
    from chapters.store import load_chapter

    return await load_chapter(root, "vol-1-ch-1")


def _save(root: str, data: dict) -> None:
    from chapters.store import save_chapter

    _run(save_chapter(root, "vol-1-ch-1", data))


def test_assemble_always_emits_four_domain_keys():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="dossier_assemble_")
    _seed(root, with_dossier=False)
    d = _run(_load(root))
    assert set(d["dossier"].keys()) == {"settings", "relations", "items", "knowledge"}
    assert all(d["dossier"][k] == [] for k in d["dossier"])


def test_dossier_roundtrip_and_shape():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="dossier_rt_")
    _seed(root)
    d = _run(_load(root))["dossier"]
    assert d["settings"][0]["area"] == "势力"
    assert d["settings"][0]["status"] == "accepted"
    assert d["relations"][0]["owner"] == "林野"
    assert d["items"][0]["name"] == "旧刀"
    assert d["knowledge"][0]["learned"] is False
    assert d["knowledge"][0]["flags"] == "unregistered"
    # 整包回存（模拟全量 PUT/导入）：逐域还原
    _save(root, {"dossier": d})
    again = _run(_load(root))["dossier"]
    assert again == d


def test_missing_dossier_key_keeps_rows():
    """部分键 PUT（无 dossier 键）不得清章档——patch-gates 同合同。"""
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="dossier_gate_")
    _seed(root)
    before = _run(_load(root))["dossier"]
    _save(root, {"challenge": "只改挑战"})
    assert _run(_load(root))["dossier"] == before


def test_dossier_none_keeps_rows_and_explicit_clear_works():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="dossier_clear_")
    _seed(root)
    _save(root, {"dossier": None})  # None ＝ 缺键
    assert _run(_load(root))["dossier"]["settings"] != []
    _save(root, {"dossier": {}})  # 显式空 dict ＝ 四域整体清空
    d = _run(_load(root))["dossier"]
    assert all(d[k] == [] for k in d)


def test_relation_and_knowledge_bind_character_ids_by_name():
    """保存时按名解析 character_id（角色卡存在则绑、不存在落空快照）。"""
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="dossier_bind_")
    _seed(root)

    from sqlalchemy import select

    from models.chapter import Chapter, ChapterRelationChange
    from models.character import Character
    from models.project import Novel

    async def _check():
        async with async_session() as session:
            ch = (await session.scalars(
                select(Chapter)
                .join(Novel, Novel.id == Chapter.project_id)
                .where(Novel.root_path == root)
            )).one()
            card = (await session.scalars(
                select(ChapterRelationChange)
                .where(ChapterRelationChange.chapter_id == ch.id)
            )).one()
            # 建卡前：按名快照、id 空
            assert card.owner_name == "林野" and card.owner_character_id is None
            # 建「林野」卡后重存 dossier：重绑成功
            session.add(Character(novel_id=ch.project_id, seq=1, name="林野", role="主角"))
            await session.flush()
            names = [c.name for c in (await session.scalars(
                select(Character).where(Character.novel_id == ch.project_id))).all()]
            assert "林野" in names
            await session.commit()

    _run(_check())
    _save(root, {"dossier": _DOSSIER})

    async def _verify():
        async with async_session() as session:
            ch = (await session.scalars(
                select(Chapter)
                .join(Novel, Novel.id == Chapter.project_id)
                .where(Novel.root_path == root)
            )).one()
            card = (await session.scalars(
                select(ChapterRelationChange)
                .where(ChapterRelationChange.chapter_id == ch.id)
            )).one()
            assert card.owner_character_id is not None
            know = (await session.scalars(
                select(Chapter)
                .where(Chapter.id == ch.id)
            )).one()
            assert know.dossier_knowledge[0].character_name == "阿蓟"

    _run(_verify())


def test_status_whitelist_and_field_clamps():
    """非法 status 落 pending；超宽字段截断到列宽（生成物截断安全）。"""
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="dossier_clamp_")
    _seed(root)
    d = _run(_load(root))["dossier"]
    d["settings"][0]["status"] = "hacked"
    d["settings"][0]["content"] = "长" * 500
    _save(root, {"dossier": d})
    got = _run(_load(root))["dossier"]
    assert got["settings"][0]["status"] == "pending"
    assert len(got["settings"][0]["content"]) == 300


def test_save_prose_keeps_dossier_row_ids_stable():
    """评审 P2：编辑器自动保存（save_prose 高频路径）不得重建章档行——
    否则行 uuid 每次保存都换，采纳会随机撞「已重新提取」误导性 409。"""
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="dossier_prose_")
    _seed(root, with_dossier=True)

    from chapters.service import save_prose
    from models.chapter import Chapter, ChapterSettingChange
    from models.project import Novel

    async def _ids():
        async with async_session() as s:
            ch = (await s.scalars(select(Chapter).join(
                Novel, Novel.id == Chapter.project_id
            ).where(Novel.root_path == root))).one()
            return [r.id for r in (await s.scalars(
                select(ChapterSettingChange)
                .where(ChapterSettingChange.chapter_id == ch.id)
                .order_by(ChapterSettingChange.sort_order)
            )).all()]

    async def _save(text: str):
        async with async_session() as s:
            proj = (await s.scalars(
                select(Novel).where(Novel.root_path == root)
            )).one()
            await save_prose(s, proj, "vol-1-ch-1", text)

    before = _run(_ids())
    assert len(before) == 1
    _run(_save("新增的一段正文，自动保存触发。"))
    _run(_save("又一段正文，第二次自动保存。"))
    assert _run(_ids()) == before
