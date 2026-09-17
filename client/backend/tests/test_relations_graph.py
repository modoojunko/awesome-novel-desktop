"""relations-graph（角色关系页签）服务层：节点/边/来源章。

模式沿既有 API 测试：async_session 直种，asyncio.run 包服务调用。
"""
import asyncio
import uuid

from settings.character_service import relations_graph


def _seed_user() -> str:
    from db import async_session
    from models.user import User

    async def _go():
        async with async_session() as session:
            uid = f"rg-{uuid.uuid4().hex[:8]}"
            session.add(User(
                id=uid, email=f"{uid}@test.local", password_hash="x",
                display_name="图测试", api_key="", api_base_url="", api_model="",
            ))
            await session.commit()
            return uid

    return asyncio.run(_go())


def _seed_book(user_id: str) -> str:
    from db import async_session
    from models.project import Novel

    async def _go():
        async with async_session() as session:
            n = Novel(
                user_id=user_id,
                name=f"图{uuid.uuid4().hex[:6]}",
                slug=f"rg-{uuid.uuid4().hex[:8]}",
                root_path=f"./data/rg-{uuid.uuid4().hex[:8]}",
                source="manual",
            )
            session.add(n)
            await session.commit()
            await session.refresh(n)
            return n.id

    return asyncio.run(_go())


def _seed_character(novel_id: str, name: str, role: str = "配角"):
    from db import async_session
    from models.character import Character

    async def _go():
        async with async_session() as session:
            c = Character(
                novel_id=novel_id,
                seq=int(uuid.uuid4().hex[:4], 16) % 900 + 100,
                name=name,
                role=role,
            )
            session.add(c)
            await session.commit()
            await session.refresh(c)
            return c

    return asyncio.run(_go())


def _seed_relation(novel_id: str, owner_id: str, other_id: str, rel_type="盟友"):
    from db import async_session
    from models.character import CharacterRelation

    async def _go():
        async with async_session() as session:
            r = CharacterRelation(
                novel_id=novel_id, owner_id=owner_id, other_id=other_id,
                rel_type=rel_type,
            )
            session.add(r)
            await session.commit()
            return r

    return asyncio.run(_go())


def _graph(novel_id: str) -> dict:
    from db import async_session
    from settings.character_service import relations_graph

    async def _go():
        async with async_session() as session:
            return await relations_graph(session, novel_id)

    return asyncio.run(_go())


def test_nodes_and_edges():
    uid = _seed_user()
    nid = _seed_book(uid)
    jia = _seed_character(nid, "甲", "主角")
    yi = _seed_character(nid, "乙")
    _seed_relation(nid, jia.id, yi.id)

    data = _graph(nid)
    names = {node["name"] for node in data["nodes"]}
    assert names == {"甲", "乙"}
    assert len(data["edges"]) == 1
    edge = data["edges"][0]
    assert edge["owner_name"] == "甲"
    assert edge["other_name"] == "乙"
    assert edge["rel_type"] == "盟友"


def test_isolated_character_is_node_without_edges():
    uid = _seed_user()
    nid = _seed_book(uid)
    _seed_character(nid, "独行侠")
    data = _graph(nid)
    assert len(data["nodes"]) == 1
    assert data["edges"] == []


def test_empty_book_gives_empty_graph():
    uid = _seed_user()
    nid = _seed_book(uid)
    data = _graph(nid)
    assert data["nodes"] == []
    assert data["edges"] == []
