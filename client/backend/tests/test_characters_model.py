"""characters / character_relations / character_gate / character_ops 表约束测试。

对应 tasks 2.1：各唯一约束、主角部分唯一索引、FK ON DELETE 行为、
seq 计数器不复用、JSON 列默认值。
"""

import uuid

import pytest
from sqlalchemy import select, update

from db import async_session
from models.character import Character, CharacterGate, CharacterOp, CharacterRelation
from models.project import Novel
from models.user import User


async def _seed_novel() -> tuple[str, str]:
    uid = f"chm-{uuid.uuid4().hex[:8]}"
    slug = f"chm-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="约束测试", api_key="", api_base_url="", api_model="",
        ))
        proj = Novel(
            user_id=uid, name="约束测试书", slug=slug,
            root_path=f"./data/{slug}", source="manual", current_phase="write",
        )
        session.add(proj)
        await session.commit()
        return uid, proj.id


async def _add_character(novel_id: str, name: str, role: str = "配角", seq: int | None = None) -> Character:
    async with async_session() as session:
        if seq is None:
            # 模拟服务层取号：读计数器 +1 回写
            novel = await session.get(Novel, novel_id)
            novel.character_seq_high += 1
            await session.flush()
            seq = novel.character_seq_high
        ch = Character(
            novel_id=novel_id, seq=seq, name=name, role=role,
        )
        session.add(ch)
        await session.commit()
        await session.refresh(ch)
        return ch


def _expect_integrity(coro):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        import asyncio
        asyncio.run(coro)


class TestCharacterConstraints:
    def test_seq_counter_never_reuses_after_delete(self):
        """删掉最大号卡再建卡 → 拿新号，不复用（tasks 2.1 关键断言）。"""
        uid, nid = asyncio_run(_seed_novel())
        a = asyncio_run(_add_character(nid, "甲"))
        b = asyncio_run(_add_character(nid, "乙"))
        assert (a.seq, b.seq) == (1, 2)

        async def _del_and_recreate():
            async with async_session() as session:
                row = await session.get(Character, b.id)
                await session.delete(row)
                await session.commit()
            return await _add_character(nid, "丙")

        c = asyncio_run(_del_and_recreate())
        assert c.seq == 3  # 不是 2（MAX+1 会复用）

    def test_duplicate_name_rejected(self):
        uid, nid = asyncio_run(_seed_novel())
        asyncio_run(_add_character(nid, "林拾"))

        async def _dup():
            return await _add_character(nid, "林拾")

        _expect_integrity(_dup())

    def test_two_protagonists_rejected_by_partial_index(self):
        uid, nid = asyncio_run(_seed_novel())
        asyncio_run(_add_character(nid, "主角甲", role="主角"))

        async def _second_prot():
            return await _add_character(nid, "主角乙", role="主角")

        _expect_integrity(_second_prot())

    def test_demote_then_promote_in_order_passes(self):
        """先降后升（含 flush 间隔）→ 换主角成功（服务层事务的形状依据）。"""
        uid, nid = asyncio_run(_seed_novel())
        prot = asyncio_run(_add_character(nid, "原主角", role="主角"))
        other = asyncio_run(_add_character(nid, "挑战者"))

        async def _swap():
            async with async_session() as session:
                # 条件写降级 + 显式 flush（与 design.md D1 的硬约束一致）
                await session.execute(
                    update(Character)
                    .where(Character.novel_id == nid, Character.role == "主角")
                    .values(role="配角")
                )
                await session.flush()
                row = await session.get(Character, other.id)
                row.role = "主角"
                await session.commit()
                roles = {
                    r.name: r.role for r in (
                        await session.scalars(
                            select(Character).where(Character.novel_id == nid)
                        )
                    ).all()
                }
                return roles

        roles = asyncio_run(_swap())
        assert roles == {"原主角": "配角", "挑战者": "主角"}
        _ = prot

    def test_json_columns_default_shape(self):
        _uid, nid = asyncio_run(_seed_novel())
        ch = asyncio_run(_add_character(nid, "空卡"))
        assert ch.dossier == "{}" and ch.cog == "{}" and ch.legacy == "{}"
        assert ch.aliases == "[]" and ch.rev == 1


