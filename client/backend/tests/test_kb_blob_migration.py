"""legacy 头像字节搬迁测试（c-kb-character-migration 刀2c ③）：搬运/幂等/孤儿/多用户同键。"""

import asyncio
import json
import uuid

from sqlalchemy import select as sel

from db import async_session
from models.character_library import CharacterLibrary, CharacterLibraryBlob
from models.kb import KbEntry, KbEntryBlob, KbLibrary
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _blob_rows(entry_id: str) -> dict[str, bytes]:
    async def _go():
        async with async_session() as db:
            rows = (await db.execute(
                sel(KbEntryBlob).where(KbEntryBlob.entry_id == entry_id)
            )).scalars().all()
            return {b.variant: b.data for b in rows}
    return _run(_go())


def _legacy_keys_within(keys: set[str]) -> set[str]:
    async def _go():
        async with async_session() as db:
            rows = (await db.execute(
                sel(CharacterLibraryBlob).where(
                    CharacterLibraryBlob.library_id.in_(sorted(keys)))
            )).scalars().all()
            return {r.library_id for r in rows}
    return _run(_go())


def test_搬运_幂等_孤儿_多用户同键():
    from kb.blob_migration import migrate_library_blobs_v1

    suffix = uuid.uuid4().hex[:8]
    uid1, uid2 = f"blobmg1-{suffix}", f"blobmg2-{suffix}"
    old_card = f"lib-{suffix}"           # 迁移卡 id＝legacy blob 键＝entry src_key
    ent1, ent2 = f"ent1-{suffix}", f"ent2-{suffix}"
    orphan_key = f"orphan-{suffix}"      # 无对应条目的孤儿行

    async def _seed():
        async with async_session() as db:
            db.add(User(id=uid1, email=f"{uid1}@t.local", password_hash="x"))
            db.add(User(id=uid2, email=f"{uid2}@t.local", password_hash="x"))
            # legacy blob 行有真 FK：父卡行必须先在场（orphan＝父卡在、kb 条目不在）
            db.add(CharacterLibrary(
                id=old_card, user_id=uid1, name="秦重霄", role="反派", persona="黑风寨大当家。",
            ))
            db.add(CharacterLibrary(
                id=orphan_key, user_id=uid1, name="王五", role="配角", persona="未迁移卡。",
            ))
            # 同一备份恢复到两账号：两个条目同 src_key（唯一索引按 user 分行）
            db.add(KbEntry(
                id=ent1, user_id=uid1, genre="", concept="角色设定",
                concept_id=":角色设定", title="秦重霄",
                payload_json=json.dumps({"archetype": "秦重霄"}, ensure_ascii=False),
                instruction="黑风寨大当家。",
                src_ref="character_library", src_key=old_card,
            ))
            db.add(KbEntry(
                id=ent2, user_id=uid2, genre="", concept="角色设定",
                concept_id=":角色设定", title="秦重霄",
                payload_json=json.dumps({"archetype": "秦重霄"}, ensure_ascii=False),
                instruction="黑风寨大当家。",
                src_ref="character_library", src_key=old_card,
            ))
            # ent1 的 thumb 早已搬过（模拟 ① 期间写入），full 未搬
            db.add(KbEntryBlob(entry_id=ent1, variant="thumb", data=b"OLD-THUMB"))
            db.add(CharacterLibraryBlob(library_id=old_card, variant="full", data=b"OLD-FULL"))
            db.add(CharacterLibraryBlob(library_id=old_card, variant="thumb", data=b"OLD-THUMB"))
            db.add(CharacterLibraryBlob(library_id=orphan_key, variant="full", data=b"ORPHAN"))
            await db.commit()
    _run(_seed())
    watch = {old_card, orphan_key}

    r1 = _run(migrate_library_blobs_v1())
    # full 搬到两个条目（×2）；thumb 行补齐 ent2（ent1 已在）→ 该行 migrated=1
    assert r1["migrated"] == 3, r1
    assert r1["removed"] == 2  # old_card 两行删（full+thumb），orphan 保留
    assert _blob_rows(ent1) == {"full": b"OLD-FULL", "thumb": b"OLD-THUMB"}
    assert _blob_rows(ent2) == {"full": b"OLD-FULL", "thumb": b"OLD-THUMB"}
    assert _legacy_keys_within(watch) == {orphan_key}  # 孤儿行保留（union 读兜底）

    r2 = _run(migrate_library_blobs_v1())
    assert r2["migrated"] == 0 and r2["removed"] == 0
    assert r2["orphaned"] == 1
    assert _blob_rows(ent1) == {"full": b"OLD-FULL", "thumb": b"OLD-THUMB"}


def test_auto库enabled自愈():
    """批3 潜伏 bug：auto 库生成漏传 enabled（default False）→ 书内启用链断。
    heal 翻 True 且幂等；手动圈选库（manual）不动。"""
    from kb.blob_migration import heal_auto_libraries_v1

    suffix = uuid.uuid4().hex[:8]
    uid = f"heal-{suffix}"

    async def _seed():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            db.add(KbLibrary(
                user_id=uid, genre="玄幻", concept="世界设定", name="世界设定库",
                rule_kind="auto", enabled=False,  # 批3 缺陷形态
            ))
            db.add(KbLibrary(
                user_id=uid, genre="玄幻", concept="文风", name="圈选库",
                rule_kind="manual", enabled=False,  # 未来「停用」语义：不动
            ))
            await db.commit()
    _run(_seed())

    healed = _run(heal_auto_libraries_v1())
    assert healed >= 1  # 共享库可能有他测试的 False auto 库一并翻正

    async def _check():
        async with async_session() as db:
            rows = (await db.execute(
                sel(KbLibrary).where(KbLibrary.user_id == uid)
            )).scalars().all()
            return {r.rule_kind: r.enabled for r in rows}
    state = _run(_check())
    assert state["auto"] is True   # auto 库翻正
    assert state["manual"] is False  # 手动库保留停用语义

    # 幂等：再跑一遍不再产生变化（本 uid 范围无 False auto 可翻）
    assert _run(heal_auto_libraries_v1()) >= 0
    assert _run(_check()) == {"auto": True, "manual": False}
