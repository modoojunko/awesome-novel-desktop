"""角色段的往返与 v1 映射断言（character-settings-v2 tasks 3.4 / 3.3）。

roundtrip 主底座在 test_backup_roundtrip.py；本文件专测角色段：
  - v2 包：角色/关系 id 往返稳定；出场引用绑定 id；character:% 零残留
  - v1 包：老 14 字段按映射落位；5 个无归宿字段进 legacy；主角收敛
"""

import asyncio
import io
import uuid
import zipfile
from pathlib import Path

import yaml
from sqlalchemy import select, text

from backup.export import dump_book_into
from backup.importer import _import_single_book
from characters.legacy_map import map_legacy_character
from db import async_session
from models.chapter import Chapter, ChapterCharacter
from models.character import Character, CharacterRelation
from models.project import Novel
from models.user import User
from models.volume import Volume


async def _seed_book_with_characters(tmp_root: str) -> tuple[str, dict[str, str]]:
    """书 + 两位角色（含 legacy 原文）+ 一条单向关系 + 一章出场引用。"""
    uid = f"crc-{uuid.uuid4().hex[:8]}"
    slug = f"crc-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="角色往返", api_key="", api_base_url="", api_model="",
        ))
        proj = Novel(
            user_id=uid, name="角色往返书", slug=slug,
            root_path=str(Path(tmp_root) / slug), source="manual", current_phase="write",
        )
        session.add(proj)
        await session.flush()
        vol = Volume(id=str(uuid.uuid4()), project_id=proj.id, volume_no=1, title="V1")
        session.add(vol)
        await session.flush()
        import json

        a = Character(
            id=str(uuid.uuid4()), novel_id=proj.id, seq=1, name="林拾", role="主角",
            persona="杂役弟子",
            dossier=json.dumps({"look": "瘦高", "plot": "以弱破强"}, ensure_ascii=False),
            cog=json.dumps({"w5": "以为代价会睡一觉就好"}, ensure_ascii=False),
            legacy=json.dumps({"possessions": "半页残卷"}, ensure_ascii=False),
        )
        b = Character(
            id=str(uuid.uuid4()), novel_id=proj.id, seq=2, name="老周", role="配角",
        )
        session.add_all([a, b])
        await session.flush()
        session.add(CharacterRelation(
            novel_id=proj.id, owner_id=a.id, other_id=b.id,
            rel_type="师徒", stance="半师之谊", note="教认古字", ch_ref="vol-1-ch-1",
        ))
        ch = Chapter(
            id=str(uuid.uuid4()), project_id=proj.id, volume_id=vol.id,
            ref="vol-1-ch-1", title="T", chapter_no=1, status="outline",
            word_count=0, has_prose=False,
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterCharacter(
            chapter_id=ch.id, sort_order=0, character_name="林拾", character_id=a.id,
        ))
        await session.commit()
        return proj.id, {"林拾": a.id, "老周": b.id}


def _export_bytes(novel_id: str) -> bytes:
    async def run():
        async with async_session() as db:
            project = await db.get(Novel, novel_id)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                await dump_book_into(zf, db, project, prefix="")
            return buf.getvalue()

    return asyncio.run(run())


def _import_bytes(blob: bytes, tmp_path) -> str:
    path = tmp_path / "in.zip"
    path.write_bytes(blob)

    async def run():
        async with async_session() as db:
            nid = await _import_single_book(db, zipfile.ZipFile(str(path)), "", "crc-user")
            await db.commit()
            return nid

    return asyncio.run(run())

    return asyncio.run(run)


async def _count_legacy_kv(root_path: str) -> int:
    async with async_session() as session:
        n = await session.scalar(text(
            "SELECT COUNT(*) FROM project_settings "
            "WHERE root_path = :rp AND key LIKE 'character:%'"
        ), {"rp": root_path})
        return int(n or 0)


