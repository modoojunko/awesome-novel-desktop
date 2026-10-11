"""relations-graph（角色关系页签）服务层：节点/边/来源章。

模式沿既有 API 测试：async_session 直种，asyncio.run 包服务调用。
"""
import asyncio
import uuid


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


def _graph(novel_id: str, *, up_to_ref: str | None = None, volume_no: int | None = None) -> dict:
    from db import async_session
    from settings.character_service import relations_graph

    async def _go():
        async with async_session() as session:
            return await relations_graph(
                session, novel_id, up_to_ref=up_to_ref, volume_no=volume_no
            )

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


# ── 口径（c-rel-graph-cast-filter，随章走）─────────────────────────────


def _seed_volume(novel_id: str, volume_no: int):
    from db import async_session
    from models.volume import Volume

    async def _go():
        async with async_session() as session:
            v = Volume(project_id=novel_id, volume_no=volume_no, title=f"第{volume_no}卷")
            session.add(v)
            await session.commit()
            await session.refresh(v)
            return v

    return asyncio.run(_go())


def _seed_chapter(novel_id: str, volume_id: str, chapter_no: int, ref: str, *, ghost_of: str | None = None):
    from db import async_session
    from models.chapter import Chapter

    async def _go():
        async with async_session() as session:
            c = Chapter(
                project_id=novel_id, volume_id=volume_id, chapter_no=chapter_no,
                ref=ref, title=ref, status="outline", ghost_of=ghost_of,
            )
            session.add(c)
            await session.commit()
            await session.refresh(c)
            return c

    return asyncio.run(_go())


def _seed_cast(chapter_id: str, name: str, character_id: str | None = None, sort_order: int = 0):
    from db import async_session
    from models.chapter import ChapterCharacter

    async def _go():
        async with async_session() as session:
            cc = ChapterCharacter(
                chapter_id=chapter_id, sort_order=sort_order,
                character_id=character_id, character_name=name,
            )
            session.add(cc)
            await session.commit()
            return cc

    return asyncio.run(_go())


def _seed_relation_ch(novel_id: str, owner_id: str, other_id: str, rel_type="盟友", ch_ref: str = ""):
    from db import async_session
    from models.character import CharacterRelation

    async def _go():
        async with async_session() as session:
            r = CharacterRelation(
                novel_id=novel_id, owner_id=owner_id, other_id=other_id,
                rel_type=rel_type, ch_ref=ch_ref,
            )
            session.add(r)
            await session.commit()
            return r

    return asyncio.run(_go())


def test_scoped_filters_nodes_by_cumulative_cast():
    """章态：登记集＝截至该章（含）累计；未登记卡不上图；cast_names 随响应。"""
    uid = _seed_user()
    nid = _seed_book(uid)
    jia = _seed_character(nid, "甲")
    yi = _seed_character(nid, "乙")
    bing = _seed_character(nid, "丙")  # 从未进章纲
    v1 = _seed_volume(nid, 1)
    ch1 = _seed_chapter(nid, v1.id, 1, "vol-1-ch-1")
    ch2 = _seed_chapter(nid, v1.id, 2, "vol-1-ch-2")
    _seed_cast(ch1.id, "甲", jia.id)
    _seed_cast(ch2.id, "乙", yi.id)

    # 截至第 1 章：只有甲
    data = _graph(nid, up_to_ref="vol-1-ch-1")
    assert {n["name"] for n in data["nodes"]} == {"甲"}
    assert set(data["cast_names"]) == {"甲"}
    # 截至第 2 章：甲（前章登记、本章未出场）＋乙；丙永不上图
    data = _graph(nid, up_to_ref="vol-1-ch-2")
    assert {n["name"] for n in data["nodes"]} == {"甲", "乙"}
    assert set(data["cast_names"]) == {"甲", "乙"}
    assert bing.id not in {n["id"] for n in data["nodes"]}


def test_scoped_edge_requires_both_endpoints_registered():
    uid = _seed_user()
    nid = _seed_book(uid)
    jia = _seed_character(nid, "甲")
    yi = _seed_character(nid, "乙")
    bing = _seed_character(nid, "丙")
    v1 = _seed_volume(nid, 1)
    ch1 = _seed_chapter(nid, v1.id, 1, "vol-1-ch-1")
    _seed_cast(ch1.id, "甲", jia.id)
    _seed_cast(ch1.id, "乙", yi.id, sort_order=1)
    _seed_relation_ch(nid, jia.id, yi.id, "师徒")
    _seed_relation_ch(nid, yi.id, bing.id, "敌对")  # 乙→丙：一端未登记

    data = _graph(nid, up_to_ref="vol-1-ch-1")
    assert [(e["owner_name"], e["other_name"]) for e in data["edges"]] == [("甲", "乙")]


