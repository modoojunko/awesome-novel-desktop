"""跨知识实例行列表测试（c-kb-instance-list 任务 1.1/1.2）。

覆盖四件套钉死的过滤边界：归档知识（archived_at 不动 status）/ merged 双滤、
已归属素材（archived）不再以素材行出现、情节素材排除、孤儿链跳级、
chain 后端拼好（题材段不入链）、src_kind 归一、created_at 倒序归并、
跨 user 隔离（userB 建知识＋其下实例，userA 请求不可见）。
"""

import asyncio
import uuid
from datetime import datetime

from db import async_session
from kb.router import list_instances_flat_api
from kb.service import add_instance, create_entry, list_instances_flat
from models.kb import KbEntry
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _mk(tag: str) -> str:
    return f"kbif-{tag}-{uuid.uuid4().hex[:8]}"


async def _seed_user(uid: str):
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="实例行钉"))
        await db.commit()


async def _mk_knowledge(uid: str, *, genre: str = "玄幻", concept: str = "手法",
                        title: str = "", definition: str = "d") -> str:
    async with async_session() as db:
        e, _gate, err = await create_entry(
            db, user_id=uid, genre=genre, concept=concept,
            title=title, instruction="知识行", payload={},
            definition=definition, as_knowledge=True,
        )
        assert err is None, f"知识行建库失败: {err}"
        return e.id


async def _mk_material(uid: str, *, genre: str = "玄幻", concept: str = "手法",
                       instruction: str = "素材句。", src_kind: str = "deconstruct",
                       src_novel_name: str = "") -> str:
    async with async_session() as db:
        e, _gate, err = await create_entry(
            db, user_id=uid, genre=genre, concept=concept,
            instruction=instruction, payload={}, as_material=True,
            src_kind=src_kind, src_novel_name=src_novel_name,
        )
        assert err is None, f"素材行建库失败: {err}"
        return e.id


async def _flat(uid: str, **kw) -> list[dict]:
    async with async_session() as db:
        return await list_instances_flat(db, user_id=uid, **kw)


class TestRowsAndChain:
    def test_两类行_形状与chain(self):
        uid = _mk("shape")
        _run(_seed_user(uid))
        parent_id = _run(_mk_knowledge(uid, title="人物塑造", concept="角色设定"))
        kid = _run(_mk_knowledge(uid, title="主角", concept="角色设定"))
        _run(_set_parent(kid, parent_id))
        inst_id = _run(_add_inst(uid, kid, text="何沉舟胆小多疑", source_kind="拆书"))
        mat_id = _run(_mk_material(uid, instruction="素材原句", src_kind="manual"))

        rows = _run(_flat(uid))
        kinds = {r["row_kind"] for r in rows}
        assert kinds == {"instance", "material"}

        inst = next(r for r in rows if r["id"] == inst_id)
        assert inst["knowledge_id"] == kid
        assert inst["knowledge_title"] == "主角"
        # chain 后端拼好：顶层父在前、末段＝所属知识点；题材段不入链
        assert [c["title"] for c in inst["chain"]] == ["人物塑造", "主角"]
        assert [c["id"] for c in inst["chain"]] == [parent_id, kid]
        assert inst["text"] == "何沉舟胆小多疑"
        assert inst["src_kind"] == "拆书"

        mat = next(r for r in rows if r["id"] == mat_id)
        assert mat["row_kind"] == "material"
        assert mat["knowledge_id"] == "" and mat["chain"] == []
        assert mat["text"] == "素材原句" and mat["quote"] == ""
        assert mat["src_kind"] == "手录"

    def test_孤儿parent链_跳级不炸(self):
        uid = _mk("orphan")
        _run(_seed_user(uid))
        kid = _run(_mk_knowledge(uid))
        _run(_set_parent(kid, "nonexistent-" + uuid.uuid4().hex[:8]))
        _run(_add_inst(uid, kid, text="x"))

        rows = _run(_flat(uid))
        inst = next(r for r in rows if r["row_kind"] == "instance")
        assert len(inst["chain"]) == 1, "父行不存在应跳级，不炸不编链"

    def test_src_kind归一_只出拆书手录两值(self):
        uid = _mk("src")
        _run(_seed_user(uid))
        kid = _run(_mk_knowledge(uid))
        _run(_add_inst(uid, kid, text="a", source_kind="manual"))
        _run(_add_inst(uid, kid, text="b", source_kind="随便填的值"))
        _run(_mk_material(uid, src_kind="deconstruct"))
        _run(_mk_material(uid, src_kind="manual"))

        rows = _run(_flat(uid))
        assert {r["src_kind"] for r in rows} <= {"拆书", "手录"}
        by_text = {r["text"]: r["src_kind"] for r in rows}
        assert by_text["a"] == "手录"
        assert by_text["b"] == "拆书"  # 未知值归一为拆书（与 summarize 二值口径一致）