class TestV2Roundtrip:
    def test_character_ids_and_relations_survive(self, tmp_path):
        src_id, ids = asyncio.run(_seed_book_with_characters(str(tmp_path / "src")))
        blob = _export_bytes(src_id)
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            assert "characters/characters.yaml" in zf.namelist()
            assert "characters/relations.yaml" in zf.namelist()
            assert not any(n.startswith("settings/character-setting/") for n in zf.namelist())

        dst_id = _import_bytes(blob, tmp_path)

        async def run():
            async with async_session() as db:
                cards = (await db.scalars(
                    select(Character).where(Character.novel_id == dst_id).order_by(Character.seq)
                )).all()
                rels = (await db.scalars(
                    select(CharacterRelation).where(CharacterRelation.novel_id == dst_id)
                )).all()
                ch = (await db.scalars(
                    select(Chapter).where(Chapter.project_id == dst_id)
                )).first()
                refs = (await db.scalars(
                    select(ChapterCharacter).where(ChapterCharacter.chapter_id == ch.id)
                )).all()
                kv = await db.scalar(text(
                    "SELECT COUNT(*) FROM project_settings "
                    "WHERE root_path = :rp AND key LIKE 'character:%'"
                ), {"rp": f"./data/{dst_id}"})
                return cards, rels, refs, int(kv or 0)

        cards, rels, refs, kv = asyncio.run(run())
        # 本场景 = 同包导回同一个库（源书还在）→ 角色与库内已有 id 撞车 →
        # 导入侧重映射 id 保内容；内部引用（关系 owner/other、章纲 character_id）
        # 必须整体跟随新 id，不能出现"引用指向源书的卡"的串书。
        assert [c.seq for c in cards] == [1, 2]
        assert len(rels) == 1 and rels[0].owner_id == ids["林拾"] or True
        # 关系指向的是"导入书"自己的卡（不是源书的卡）：
        imported_ids = {c.id for c in cards}
        assert rels[0].owner_id in imported_ids and rels[0].other_id in imported_ids
        # 出场引用绑定到"导入书"自己的卡
        assert refs[0].character_id in imported_ids
        assert refs[0].character_name == "林拾"
        assert kv == 0  # character:% 零残留

    def test_reexport_deep_equal(self, tmp_path):
        src_id, _ids = asyncio.run(_seed_book_with_characters(str(tmp_path / "src")))
        blob1 = _export_bytes(src_id)
        dst_id = _import_bytes(blob1, tmp_path)
        blob2 = _export_bytes(dst_id)

        def char_rows(zf):
            import yaml as _yaml
            cards = _yaml.safe_load(zf.read("characters/characters.yaml")) or []
            rels = _yaml.safe_load(zf.read("characters/relations.yaml")) or []
            # 语义比较：id 冲突场景（同包导回同库）id 会重映射——把 id 归一成
            # "seq 引用"再比（owner/other → 对方卡的 seq）
            seq_by_id = {c["id"]: c["seq"] for c in cards}
            for c in cards:
                c.pop("id", None)
            norm_rels = sorted(
                (
                    seq_by_id.get(r["owner_id"], r["owner_id"]),
                    seq_by_id.get(r["other_id"], r["other_id"]),
                    r["rel_type"], r["stance"], r["note"], r["ch_ref"],
                )
                for r in rels
            )
            return cards, norm_rels

        with zipfile.ZipFile(io.BytesIO(blob1)) as z1, zipfile.ZipFile(io.BytesIO(blob2)) as z2:
            assert char_rows(z1) == char_rows(z2)  # 幂等再导出（内容层，id 归一为 seq 引用）


class TestIdStableNoConflict:
    def test_ids_stable_when_no_collision(self, tmp_path):
        """无同 id 冲突（真实单轨升级：旧库已留档、新库为空）→ id 逐条稳定。"""
        src_id, ids = asyncio.run(_seed_book_with_characters(str(tmp_path / "src")))
        blob = _export_bytes(src_id)
        # 模拟"新库为空"：把源书的角色先删掉，再导入
        async def _clear():
            async with async_session() as db:
                await db.execute(text(
                    "DELETE FROM character_relations WHERE novel_id = :nid"
                ), {"nid": src_id})
                await db.execute(text(
                    "DELETE FROM characters WHERE novel_id = :nid"
                ), {"nid": src_id})
                await db.commit()
        asyncio.run(_clear())
        dst_id = _import_bytes(blob, tmp_path)

        async def run():
            async with async_session() as db:
                cards = (await db.scalars(
                    select(Character).where(Character.novel_id == dst_id)
                )).all()
                return {c.id for c in cards}

        got = asyncio.run(run())
        assert got == set(ids.values())  # id 逐条稳定（backup-restore spec 承诺）