class TestRelationConstraints:
    def test_same_pair_unique_and_cascade(self):
        _uid, nid = asyncio_run(_seed_novel())
        a = asyncio_run(_add_character(nid, "甲"))
        b = asyncio_run(_add_character(nid, "乙"))

        async def _add_rel():
            async with async_session() as session:
                rel = CharacterRelation(
                    novel_id=nid, owner_id=a.id, other_id=b.id, rel_type="同盟",
                )
                session.add(rel)
                await session.commit()
                await session.refresh(rel)
                return rel

        rel = asyncio_run(_add_rel())
        assert rel.rev == 1

        async def _dup():
            async with async_session() as session:
                session.add(CharacterRelation(
                    novel_id=nid, owner_id=a.id, other_id=b.id, rel_type="敌对",
                ))
                await session.commit()

        _expect_integrity(_dup())

        # 删 owner → 关系级联消失
        async def _del_owner():
            async with async_session() as session:
                row = await session.get(Character, a.id)
                await session.delete(row)
                await session.commit()
                left = (await session.scalars(
                    select(CharacterRelation).where(CharacterRelation.novel_id == nid)
                )).all()
                return len(left)

        assert asyncio_run(_del_owner()) == 0

    def test_reverse_direction_is_a_separate_row(self):
        """单向语义：甲看乙 ≠ 乙看甲——反向是合法的另一条。"""
        uid, nid = asyncio_run(_seed_novel())
        a = asyncio_run(_add_character(nid, "甲"))
        b = asyncio_run(_add_character(nid, "乙"))
        asyncio_run(_add_rel(nid, a.id, b.id, "师徒"))

        async def _reverse():
            return await _add_rel(nid, b.id, a.id, "师徒")

        rel = asyncio_run(_reverse())
        assert rel.owner_id == b.id and rel.other_id == a.id


async def _add_rel(nid: str, owner: str, other: str, rel_type: str) -> CharacterRelation:
    async with async_session() as session:
        rel = CharacterRelation(novel_id=nid, owner_id=owner, other_id=other, rel_type=rel_type)
        session.add(rel)
        await session.commit()
        await session.refresh(rel)
        return rel


class TestGateAndOps:
    def test_gate_one_row_per_novel_and_protagonist_setnull(self):
        _uid, nid = asyncio_run(_seed_novel())
        prot = asyncio_run(_add_character(nid, "主角", role="主角"))

        async def _seed_gate():
            async with async_session() as session:
                session.add(CharacterGate(
                    novel_id=nid, protagonist_id=prot.id, fingerprint="ab" * 8,
                ))
                await session.commit()

        asyncio_run(_seed_gate())

        async def _second_gate():
            async with async_session() as session:
                session.add(CharacterGate(novel_id=nid, fingerprint="cd" * 8))
                await session.commit()

        _expect_integrity(_second_gate())

        # 删主角 → gate 行还在（审计），protagonist_id 置 NULL
        async def _del_prot():
            async with async_session() as session:
                row = await session.get(Character, prot.id)
                await session.delete(row)
                await session.commit()
                gate = await session.get(CharacterGate, nid)
                return gate, gate.protagonist_id

        gate, pid = asyncio_run(_del_prot())
        assert gate is not None and pid is None

    def test_op_token_unique_and_fields(self):
        _uid, nid = asyncio_run(_seed_novel())
        token = uuid.uuid4().hex

        async def _add_op():
            async with async_session() as session:
                from datetime import datetime, timedelta
                session.add(CharacterOp(
                    novel_id=nid, kind="delete", before="{}",
                    undo_token=token, expires_at=datetime.now() + timedelta(seconds=600),
                ))
                await session.commit()

        asyncio_run(_add_op())

        async def _dup_token():
            async with async_session() as session:
                from datetime import datetime, timedelta
                session.add(CharacterOp(
                    novel_id=nid, kind="merge", before="{}",
                    undo_token=token, expires_at=datetime.now() + timedelta(seconds=600),
                ))
                await session.commit()

        _expect_integrity(_dup_token())


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)