def test_scoped_origin_chapter_narrowing():
    """设定边随章收窄：来源章在口径点之后不上图；空 origin＝开书设定恒在。"""
    uid = _seed_user()
    nid = _seed_book(uid)
    jia = _seed_character(nid, "甲")
    yi = _seed_character(nid, "乙")
    bing = _seed_character(nid, "丙")
    v1 = _seed_volume(nid, 1)
    v2 = _seed_volume(nid, 2)
    ch1 = _seed_chapter(nid, v1.id, 1, "vol-1-ch-1")
    ch2 = _seed_chapter(nid, v1.id, 2, "vol-1-ch-2")
    _seed_chapter(nid, v2.id, 1, "vol-2-ch-1")
    for i, (nm, cid) in enumerate((("甲", jia.id), ("乙", yi.id), ("丙", bing.id))):
        _seed_cast(ch1.id, nm, cid, sort_order=i)
    _seed_cast(ch2.id, "甲", jia.id)
    _seed_relation_ch(nid, jia.id, yi.id, "师徒", ch_ref="vol-1-ch-1")   # 口径点前 → 在
    _seed_relation_ch(nid, yi.id, bing.id, "结拜", ch_ref="vol-2-ch-1")  # 口径点后 → 不在
    _seed_relation_ch(nid, jia.id, bing.id, "同盟")                      # 开书设定 → 恒在

    data = _graph(nid, up_to_ref="vol-1-ch-2")
    got = [(e["owner_name"], e["other_name"]) for e in data["edges"]]
    assert ("甲", "乙") in got and ("甲", "丙") in got
    assert ("乙", "丙") not in got
    # 卷态同规则：截至第 1 卷末，第 2 卷来源的边不进投影
    data = _graph(nid, volume_no=1)
    got = [(e["owner_name"], e["other_name"]) for e in data["edges"]]
    assert ("乙", "丙") not in got and ("甲", "乙") in got


def test_scoped_cast_registered_cardless_name_survives():
    """登记过但卡已删（character_id NULL）→ 名进 cast_names，供前端虚线占位。"""
    uid = _seed_user()
    nid = _seed_book(uid)
    jia = _seed_character(nid, "甲")
    v1 = _seed_volume(nid, 1)
    ch1 = _seed_chapter(nid, v1.id, 1, "vol-1-ch-1")
    _seed_cast(ch1.id, "甲", jia.id)
    _seed_cast(ch1.id, "阿鬼", None, sort_order=1)  # 未建卡

    data = _graph(nid, up_to_ref="vol-1-ch-1")
    assert set(data["cast_names"]) == {"阿鬼", "甲"}
    assert {n["name"] for n in data["nodes"]} == {"甲"}


def test_scoped_cast_resolves_renamed_card():
    """登记名是快照、卡已改名：按 character_id 命中，cast_names 给现名。"""
    uid = _seed_user()
    nid = _seed_book(uid)
    yi = _seed_character(nid, "乙新名")
    v1 = _seed_volume(nid, 1)
    ch1 = _seed_chapter(nid, v1.id, 1, "vol-1-ch-1")
    _seed_cast(ch1.id, "乙旧名", yi.id)

    data = _graph(nid, up_to_ref="vol-1-ch-1")
    assert [n["name"] for n in data["nodes"]] == ["乙新名"]
    assert data["cast_names"] == ["乙新名"]


def test_scoped_ignores_ghost_branch_chapters():
    """支线（ghost_of 非空）章的登记不进主线登记集。"""
    uid = _seed_user()
    nid = _seed_book(uid)
    jia = _seed_character(nid, "甲")
    gui = _seed_character(nid, "阿鬼")
    v1 = _seed_volume(nid, 1)
    ch1 = _seed_chapter(nid, v1.id, 1, "vol-1-ch-1")
    ghost = _seed_chapter(nid, v1.id, 2, "vol-1-ch-2", ghost_of="vol-1-ch-1")
    _seed_cast(ch1.id, "甲", jia.id)
    _seed_cast(ghost.id, "阿鬼", gui.id)

    data = _graph(nid, up_to_ref="vol-1-ch-2")
    assert {n["name"] for n in data["nodes"]} == {"甲"}
    assert data["cast_names"] == ["甲"]


def test_unknown_up_to_ref_falls_back_to_whole_book():
    uid = _seed_user()
    nid = _seed_book(uid)
    _seed_character(nid, "甲")
    data = _graph(nid, up_to_ref="vol-9-ch-9")
    assert {n["name"] for n in data["nodes"]} == {"甲"}
    assert "cast_names" not in data  # 回落全书口径：无登记集键


def test_unscoped_response_shape_unchanged():
    """缺省＝全书视图：不附带 cast_names 键（存量消费方兼容）。"""
    uid = _seed_user()
    nid = _seed_book(uid)
    data = _graph(nid)
    assert set(data.keys()) == {"nodes", "edges"}