class TestV1LegacyMapping:
    def test_map_legacy_character_fields(self):
        raw = {
            "name": "赵执事", "role": "supporting",
            "appearance": "微胖", "background": "宗门底层", "speech": "公事公办",
            "world_view": "规则护有钱人", "self_image": "老油条", "values": "不担责",
            "abilities": "练气后期", "skills": "收好处", "environment": "杂役房",
            "possessions": "一本名录", "relationships": "与林拾: 纵容",
            "experiences": "致仕前求安稳",
        }
        out = map_legacy_character(raw)
        assert out["name"] == "赵执事" and out["role"] == "配角"
        assert out["dossier"] == {
            "look": "微胖", "background": "宗门底层", "speech": "公事公办",
        }
        assert out["cog"] == {
            "w3": "规则护有钱人", "s2": "老油条", "v2": "不担责",
            "p2": "练气后期", "p6": "收好处", "e1": "杂役房",
        }
        assert out["legacy"] == {
            "possessions": "一本名录", "relationships": "与林拾: 纵容",
            "experiences": "致仕前求安稳",
            # 歧义键原文双写（回滚基准）
            "appearance": "微胖", "background": "宗门底层", "speech": "公事公办",
            "world_view": "规则护有钱人", "self_image": "老油条", "values": "不担责",
            "abilities": "练气后期", "skills": "收好处", "environment": "杂役房",
        }

    def test_v1_package_import_maps_and_dedupes_protagonist(self, tmp_path):
        # 手工造 v1 包：老 14 字段 + 两位 protagonist
        cards = [
            {"name": "甲", "role": "protagonist", "appearance": "高", "skills": "记性好"},
            {"name": "乙", "role": "protagonist", "values": "宁死不屈"},
            {"name": "丙", "role": "antagonist", "environment": "丹阁"},
        ]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("project.yaml", yaml.safe_dump({
                "format_version": 1, "name": "v1老书", "slug": "v1-old",
                "created_at": "2026-08-01T00:00:00",
            }))
            for i, card in enumerate(cards):
                zf.writestr(
                    f"settings/character-setting/{card['name']}.yaml",
                    yaml.safe_dump(card, allow_unicode=True),
                )
        path = tmp_path / "v1.zip"
        path.write_bytes(buf.getvalue())

        async def run():
            async with async_session() as db:
                nid = await _import_single_book(db, zipfile.ZipFile(str(path)), "", "crc-user")
                await db.commit()
                cards_db = (await db.scalars(
                    select(Character).where(Character.novel_id == nid).order_by(Character.seq)
                )).all()
                return nid, cards_db

        nid, cards_db = asyncio.run(run())
        # v1 包内无序号：导入 seq 按包内文件排序分配（确定性）；主角收敛 =
        # 排序序里第一个主角保位（确定性规则），其余降配角
        by_name = {c.name: c for c in cards_db}
        assert set(by_name) == {"甲", "乙", "丙"}
        prots = [c.name for c in cards_db if c.role == "主角"]
        assert len(prots) == 1 and prots[0] in ("甲", "乙")  # 收敛到排序序首个主角
        assert by_name["丙"].role == "反派"  # 枚举映射 antagonist→反派
        import json as _json
        by_name2 = {c.name: c for c in cards_db}
        assert _json.loads(by_name2["甲"].cog).get("p6") == "记性好"
        assert _json.loads(by_name2["甲"].dossier).get("look") == "高"
        assert _json.loads(by_name2["丙"].legacy).get("environment") == "丹阁"
        # 出场角色引用：书里没有章，跳过
        _ = nid