async def _set_parent(entry_id: str, parent_id: str):
    async with async_session() as db:
        e = await db.get(KbEntry, entry_id)
        e.parent_id = parent_id
        await db.commit()


async def _add_inst(uid: str, kid: str, *, text: str, source_kind: str = "拆书",
                    source_novel: str = "") -> str:
    async with async_session() as db:
        inst = await add_instance(
            db, knowledge_id=kid, text=text,
            source_kind=source_kind, source_novel=source_novel,
        )
        return inst.id


class TestFilterBoundaries:
    def test_已归属素材_不再以素材行出现(self):
        uid = _mk("archmat")
        _run(_seed_user(uid))
        mat_id = _run(_mk_material(uid))
        _run(_mk_knowledge(uid))
        _run(_archive_material(mat_id))

        rows = _run(_flat(uid))
        assert all(r["id"] != mat_id for r in rows), "已归属素材已归档，不得再挂待归属标"

    def test_已归档知识_其实例被排除(self):
        uid = _mk("archkb")
        _run(_seed_user(uid))
        kid = _run(_mk_knowledge(uid))
        _run(_add_inst(uid, kid, text="x"))
        _run(_archive_knowledge(kid))

        rows = _run(_flat(uid))
        assert rows == [], "归档知识只写 archived_at 不动 status——实例行必须一并排除"

    def test_merged知识_其实例被排除(self):
        uid = _mk("merged")
        _run(_seed_user(uid))
        kid = _run(_mk_knowledge(uid))
        _run(_add_inst(uid, kid, text="x"))

        async def _merge():
            async with async_session() as db:
                e = await db.get(KbEntry, kid)
                e.status = "merged"
                await db.commit()
        _run(_merge())

        assert _run(_flat(uid)) == []

    def test_情节素材_不出现在列表(self):
        uid = _mk("plot")
        _run(_seed_user(uid))
        _run(_mk_material(uid, concept="情节", instruction="情节素材句"))

        assert _run(_flat(uid)) == []

    def test_genre_concept过滤_空串不过滤(self):
        uid = _mk("filt")
        _run(_seed_user(uid))
        kid_a = _run(_mk_knowledge(uid, genre="玄幻", concept="手法"))
        kid_b = _run(_mk_knowledge(uid, genre="都市", concept="文风"))
        _run(_add_inst(uid, kid_a, text="手法实例"))
        _run(_add_inst(uid, kid_b, text="文风实例"))

        all_rows = _run(_flat(uid))
        assert {r["concept"] for r in all_rows} == {"手法", "文风"}
        assert {r["genre"] for r in all_rows} == {"玄幻", "都市"}

        only_xh = _run(_flat(uid, genre="玄幻"))
        assert {r["knowledge_id"] for r in only_xh} == {kid_a}
        only_wf = _run(_flat(uid, concept="文风"))
        assert {r["knowledge_id"] for r in only_wf} == {kid_b}

    def test_q覆盖_实例文本_素材句_知识名_来源书名(self):
        uid = _mk("qcov")
        _run(_seed_user(uid))
        kid = _run(_mk_knowledge(uid, title="开篇钩子"))
        _run(_add_inst(uid, kid, text="先写结果再倒拆", source_novel="13路末班车"))
        _run(_mk_material(uid, instruction="夜雨转场的素材", src_novel_name="旧城书"))

        assert len(_run(_flat(uid, q="倒拆"))) == 1  # 实例 text
        assert len(_run(_flat(uid, q="夜雨转场"))) == 1  # 素材 instruction
        assert len(_run(_flat(uid, q="开篇钩子"))) == 1  # 所属知识名
        assert len(_run(_flat(uid, q="13路末班车"))) == 1  # 实例来源书名
        assert _run(_flat(uid, q="不存在的词")) == []

    def test_created_at倒序归并_两类行混排(self):
        uid = _mk("order")
        _run(_seed_user(uid))
        kid = _run(_mk_knowledge(uid))
        _run(_add_inst(uid, kid, text="旧实例"))
        _run(_mk_material(uid))
        _run(_add_inst(uid, kid, text="新实例"))

        rows = _run(_flat(uid))
        assert len(rows) == 3
        stamps = [r["created_at"] for r in rows]
        assert stamps == sorted(stamps, key=lambda t: t or datetime.min, reverse=True), \
            "两类行须按 created_at 归并倒序（最近进列表在前）"

    def test_跨user隔离_他人知识及其实例不可见(self):
        uid_a = _mk("userA")
        uid_b = _mk("userB")
        _run(_seed_user(uid_a))
        _run(_seed_user(uid_b))
        # userB 建知识＋其下实例（隔离靠 JOIN 侧谓词，不能只造孤立实例行）
        kid_b = _run(_mk_knowledge(uid_b))
        _run(_add_inst(uid_b, kid_b, text="userB 的实例"))
        _run(_mk_material(uid_b))
        # userA 自己也有内容
        kid_a = _run(_mk_knowledge(uid_a))
        _run(_add_inst(uid_a, kid_a, text="userA 自己的实例"))

        rows = _run(_flat(uid_a))
        assert [r["text"] for r in rows] == ["userA 自己的实例"]


