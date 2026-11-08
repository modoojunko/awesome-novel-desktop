"""知识树装配测试（boss 2026-11-08 截图定罪后的重写钉）：

- 单根：唯一根＝「写作知识」根行（旧概念根装配把多个无标题概念根平铺＝游离箭头）；
- 孤儿剔除：parent_id 空且非根行的知识行（老角色库迁移行如「马望津」）不进树；
- 发版序：同级按 taxonomy 文件序（笔法→世界→角色→其他），未收录标题排尾；
- 剥前缀：树面 definition 不带「题材·标题——」懒物化前缀。
"""

import asyncio
import uuid

from db import async_session
from kb.router import graph_tree_api
from models.kb import KbEntry
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _mk(tag: str) -> str:
    return f"kbtree-{tag}-{uuid.uuid4().hex[:8]}"


async def _seed_user(uid: str):
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="树装配钉"))
        await db.commit()


async def _seed_row(uid: str, genre: str, title: str, *, parent_id: str = "", concept: str = "",
                    definition: str = "", origin: str = "summary") -> str:
    rid = uuid.uuid4().hex
    async with async_session() as db:
        db.add(KbEntry(
            id=rid, user_id=uid, genre=genre, concept=concept, concept_id=f"{genre}:{concept}",
            title=title, payload_json="{}", instruction="",
            definition=definition or (f"{genre}·{title}——纯定义。" if title != "写作知识" else "这本书学到的写法与设定知识——全树根。"),
            origin=origin, status="active", version=1, parent_id=parent_id,
        ))
        await db.commit()
    return rid


class TestTreeAssembly:
    def test_单根_孤儿剔除_发版序_剥前缀(self):
        uid = _mk("main")
        _run(_seed_user(uid))
        g = "志怪/民俗灵异"

        async def _seed():
            root = await _seed_row(uid, g, "写作知识", concept="")
            craft = await _seed_row(uid, g, "笔法", parent_id=root, concept="文笔")
            world = await _seed_row(uid, g, "世界", parent_id=root, concept="世界设定")
            char = await _seed_row(uid, g, "角色", parent_id=root, concept="角色设定")
            other = await _seed_row(uid, g, "其他", parent_id=root, concept="")
            # 枝干下叶子：笔法下先插「声音招式」再插「叙事身份」——验发版序（叙事身份在前）
            await _seed_row(uid, g, "声音招式", parent_id=craft, concept="文风")
            await _seed_row(uid, g, "叙事身份", parent_id=craft, concept="文风")
            # 角色下叶子乱序插——验发版序（主角/配角/反派/核心）
            await _seed_row(uid, g, "反派", parent_id=char, concept="角色设定")
            await _seed_row(uid, g, "核心", parent_id=char, concept="角色设定")
            await _seed_row(uid, g, "配角", parent_id=char, concept="角色设定")
            await _seed_row(uid, g, "主角", parent_id=char, concept="角色设定")
            # 孤儿：老角色库迁移知识行（parent_id 空、非根行）——不进树
            await _seed_row(uid, g, "马望津", concept="角色设定", origin="manual")
            await _seed_row(uid, g, "萧铁衣", concept="角色设定", origin="manual")
            return root, [craft, world, char, other]
        _root, _branch_ids = _run(_seed())

        async def _call():
            async with async_session() as db:
                return await graph_tree_api(genre=g, user={"id": uid}, db=db)
        data = _run(_call())["data"]

        roots = data["roots"]
        assert len(roots) == 1, f"唯一根：{[r['title'] for r in roots]}"
        top = roots[0]
        assert top["title"] == "写作知识"
        kid_titles = [k["title"] for k in top["children"]]
        # 发版序：笔法 → 世界 → 角色 → 其他（taxonomy 文件序）
        assert kid_titles == ["笔法", "世界", "角色", "其他"], kid_titles
        craft = top["children"][0]
        assert [k["title"] for k in craft["children"]] == ["叙事身份", "声音招式"], "笔法叶子按发版序"
        char = top["children"][2]
        assert [k["title"] for k in char["children"]] == ["主角", "配角", "反派", "核心", ], char["children"] or [k["title"] for k in char["children"]]
        # 孤儿老知识行不进树
        all_titles = []
        def _walk(n):
            all_titles.append(n["title"])
            for k in n["children"]:
                _walk(k)
        _walk(top)
        assert "马望津" not in all_titles and "萧铁衣" not in all_titles, all_titles
        # 剥前缀：树面定义不带「题材·标题——」
        assert craft["definition"] == "纯定义。", craft["definition"]

    def test_无根行_回落旧概念根装配(self):
        uid = _mk("legacy")
        _run(_seed_user(uid))
        g = "都市"
        _run(_seed_row(uid, g, "老知识", concept="手法", origin="manual"))

        async def _call():
            async with async_session() as db:
                return await graph_tree_api(genre=g, user={"id": uid}, db=db)
        data = _run(_call())["data"]
        # 概念根兜底：kind=root 的组在，老知识挂组下
        assert len(data["roots"]) == 1 and data["roots"][0]["kind"] == "root"
        assert data["roots"][0]["children"][0]["title"] == "老知识"
