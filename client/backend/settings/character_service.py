"""角色服务层 — 全部跨表事务收在这里，router 只做参数与响应整形。

并发纪律（design.md D1）：
- 单格写入 = 条件 UPDATE（WHERE id=? AND rev=?），rowcount==0 才 409——
  SQLite 无 SELECT FOR UPDATE，"读-比较-ORM 赋值"在并发下必丢字。
- 设主角 = 同事务"先降后升"，两条 UPDATE 之间显式 flush（部分唯一索引）。
- seq 取号 = novels.character_seq_high 计数器同事务读改写（单调不复用）。
- 破坏性操作（删除/合并/删关系）写 character_ops 前像；撤销按前像同事务重放。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from models.character import Character, CharacterGate, CharacterOp, CharacterRelation
from models.project import Novel
from models.volume import Volume
from settings.character_model import (
    COG_KEYS,
    DOSSIER_KEYS,
    RELATION_TYPES,
    ROLES,
    book_characters_gate,
    gate_fingerprint,
)

UNDO_TTL_SECONDS = 600

# 允许单格写入的字段（白名单；dossier.<k>/cog.<k> 的 k 也在各自键集内）
_PATCH_ROOTS = {"name", "aliases", "role", "persona"}


class Conflict(Exception):
    """rev 冲突 / 语义冲突（409）。detail 直接给前端。"""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.detail = {"code": code, "message": message, **extra}


class Unprocessable(Exception):
    """语义拒绝（400 / 422）。"""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.detail = {"code": code, "message": message, **extra}


def _json_dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False)


def card_to_dict(ch: Character) -> dict:
    """显式白名单整形——禁止 model_dump() 直出（legacy 不得出现在任何响应）。"""
    return {
        "id": ch.id,
        "novel_id": ch.novel_id,
        "seq": ch.seq,
        "code": f"C-{ch.seq:04d}",
        "name": ch.name,
        "aliases": json.loads(ch.aliases or "[]"),
        "role": ch.role,
        "persona": ch.persona,
        "dossier": json.loads(ch.dossier or "{}"),
        "cog": json.loads(ch.cog or "{}"),
        "rev": ch.rev,
        "created_at": ch.created_at.isoformat() if ch.created_at else None,
        "updated_at": ch.updated_at.isoformat() if ch.updated_at else None,
    }


def rel_to_dict(rel: CharacterRelation, other_name: str = "") -> dict:
    return {
        "id": rel.id,
        "owner_id": rel.owner_id,
        "other_id": rel.other_id,
        "other_name": other_name,
        "rel_type": rel.rel_type,
        "stance": rel.stance,
        "note": rel.note,
        "ch_ref": rel.ch_ref,
        "rev": rel.rev,
    }


async def _load_card(session: AsyncSession, novel_id: str, character_id: str) -> Character:
    ch = await session.get(Character, character_id)
    if ch is None or ch.novel_id != novel_id:
        raise Unprocessable("not_found", "角色不存在或已删除")
    return ch


async def _card_view(session: AsyncSession, ch: Character) -> dict:
    view = card_to_dict(ch)
    view["first_chapter"] = (await _first_chapters(session, ch.novel_id)).get(ch.id)
    rels = (
        await session.scalars(
            select(CharacterRelation).where(CharacterRelation.owner_id == ch.id)
        )
    ).all()
    names = await _names_by_ids(session, [r.other_id for r in rels])
    view["relations"] = [
        rel_to_dict(r, names.get(r.other_id, "")) for r in rels
    ]
    return view


async def _names_by_ids(session: AsyncSession, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = (
        await session.scalars(
            select(Character).where(Character.id.in_(ids))
        )
    ).all()
    return {r.id: r.name for r in rows}


async def _resolve_character(session: AsyncSession, novel_id: str, name: str) -> Character | None:
    """名字/别名 → 卡（别名命中；同书内名字唯一由 DB 保证）。"""
    rows = (
        await session.scalars(
            select(Character).where(
                Character.novel_id == novel_id, Character.name == name
            )
        )
    ).all()
    if rows:
        return rows[0]
    cards = (
        await session.scalars(
            select(Character).where(Character.novel_id == novel_id)
        )
    ).all()
    for card in cards:
        try:
            aliases = json.loads(card.aliases or "[]")
        except (TypeError, ValueError):
            aliases = []
        if name in aliases:
            return card
    return None


async def _first_chapters(session: AsyncSession, novel_id: str) -> dict[str, int]:
    """首次出场＝出场章最小阅读序（卷×1000+章）的章号；一次 GROUP BY 给全。"""
    from models.chapter import Chapter, ChapterCharacter

    rows = (
        await session.execute(
            select(
                ChapterCharacter.character_id,
                func.min(Volume.volume_no * 1000 + Chapter.chapter_no),
            )
            .join(Chapter, Chapter.id == ChapterCharacter.chapter_id)
            .join(Volume, Volume.id == Chapter.volume_id)
            .where(
                Chapter.project_id == novel_id,
                ChapterCharacter.character_id.isnot(None),
            )
            .group_by(ChapterCharacter.character_id)
        )
    ).all()
    return {cid: int(key) % 1000 for cid, key in rows if cid}


async def list_characters(session: AsyncSession, novel_id: str) -> dict:
    """列表聚合，一次给全（tasks 2.3）：含编号、类型、缺口、门禁摘要。"""
    from settings.character_model import card_gaps

    cards = (
        await session.scalars(
            select(Character).where(Character.novel_id == novel_id).order_by(Character.seq)
        )
    ).all()
    firsts = await _first_chapters(session, novel_id)
    items = []
    for ch in cards:
        view = card_to_dict(ch)
        view["gaps"] = card_gaps(_card_full(ch))
        view["first_chapter"] = firsts.get(ch.id)
        items.append(view)
    prot = next((c for c in cards if c.role == "主角"), None)
    gate_cards = [_card_full(c) for c in cards]
    gate = book_characters_gate(gate_cards)
    gate_row = await session.get(CharacterGate, novel_id)
    return {
        "count": len(items),
        "protagonist_id": prot.id if prot else None,
        "gate": {"ok": gate["ok"], "no_protagonist": gate["no_protagonist"]},
        "confirmed": gate_row is not None,
        "items": items,
    }


def _card_full(ch: Character) -> dict:
    return {
        "seq": ch.seq,
        "name": ch.name,
        "role": ch.role,
        "persona": ch.persona,
        "dossier": json.loads(ch.dossier or "{}"),
        "cog": json.loads(ch.cog or "{}"),
    }


async def create_character(
    session: AsyncSession, novel_id: str, name: str, role: str = "配角"
) -> Character:
    if role not in ROLES:
        raise Unprocessable("invalid_role", f"角色类型只能是 {'/'.join(ROLES)}")
    name = (name or "").strip()
    if not name:
        # 空名允许（作者可以从称呼写起），但 DB 的 UNIQUE(novel_id, name) 会对空串撞车
        # → 空名用占位（唯一 uuid 段），展示层把空名显示为「未命名」
        name = f"\u0000{uuid.uuid4().hex[:12]}"
    taken = (
        await session.scalars(
            select(Character).where(Character.novel_id == novel_id, Character.name == name)
        )
    ).first()
    if taken:
        raise Conflict("name_taken", f"已有角色叫「{name}」，换一个名字")
    novel = await session.get(Novel, novel_id)
    if novel is None:
        raise Unprocessable("not_found", "书不存在")
    novel.character_seq_high += 1
    ch = Character(novel_id=novel_id, seq=novel.character_seq_high, name=name, role=role)
    session.add(ch)
    await session.flush()
    if role == "主角":
        await _demote_other_protagonists(session, novel_id, keep_id=ch.id)
    await session.commit()
    await session.refresh(ch)
    return ch


async def patch_character(
    session: AsyncSession, novel_id: str, character_id: str,
    path: str, value: Any, base_rev: int,
) -> dict:
    """单格写入：条件 UPDATE（CAS）。返回新 rev。"""
    ch = await _load_card(session, novel_id, character_id)
    if not isinstance(base_rev, int) or base_rev != ch.rev:
        raise Conflict(
            "rev_conflict",
            "这一格已被其它改动更新，请刷新后重试",
            field=path, current=_read_field(ch, path), rev=ch.rev,
        )
    if path in _PATCH_ROOTS:
        if path == "name":
            new_name = str(value or "").strip()
            if new_name:
                taken = (
                    await session.scalars(
                        select(Character).where(
                            Character.novel_id == novel_id,
                            Character.name == new_name,
                            Character.id != character_id,
                        )
                    )
                ).first()
                if taken:
                    raise Conflict("name_taken", f"已有角色叫「{new_name}」，换一个名字")
            elif not str(ch.name or "").startswith("\u0000"):
                # 清空 = 回到未命名占位（create 同款哨兵）；直接写 "" 会让第二张
                # 空名卡撞 uq_char_novel_name → 500（review P2）
                value = f"\u0000{uuid.uuid4().hex[:12]}"
        if path == "role":
            if value not in ROLES:
                raise Unprocessable("invalid_role", f"角色类型只能是 {'/'.join(ROLES)}")
            await _promote_to_protagonist(session, novel_id, character_id, value, base_rev)
            await session.commit()
            await session.refresh(ch)
            return {"rev": ch.rev}
        col = getattr(Character, path)
        extra: dict = {}
        if path == "aliases":
            if not isinstance(value, list) or not all(isinstance(a, str) for a in value):
                raise Unprocessable("invalid_aliases", "别名需要是字符串列表")
            value = _json_dumps(value)
        stmt = (
            update(Character)
            .where(Character.id == character_id, Character.rev == base_rev)
            .values({col.name: value, "rev": Character.rev + 1, **extra})
        )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise Conflict(
                "rev_conflict", "这一格已被其它改动更新，请刷新后重试",
                field=path, current=_read_field(ch, path), rev=ch.rev,
            )
    elif path.startswith(("dossier.", "cog.")):
        bucket, key = path.split(".", 1)
        allowed = DOSSIER_KEYS if bucket == "dossier" else COG_KEYS
        if key not in allowed:
            raise Unprocessable("unknown_field", f"没有「{path}」这一格")
        current = json.loads(getattr(ch, bucket) or "{}")
        current[key] = str(value or "")
        stmt = (
            update(Character)
            .where(Character.id == character_id, Character.rev == base_rev)
            .values({bucket: _json_dumps(current), "rev": Character.rev + 1})
        )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise Conflict(
                "rev_conflict", "这一格已被其它改动更新，请刷新后重试",
                field=path, current=_read_field(ch, path), rev=ch.rev,
            )
    else:
        raise Unprocessable("unknown_field", f"没有「{path}」这一格")
    await session.commit()
    await session.refresh(ch)
    return {"rev": ch.rev}


def _read_field(ch: Character, path: str):
    if path in _PATCH_ROOTS:
        if path == "aliases":
            return json.loads(ch.aliases or "[]")
        return getattr(ch, path)
    bucket, key = path.split(".", 1)
    return json.loads(getattr(ch, bucket) or "{}").get(key)


async def _demote_other_protagonists(
    session: AsyncSession, novel_id: str, keep_id: str
) -> None:
    # 先降级 + 显式 flush——部分唯一索引下"先升后降"会在 unit-of-work 排序上撞索引
    await session.execute(
        update(Character)
        .where(
            Character.novel_id == novel_id,
            Character.role == "主角",
            Character.id != keep_id,
        )
        .values(role="配角")
    )
    await session.flush()


async def _promote_to_protagonist(
    session: AsyncSession, novel_id: str, character_id: str, new_role: str, base_rev: int
) -> None:
    if new_role == "主角":
        await _demote_other_protagonists(session, novel_id, keep_id=character_id)
        stmt = (
            update(Character)
            .where(Character.id == character_id, Character.rev == base_rev)
            .values(role="主角", rev=Character.rev + 1)
        )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise Conflict("rev_conflict", "这一格已被其它改动更新，请刷新后重试", field="role")
        # 门禁存档作废（内容有变）
        await session.execute(
            delete(CharacterGate).where(CharacterGate.novel_id == novel_id)
        )
    else:
        stmt = (
            update(Character)
            .where(Character.id == character_id, Character.rev == base_rev)
            .values(role=new_role, rev=Character.rev + 1)
        )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise Conflict("rev_conflict", "这一格已被其它改动更新，请刷新后重试", field="role")
        await session.execute(
            delete(CharacterGate).where(CharacterGate.novel_id == novel_id)
        )


async def _snapshot_card(session: AsyncSession, ch: Character) -> dict:
    view = card_to_dict(ch)
    rels = (
        await session.scalars(
            select(CharacterRelation).where(
                (CharacterRelation.owner_id == ch.id)
                | (CharacterRelation.other_id == ch.id)
            )
        )
    ).all()
    view["relations"] = [rel_to_dict(r) for r in rels]
    return view


async def delete_character(
    session: AsyncSession, novel_id: str, character_id: str
) -> dict:
    ch = await _load_card(session, novel_id, character_id)
    before = await _snapshot_card(session, ch)
    token = uuid.uuid4().hex
    await session.execute(
        delete(CharacterRelation).where(
            (CharacterRelation.owner_id == character_id)
            | (CharacterRelation.other_id == character_id)
        )
    )
    await session.delete(ch)
    await session.execute(
        delete(CharacterGate).where(CharacterGate.novel_id == novel_id)
    )
    session.add(CharacterOp(
        novel_id=novel_id, kind="delete", before=_json_dumps(before),
        undo_token=token,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=UNDO_TTL_SECONDS),
    ))
    await session.commit()
    return {
        "receipt": f"已删除《{ch.name}》",
        "undo": {"op_id": token},
    }


async def merge_character(
    session: AsyncSession, novel_id: str, source_id: str, target_id: str
) -> dict:
    if source_id == target_id:
        raise Unprocessable("same_card", "不能把一张卡并进它自己")
    src = await _load_card(session, novel_id, source_id)
    tgt = await _load_card(session, novel_id, target_id)
    before_src = await _snapshot_card(session, src)
    # 目标卡的既有关系必须进前像：undo 会清掉触及目标卡的全部关系再重建，
    # 不快照它们就会被一并抹掉（review P1）
    before_tgt = card_to_dict(tgt)
    before_tgt["relations"] = [
        rel_to_dict(r)
        for r in await session.scalars(
            select(CharacterRelation).where(
                (CharacterRelation.owner_id == target_id)
                | (CharacterRelation.other_id == target_id)
            )
        )
    ]
    filled_count = 0

    # 空格用来源卡补齐；目标已有的字不动
    if not tgt.persona.strip() and src.persona.strip():
        tgt.persona = src.persona
        filled_count += 1
    tgt_dossier = json.loads(tgt.dossier or "{}")
    src_dossier = json.loads(src.dossier or "{}")
    for key in DOSSIER_KEYS:
        if not str(tgt_dossier.get(key) or "").strip() and str(src_dossier.get(key) or "").strip():
            tgt_dossier[key] = src_dossier[key]
            filled_count += 1
    tgt.dossier = _json_dumps(tgt_dossier)
    tgt_cog = json.loads(tgt.cog or "{}")
    src_cog = json.loads(src.cog or "{}")
    for key in COG_KEYS:
        if not str(tgt_cog.get(key) or "").strip() and str(src_cog.get(key) or "").strip():
            tgt_cog[key] = src_cog[key]
            filled_count += 1
    tgt.cog = _json_dumps(tgt_cog)

    # 名字并入别名（去重；空名占位不入别名）
    aliases = json.loads(tgt.aliases or "[]")
    for candidate in [src.name, *json.loads(src.aliases or "[]")]:
        if candidate and not candidate.startswith("\u0000") and candidate not in aliases:
            aliases.append(candidate)
    tgt.aliases = _json_dumps(aliases)

    # 关系改指：自己写的并进目标；别人写给他的改指目标
    moved = 0
    dropped = 0
    rels = (
        await session.scalars(
            select(CharacterRelation).where(
                (CharacterRelation.owner_id == source_id)
                | (CharacterRelation.other_id == source_id)
            )
        )
    ).all()
    # 先删"改指后会撞唯一键"的现存行：目标卡与 X 已有一条，而 source 与 X 也有一条
    # → 保留目标卡那条，source 的这条进前像（撤销时随源卡关系一起回来）
    for rel in list(rels):
        if rel.owner_id == source_id:
            clash = (
                await session.scalars(
                    select(CharacterRelation).where(
                        CharacterRelation.owner_id == target_id,
                        CharacterRelation.other_id == rel.other_id,
                        CharacterRelation.id != rel.id,
                    )
                )
            ).first()
            if clash is not None:
                await session.delete(rel)
                dropped += 1
                rels.remove(rel)
        elif rel.other_id == source_id:
            clash = (
                await session.scalars(
                    select(CharacterRelation).where(
                        CharacterRelation.other_id == target_id,
                        CharacterRelation.owner_id == rel.owner_id,
                        CharacterRelation.id != rel.id,
                    )
                )
            ).first()
            if clash is not None:
                await session.delete(rel)
                dropped += 1
                rels.remove(rel)
    for rel in rels:
        if rel.owner_id == source_id:
            rel.owner_id = target_id
            moved += 1
        elif rel.other_id == source_id:
            rel.other_id = target_id
            moved += 1
    # 自环消解 + 同对端兜底去重（跨批引入的重复）
    seen: dict[tuple[str, str], CharacterRelation] = {}
    for rel in (
        await session.scalars(
            select(CharacterRelation).where(
                (CharacterRelation.owner_id == target_id)
                | (CharacterRelation.other_id == target_id)
            )
        )
    ).all():
        if rel.owner_id == rel.other_id:
            await session.delete(rel)
            dropped += 1
            continue
        key_pair = (rel.owner_id, rel.other_id)
        if key_pair in seen:
            kept = seen[key_pair]
            if not kept.stance and rel.stance:
                kept.stance = rel.stance
            if not kept.note and rel.note:
                kept.note = rel.note
            await session.delete(rel)
            dropped += 1
            continue
        seen[key_pair] = rel
    tgt.rev += 1

    # 主角身份随内容走
    was_protagonist = src.role == "主角"
    await session.delete(src)
    await session.execute(
        delete(CharacterGate).where(CharacterGate.novel_id == novel_id)
    )
    if was_protagonist:
        await _demote_other_protagonists(session, novel_id, keep_id=tgt.id)
        tgt.role = "主角"

    token = uuid.uuid4().hex
    session.add(CharacterOp(
        novel_id=novel_id, kind="merge",
        before=_json_dumps({"source": before_src, "target": before_tgt}),
        undo_token=token,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=UNDO_TTL_SECONDS),
    ))
    await session.commit()
    await session.refresh(tgt)
    return {
        "receipt": (
            f"已把《{src.name}》并进《{tgt.name}》——补 {filled_count} 处空格、"
            f"关系归并 {moved} 段（去重 {dropped} 段）"
        ),
        "undo": {"op_id": token},
        "target": card_to_dict(tgt),
    }


async def undo_op(session: AsyncSession, novel_id: str, token: str) -> dict:
    op = (
        await session.scalars(
            select(CharacterOp).where(
                CharacterOp.novel_id == novel_id, CharacterOp.undo_token == token
            )
        )
    ).first()
    if op is None:
        raise Unprocessable("not_found", "没有这次操作的撤销记录")
    if op.undone_at is not None:
        raise Conflict("already_undone", "这次操作已经撤销过了")
    if op.expires_at < datetime.now(UTC).replace(tzinfo=None):
        raise Conflict("undo_expired", "撤销窗口已过，无法撤回")
    before = json.loads(op.before or "{}")

    if op.kind == "delete":
        await _restore_card(session, before)
        for rel in before.get("relations") or []:
            session.add(CharacterRelation(
                novel_id=novel_id, owner_id=rel["owner_id"], other_id=rel["other_id"],
                rel_type=rel["rel_type"], stance=rel["stance"], note=rel["note"],
                ch_ref=rel["ch_ref"],
            ))
    elif op.kind == "merge":
        # 撤销 = 重建源卡 + 恢复目标卡改前的样子 + 关系改回 + 恢复被去重删除的行
        await _restore_card(session, before.get("source") or {})
        tgt_before = before.get("target") or {}
        tgt = await _load_card(session, novel_id, tgt_before["id"])
        _overwrite_from_snapshot(tgt, tgt_before)
        # 现存触及目标卡的关系全部清掉，按前像重建——源卡的与目标卡自己的都要
        # （目标卡自己的关系在合并时虽未被移动，但 undo 的清理是全量清除）
        await session.execute(
            delete(CharacterRelation).where(
                (CharacterRelation.owner_id == tgt_before["id"])
                | (CharacterRelation.other_id == tgt_before["id"])
            )
        )
        for side in ("source", "target"):
            for rel in (before.get(side) or {}).get("relations") or []:
                session.add(CharacterRelation(
                    novel_id=novel_id, owner_id=rel["owner_id"], other_id=rel["other_id"],
                    rel_type=rel["rel_type"], stance=rel["stance"], note=rel["note"],
                    ch_ref=rel["ch_ref"],
                ))
    elif op.kind == "relation_delete":
        for rel in before.get("relations") or []:
            session.add(CharacterRelation(
                novel_id=novel_id, owner_id=rel["owner_id"], other_id=rel["other_id"],
                rel_type=rel["rel_type"], stance=rel["stance"], note=rel["note"],
                ch_ref=rel["ch_ref"],
            ))

    # 撤销也作废门禁存档（内容回到确认前的样子）
    await session.execute(
        delete(CharacterGate).where(CharacterGate.novel_id == novel_id)
    )
    op.undone_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    return {"ok": True, "receipt": "已撤销，恢复到操作前"}


def _overwrite_from_snapshot(ch: Character, snap: dict) -> None:
    ch.name = snap.get("name", ch.name)
    ch.aliases = _json_dumps(snap.get("aliases", json.loads(ch.aliases or "[]")))
    ch.role = snap.get("role", ch.role)
    ch.persona = snap.get("persona", ch.persona)
    ch.dossier = _json_dumps(snap.get("dossier", json.loads(ch.dossier or "{}")))
    ch.cog = _json_dumps(snap.get("cog", json.loads(ch.cog or "{}")))
    ch.seq = snap.get("seq", ch.seq)


async def _restore_card(session: AsyncSession, snap: dict) -> Character:
    existing = await session.get(Character, snap.get("id") or "")
    if existing is not None:
        _overwrite_from_snapshot(existing, snap)
        return existing
    ch = Character(
        id=snap["id"], novel_id=snap["novel_id"], seq=snap["seq"],
        name=snap.get("name", ""), aliases=_json_dumps(snap.get("aliases", [])),
        role=snap.get("role", "配角"), persona=snap.get("persona", ""),
        dossier=_json_dumps(snap.get("dossier", {})),
        cog=_json_dumps(snap.get("cog", {})),
        legacy=_json_dumps(snap.get("legacy", {})),
    )
    session.add(ch)
    await session.flush()
    # 计数器不能倒退（防复用）
    novel = await session.get(Novel, snap["novel_id"])
    if novel is not None and snap.get("seq", 0) > novel.character_seq_high:
        novel.character_seq_high = snap["seq"]
    return ch


async def upsert_relation(
    session: AsyncSession, novel_id: str, owner_id: str, other_id: str,
    rel_type: str, stance: str, note: str, ch_ref: str = "",
) -> CharacterRelation:
    if owner_id == other_id:
        raise Unprocessable("self_relation", "不能把关系记到自己头上")
    if rel_type not in RELATION_TYPES:
        raise Unprocessable("invalid_rel_type", f"关系类型只能是 {'/'.join(RELATION_TYPES)}")
    await _load_card(session, novel_id, owner_id)
    await _load_card(session, novel_id, other_id)
    rel = (
        await session.scalars(
            select(CharacterRelation).where(
                CharacterRelation.owner_id == owner_id,
                CharacterRelation.other_id == other_id,
            )
        )
    ).first()
    if rel is None:
        rel = CharacterRelation(
            novel_id=novel_id, owner_id=owner_id, other_id=other_id,
            rel_type=rel_type, stance=stance, note=note, ch_ref=ch_ref,
        )
        session.add(rel)
    else:
        rel.rel_type = rel_type
        rel.stance = stance
        rel.note = note
        rel.rev += 1
    # 关系变更 bump 双方卡的 rev（前端单格 PATCH 的 rev 依据）
    await session.execute(
        update(Character).where(Character.id == owner_id).values(rev=Character.rev + 1)
    )
    await session.execute(
        update(Character).where(Character.id == other_id).values(rev=Character.rev + 1)
    )
    await session.commit()
    await session.refresh(rel)
    return rel


async def delete_relation(
    session: AsyncSession, novel_id: str, owner_id: str, other_id: str
) -> dict:
    rel = (
        await session.scalars(
            select(CharacterRelation).where(
                CharacterRelation.owner_id == owner_id,
                CharacterRelation.other_id == other_id,
            )
        )
    ).first()
    if rel is None:
        raise Unprocessable("not_found", "没有这段关系记录")
    snap = rel_to_dict(rel)
    before = {"relations": [snap]}
    token = uuid.uuid4().hex
    await session.delete(rel)
    await session.execute(
        update(Character).where(Character.id == owner_id).values(rev=Character.rev + 1)
    )
    session.add(CharacterOp(
        novel_id=novel_id, kind="relation_delete", before=_json_dumps(before),
        undo_token=token,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=UNDO_TTL_SECONDS),
    ))
    await session.commit()
    return {"receipt": "已删掉这段关系", "undo": {"op_id": token}}


async def gate_status(session: AsyncSession, novel_id: str) -> dict | None:
    """第三态派生：确认存档 vs 当前内容。stale = 指纹或主角 id 不一致。"""
    gate = await session.get(CharacterGate, novel_id)
    if gate is None:
        return None
    cards = (
        await session.scalars(
            select(Character).where(Character.novel_id == novel_id)
        )
    ).all()
    current_fp = gate_fingerprint([_card_full(c) for c in cards])
    prot = next((c for c in cards if c.role == "主角"), None)
    stale = (
        gate.fingerprint != current_fp
        or gate.protagonist_id != (prot.id if prot else None)
    )
    return {
        "confirmed": True,
        "stale": stale,
        "confirmed_at": gate.confirmed_at.isoformat() if gate.confirmed_at else None,
    }


async def confirm_characters(session: AsyncSession, novel_id: str, first: bool) -> dict:
    """确认门禁（两档）。通过则落 character_gate（确认存档）。"""
    cards = (
        await session.scalars(
            select(Character).where(Character.novel_id == novel_id)
        )
    ).all()
    gate = book_characters_gate([_card_full(c) for c in cards], first=first)
    if gate["no_protagonist"]:
        raise Unprocessable(
            "no_protagonist", "先立主角：在卡头把谁设为「主角」"
        )
    if not gate["ok"]:
        first_miss = gate["missing"][0]
        more = f"（共 {len(gate['missing'])} 张卡）" if len(gate["missing"]) > 1 else ""
        raise Unprocessable(
            "incomplete",
            f"还差：{first_miss['name']}缺 {'、'.join(first_miss['fields'])}{more}",
            missing=gate["missing"],
        )
    prot = next(c for c in cards if c.role == "主角")
    fp = gate_fingerprint([_card_full(c) for c in cards])
    row = await session.get(CharacterGate, novel_id)
    if row is None:
        session.add(CharacterGate(
            novel_id=novel_id, protagonist_id=prot.id, fingerprint=fp,
        ))
    else:
        row.protagonist_id = prot.id
        row.fingerprint = fp
        row.confirmed_at = datetime.now(UTC).replace(tzinfo=None)
        row.rev += 1
    await session.commit()
    return {"ok": True, "type": "characters", "confirmed": True}


_ = attributes  # 保持 import（sqlalchemy.attributes 供后续审计扩展）