async def _archive_material(entry_id: str):
    """素材归属：summarize 同款——status 置 archived。"""
    async with async_session() as db:
        e = await db.get(KbEntry, entry_id)
        e.status = "archived"
        await db.commit()


async def _archive_knowledge(entry_id: str):
    """知识归档：archive_knowledge 同款——只写 archived_at 不动 status。"""
    async with async_session() as db:
        e = await db.get(KbEntry, entry_id)
        e.archived_at = datetime.now()
        await db.commit()


class TestEndpoint:
    def test_空库返回空数组_无分页字段(self):
        uid = _mk("ep")
        _run(_seed_user(uid))

        async def _go():
            async with async_session() as db:
                return await list_instances_flat_api(
                    genre="", concept="", q="",
                    user={"id": uid}, db=db,
                )
        resp = _run(_go())
        assert resp == {"ok": True, "data": {"rows": []}}
        assert "cursor" not in resp and "next_cursor" not in resp and "total" not in resp

    def test_过滤参数透传(self):
        uid = _mk("epparam")
        _run(_seed_user(uid))
        kid = _run(_mk_knowledge(uid, concept="手法"))
        _run(_add_inst(uid, kid, text="手法实例"))

        async def _go(**params):
            async with async_session() as db:
                return await list_instances_flat_api(
                    user={"id": uid}, db=db, **params)
        resp = _run(_go(genre="玄幻", concept="手法", q="手法"))
        assert resp["ok"] is True and len(resp["data"]["rows"]) == 1
        resp_miss = _run(_go(genre="都市"))
        assert resp_miss["data"]["rows"] == []
