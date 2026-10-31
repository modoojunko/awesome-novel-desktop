"""知识库备份段测试（c-knowledge-base 批5）：配置包 knowledge_base 段、单书 kb 段、导入幂等与标签重建、旧包缺段跳过。"""

import asyncio
import io
import json
import uuid
import zipfile

import yaml

from db import async_session
from models.kb import KbBookBinding, KbEntry, KbEntryTag, KbLibrary, KbPref
from models.project import Novel
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _entry(user_id: str, genre: str, concept: str, payload: dict) -> KbEntry:
    return KbEntry(
        user_id=user_id, genre=genre, concept=concept, concept_id=f"{genre}:{concept}",
        title="t", payload_json=json.dumps(payload, ensure_ascii=False),
        instruction="x。", when_json="{}", src_kind="manual",
    )


async def _seed() -> dict:
    uid = f"kbak-{uuid.uuid4().hex[:8]}"
    slug = f"kbak-{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        db.add(User(
            id=uid, email=f"{uid}@t.local", password_hash="x", display_name="备份测试",
            api_key="", api_base_url="", api_model="",
        ))
        novel = Novel(
            user_id=uid, name="备份测试书", slug=slug, root_path=f"./data/{slug}",
            source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        e = _entry(uid, "都市", "文风", {"slot": "role", "role": "冷峻旁白"})
        lib = KbLibrary(user_id=uid, genre="都市", concept="文风", name="文风库", contract="snapshot", rule_kind="auto")
        pref = KbPref(user_id=uid, entry_id="placeholder", weight=1.0, adopt_count=1)
        db.add_all([e, lib, pref])
        await db.flush()
        pref.entry_id = e.id
        binding = KbBookBinding(novel_id=novel.id, library_id=lib.id, enabled=True, snapshot_json="{}")
        db.add(binding)
        await db.commit()
        # 直插条目绕过了 service 物化——备份导出前补建标签索引（顺带当 rebuild 用例）
        from kb.service import rebuild_tag_index

        await rebuild_tag_index(db, user_id=uid)
        return {"uid": uid, "novel_id": novel.id, "entry_id": e.id, "lib_id": lib.id}


def test_配置包含knowledge_base段与预览摘要():
    from backup.export import build_config_package_bytes, config_preview

    seed = _run(_seed())

    async def _go():
        async with async_session() as db:
            data, name = await build_config_package_bytes(db, seed["uid"])
            preview = await config_preview(db, seed["uid"])
            return data, name, preview

    data, _name, preview = _run(_go())
    assert preview["knowledge_base"] == {"entries": 1, "libraries": 1}
    zf = zipfile.ZipFile(io.BytesIO(data))
    cfg = yaml.safe_load(zf.read("config.yaml"))
    kb = cfg["knowledge_base"]
    assert cfg["format_version"] == 9
    assert len(kb["entries"]) == 1 and kb["entries"][0]["id"] == seed["entry_id"]
    assert len(kb["libraries"]) == 1
    assert len(kb["prefs"]) == 1
    assert len(kb["entry_tags"]) >= 1  # 物化标签随包（导入端不导入，重建）
    assert "concepts" in kb and "relations" in kb


def test_单书包含kb书内段():
    from backup.export import dump_book_into
    from models.project import Novel

    seed = _run(_seed())

    async def _go():
        async with async_session() as db:
            novel = await db.get(Novel, seed["novel_id"])
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                await dump_book_into(zf, db, novel)
            return buf.getvalue()

    zf = zipfile.ZipFile(io.BytesIO(_run(_go())))
    doc = yaml.safe_load(zf.read("kb/kb-book.yaml"))
    assert len(doc["bindings"]) == 1
    assert doc["bindings"][0]["library_id"] == seed["lib_id"]
    assert doc["match_runs"] == []


def test_导入配置包_kb段_幂等_标签重建():
    from backup.export import build_config_package_bytes
    from backup.importer import _restore_config
    from models.kb import KbEntry as E

    seed = _run(_seed())

    async def _export(sd):
        async with async_session() as db:
            return await build_config_package_bytes(db, sd["uid"])

    data, _ = _run(_export(seed))

    # 导入到全新用户
    uid2 = f"kbak2-{uuid.uuid4().hex[:8]}"

    async def _setup_user():
        async with async_session() as db:
            db.add(User(
                id=uid2, email=f"{uid2}@t.local", password_hash="x", display_name="恢复测试",
                api_key="", api_base_url="", api_model="",
            ))
            await db.commit()

    _run(_setup_user())

    async def _import():
        async with async_session() as db:
            zf = zipfile.ZipFile(io.BytesIO(data))
            cfg = yaml.safe_load(zf.read("config.yaml"))
            # 共享测试库同 id 已存在——改写包内 id 模拟「全新设备恢复」
            import uuid as _u

            new_eid, new_lid = str(_u.uuid4()), str(_u.uuid4())
            cfg["knowledge_base"]["entries"][0]["id"] = new_eid
            cfg["knowledge_base"]["libraries"][0]["id"] = new_lid
            cfg["knowledge_base"]["library_items"] = []
            cfg["knowledge_base"]["prefs"][0]["entry_id"] = new_eid
            summary = await _restore_config(db, uid2, cfg)
            await db.commit()
            # 幂等：二次导入全 skip
            summary2 = await _restore_config(db, uid2, cfg)
            await db.commit()
            n = (
                await db.scalars(
                    __import__("sqlalchemy", fromlist=["select"]).select(E.id).where(E.user_id == uid2)
                )
            ).all()
            tags = (
                await db.scalars(
                    __import__("sqlalchemy", fromlist=["select"]).select(KbEntryTag.id).where(KbEntryTag.user_id == uid2)
                )
            ).all()
            return summary, summary2, len(n), len(tags)

    summary, summary2, entries_n, tags_n = _run(_import())
    assert summary["knowledge_base"]["created"]["entries"] == 1
    assert summary2["knowledge_base"]["created"]["entries"] == 0  # 二次全 skip
    assert summary2["knowledge_base"]["skipped"]["entries"] == 1
    assert entries_n == 1
    assert tags_n >= 1  # 恢复后标签索引已重建


def test_旧包缺kb段跳过不报错():
    from backup.importer import _restore_config

    uid = f"kbak3-{uuid.uuid4().hex[:8]}"

    async def _go():
        async with async_session() as db:
            db.add(User(
                id=uid, email=f"{uid}@t.local", password_hash="x", display_name="旧包测试",
                api_key="", api_base_url="", api_model="",
            ))
            await db.commit()
            cfg = {"format_version": 8, "user": {"display_name": "x"}, "api_configs": []}
            summary = await _restore_config(db, uid, cfg)
            await db.commit()
            return summary

    summary = _run(_go())
    assert "knowledge_base" not in summary  # 缺段整体跳过
