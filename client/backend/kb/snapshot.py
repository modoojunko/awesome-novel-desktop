"""启用库落设定（c-kb-snapshot 批3）。

书绑定库（kb_book_bindings）＋基线快照落书内 style/world KV：
- 快照只取基线条目（when_json 为空＝scope base）；场景条目不进快照、不进同步
- 同题材同概念互斥：一个书的一个 (genre, concept) 只有一个启用库
- 落设定「本书改过保留」：role 只空时写；列表/段落键追加去重
- 同步差异：库当前基线 vs 快照成员 → added/removed 计数；显式 sync 重新快照＋重落
- 解绑只删绑定行，书内已落设定保留（快照型消费＝独立文本，整体方案 §删库不惊动）
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from filesystem.storage import get_storage
from models.kb import KbBookBinding, KbEntry, KbLibrary, KbLibraryItem

# 文风 payload 槽位 → style 白名单键（STYLE_WRITE_KEYS 消费端真实键）；pov 无消费键，跳过
_STYLE_SLOT_TARGET: dict[str, str] = {
    "role": "role",
    "sample": "style_samples",
}
# 文笔 payload 槽位 → style 白名单键；banned_word/tic 走专用归一键
_CRAFT_SLOT_TARGET: dict[str, str] = {
    "rule": "rules",
    "craft": "craft",
    "banned_word": "banned_words",
    "tic": "tic_patterns",
}
# 世界 payload part → world V2 键（constraint 单数→复数键；no_power 不开放）
_WORLD_PART_TARGET: dict[str, str] = {
    "stage": "stage",
    "power": "power",
    "cost": "cost",
    "history": "history",
    "factions": "factions",
    "constraint": "constraints",
    "extra": "extra",
}
_PARA_KEYS = ("stage", "power", "cost")
_LIST_KEYS = ("history", "factions", "constraints", "extra")


def _when_of(e: KbEntry) -> dict:
    try:
        w = json.loads(e.when_json or "{}")
    except ValueError:
        w = {}
    return w if isinstance(w, dict) else {}


async def library_base_entries(db: AsyncSession, lib: KbLibrary) -> list[KbEntry]:
    """库的基线条目：auto 库按 (user, genre, concept) 扫描；手动圈选库走 items join。

    基线＝when_json 为空（无 scene/emotion/chapter_pos）；场景条目不进快照。
    """
    if lib.rule_kind == "auto":
        rows = (
            (
                await db.execute(
                    select(KbEntry)
                    .where(
                        KbEntry.user_id == lib.user_id,
                        KbEntry.genre == lib.genre,
                        KbEntry.concept == lib.concept,
                        KbEntry.status == "active",
                    )
                    .order_by(KbEntry.created_at, KbEntry.id)
                )
            )
            .scalars()
            .all()
        )
    else:
        item_ids = (
            (
                await db.execute(
                    select(KbLibraryItem.entry_id).where(KbLibraryItem.library_id == lib.id).order_by(KbLibraryItem.sort)
                )
            )
            .scalars()
            .all()
        )
        rows = (
            list(
                (
                    await db.execute(
                        select(KbEntry)
                        .where(KbEntry.id.in_(item_ids), KbEntry.status == "active")
                        .order_by(KbEntry.created_at, KbEntry.id)
                    )
                )
                .scalars()
                .all()
            )
            if item_ids
            else []
        )
    return [e for e in rows if not _when_of(e)]


def _payload_of(e: KbEntry) -> dict:
    try:
        p = json.loads(e.payload_json or "{}")
    except ValueError:
        p = {}
    return p if isinstance(p, dict) else {}


def build_members(entries: list[KbEntry]) -> list[dict[str, Any]]:
    """基线条目 → 快照成员（含落点 target 与落库文本，供来源行展示＋同步 diff）。

    有落点才进快照：文风 pov（无消费键）、角色/手法（无书级基线落点）跳过。
    """
    members: list[dict[str, Any]] = []
    for e in entries:
        payload = _payload_of(e)
        slot = str(payload.get("slot") or "")
        part = str(payload.get("part") or "")
        target = ""
        text = ""
        if e.concept == "文风":
            target = _STYLE_SLOT_TARGET.get(slot, "")
            text = str(payload.get("role") or "") if slot == "role" else str(payload.get("sample") or "")
        elif e.concept == "文笔":
            target = _CRAFT_SLOT_TARGET.get(slot, "")
            text = str(payload.get("rule") or payload.get("craft") or payload.get("banned") or payload.get("tic_pattern") or "")
        elif e.concept == "世界设定":
            target = _WORLD_PART_TARGET.get(part, "")
            text = str(payload.get("content") or "")
        if not target or not text.strip():
            continue
        members.append(
            {
                "entry_id": e.id,
                "title": e.title,
                "concept": e.concept,
                "slot": slot,
                "part": part,
                "target": target,
                "text": text.strip(),
            }
        )
    return members


def _snapshot_members(binding: KbBookBinding) -> list[dict[str, Any]]:
    try:
        snap = json.loads(binding.snapshot_json or "{}")
    except ValueError:
        snap = {}
    members = snap.get("members")
    return members if isinstance(members, list) else []


async def apply_members(root_path: str, members: list[dict[str, Any]]) -> dict[str, int]:
    """快照成员落书内 KV（style/world）。返回逐键落库计数（来源行「N 条」用）。"""
    landed: dict[str, int] = {}

    # ── 文风/文笔 → style KV ──
    style_members = [m for m in members if m["concept"] in ("文风", "文笔")]
    if style_members:
        from settings.style_model import normalize_style, put_style

        path = "settings/writing-style.yaml"
        raw = await get_storage().read_yaml(root_path, path) or {}
        cur = normalize_style(raw)
        body: dict[str, Any] = {}

        # 单值键：role 只空时写（书级恒定，本书已写过不覆盖）
        roles = [m["text"] for m in style_members if m["target"] == "role"]
        if roles and not str(cur.get("role") or "").strip():
            body["role"] = roles[0]
            landed["style.role"] = 1

        # 字符串列表键：rules / craft / style_samples
        for key in ("rules", "craft", "style_samples"):
            texts = [m["text"] for m in style_members if m["target"] == key]
            if not texts:
                continue
            merged_list = list(cur.get(key) or [])
            added = 0
            for t in texts:
                if t not in merged_list:
                    merged_list.append(t)
                    added += 1
            if added:
                body[key] = merged_list
                landed[f"style.{key}"] = added

        # 禁用词（词表归一专用形状）
        words = [m["text"] for m in style_members if m["target"] == "banned_words"]
        if words:
            merged_list = list(cur.get("banned_words") or [])
            added = 0
            for w in words:
                if w not in merged_list:
                    merged_list.append(w)
                    added += 1
            if added:
                body["banned_words"] = merged_list
                landed["style.banned_words"] = added

        # 句式规则（dict 列表，按 pattern 去重）
        tics = [m for m in style_members if m["target"] == "tic_patterns"]
        if tics:
            merged_list = list(cur.get("tic_patterns") or [])
            seen = {str(t.get("pattern") or "") for t in merged_list}
            added = 0
            for m in tics:
                if m["text"] and m["text"] not in seen:
                    merged_list.append({"pattern": m["text"], "severity": "medium", "description": m.get("title") or ""})
                    seen.add(m["text"])
                    added += 1
            if added:
                body["tic_patterns"] = merged_list
                landed["style.tic_patterns"] = added

        if body:
            await get_storage().write_yaml(root_path, path, put_style(raw, body))

    # ── 世界设定 → world KV ──
    world_members = [m for m in members if m["concept"] == "世界设定"]
    if world_members:
        from settings.world_model import normalize_world, put_world_merged

        path = "settings/world-setting.yaml"
        raw = await get_storage().read_yaml(root_path, path) or {}
        cur = normalize_world(raw)
        body_w: dict[str, Any] = {}

        for key in _LIST_KEYS:
            texts = [m["text"] for m in world_members if m["target"] == key]
            if not texts:
                continue
            merged_list = list(cur.get(key) or [])
            added = 0
            for t in texts:
                if key == "factions":
                    names = {str(f.get("name") or "") for f in merged_list}
                    if t in names:
                        continue
                    merged_list.append({"name": t, "note": ""})
                    added += 1
                else:
                    values = {str(x.get("value") or "") for x in merged_list}
                    if t in values:
                        continue
                    merged_list.append({"key": t[:12], "value": t})
                    added += 1
            if added:
                body_w[key] = merged_list
                landed[f"world.{key}"] = added

        for key in _PARA_KEYS:
            texts = [m["text"] for m in world_members if m["target"] == key]
            if not texts:
                continue
            exist_text = str(cur.get(key) or "").strip()
            added = 0
            for t in texts:
                if t and t not in exist_text:
                    exist_text = f"{exist_text}\n{t}" if exist_text else t
                    added += 1
            if added:
                body_w[key] = exist_text
                landed[f"world.{key}"] = added

        if body_w:
            await get_storage().write_yaml(root_path, path, put_world_merged(raw, body_w))

    return landed


async def _same_cell_binding_ids(db: AsyncSession, novel_id: str, lib: KbLibrary, keep_id: str) -> list[str]:
    """同书同 (genre, concept) 的其他启用绑定 id（互斥清理对象）。"""
    rows = (
        (
            await db.execute(
                select(KbBookBinding).where(KbBookBinding.novel_id == novel_id, KbBookBinding.enabled.is_(True))
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    libs = (
        (
            await db.execute(
                select(KbLibrary).where(
                    KbLibrary.id.in_([b.library_id for b in rows]),
                    KbLibrary.genre == lib.genre,
                    KbLibrary.concept == lib.concept,
                )
            )
        )
        .scalars()
        .all()
    )
    return [b.id for b in rows if b.library_id in {o.id for o in libs} and b.library_id != keep_id]


async def bind_library(
    db: AsyncSession,
    *,
    user_id: str,
    novel_id: str,
    root_path: str,
    library_id: str,
) -> tuple[KbBookBinding | None, dict[str, Any], str]:
    """启用库：互斥同格、快照基线、落设定。返回 (binding, info, error)。"""
    lib = (
        await db.execute(select(KbLibrary).where(KbLibrary.id == library_id, KbLibrary.user_id == user_id))
    ).scalar_one_or_none()
    if not lib:
        return None, {}, "库不存在"

    kill_ids = await _same_cell_binding_ids(db, novel_id, lib, library_id)
    if kill_ids:
        await db.execute(delete(KbBookBinding).where(KbBookBinding.id.in_(kill_ids)))

    entries = await library_base_entries(db, lib)
    members = build_members(entries)
    landed = await apply_members(root_path, members)
    snapshot = {
        "genre": lib.genre,
        "concept": lib.concept,
        "library_name": lib.name,
        "members": members,
    }
    binding = (
        await db.execute(
            select(KbBookBinding).where(KbBookBinding.novel_id == novel_id, KbBookBinding.library_id == library_id)
        )
    ).scalar_one_or_none()
    if binding:
        binding.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
        binding.enabled = True
    else:
        binding = KbBookBinding(
            novel_id=novel_id,
            library_id=library_id,
            enabled=True,
            snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        )
        db.add(binding)
    await db.commit()
    info = {
        "library_id": library_id,
        "genre": lib.genre,
        "concept": lib.concept,
        "library_name": lib.name,
        "member_count": len(members),
        "landed": landed,
        "replaced_bindings": len(kill_ids),
    }
    return binding, info, ""


async def binding_status(db: AsyncSession, binding: KbBookBinding) -> dict[str, Any]:
    """绑定状态：同步差异（库更新 N 条 / 来源库已移除）＋场景条目计数。"""
    lib = (
        await db.execute(select(KbLibrary).where(KbLibrary.id == binding.library_id))
    ).scalar_one_or_none()
    snap_ids = [m.get("entry_id") for m in _snapshot_members(binding)]
    if not lib:
        return {"library_missing": True, "added": 0, "removed": 0, "member_count": len(snap_ids), "scene_count": 0}
    cur = await library_base_entries(db, lib)
    cur_ids = [e.id for e in cur]
    added = len([i for i in cur_ids if i not in snap_ids])
    removed = len([i for i in snap_ids if i not in cur_ids])
    scene_n = 0
    if lib.rule_kind == "auto":
        rows = (
            (
                await db.execute(
                    select(KbEntry).where(
                        KbEntry.user_id == lib.user_id,
                        KbEntry.genre == lib.genre,
                        KbEntry.concept == lib.concept,
                        KbEntry.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        scene_n = sum(1 for e in rows if _when_of(e))
    return {
        "library_missing": False,
        "added": added,
        "removed": removed,
        "member_count": len(snap_ids),
        "scene_count": scene_n,
    }


async def sync_binding(db: AsyncSession, binding: KbBookBinding, root_path: str) -> dict[str, Any]:
    """显式同步：重新快照＋重落设定（本书改过保留语义不变）。"""
    lib = (
        await db.execute(select(KbLibrary).where(KbLibrary.id == binding.library_id))
    ).scalar_one_or_none()
    if not lib:
        return {"error": "来源库已移除"}
    entries = await library_base_entries(db, lib)
    members = build_members(entries)
    landed = await apply_members(root_path, members)
    binding.snapshot_json = json.dumps(
        {"genre": lib.genre, "concept": lib.concept, "library_name": lib.name, "members": members},
        ensure_ascii=False,
    )
    binding.enabled = True
    await db.commit()
    return {"member_count": len(members), "landed": landed}


async def unbind(db: AsyncSession, *, novel_id: str, binding_id: str) -> bool:
    """解除绑定：只删绑定行，书内已落设定保留。"""
    res = await db.execute(
        delete(KbBookBinding).where(KbBookBinding.id == binding_id, KbBookBinding.novel_id == novel_id)
    )
    await db.commit()
    return bool(res.rowcount)


async def list_bindings(db: AsyncSession, *, novel_id: str) -> list[dict[str, Any]]:
    """书的绑定列表＋来源行＋差异状态。"""
    rows = (
        (
            await db.execute(
                select(KbBookBinding).where(KbBookBinding.novel_id == novel_id).order_by(KbBookBinding.id)
            )
        )
        .scalars()
        .all()
    )
    out: list[dict[str, Any]] = []
    for b in rows:
        snap = json.loads(b.snapshot_json or "{}") if b.snapshot_json else {}
        status = await binding_status(db, b)
        out.append(
            {
                "id": b.id,
                "novel_id": b.novel_id,
                "library_id": b.library_id,
                "enabled": b.enabled,
                "genre": snap.get("genre", ""),
                "concept": snap.get("concept", ""),
                "library_name": snap.get("library_name", ""),
                "member_count": status.get("member_count", 0),
                "scene_count": status.get("scene_count", 0),
                "added": status.get("added", 0),
                "removed": status.get("removed", 0),
                "library_missing": status.get("library_missing", False),
                "synced_at": b.synced_at.isoformat() if b.synced_at else "",
            }
        )
    return out
