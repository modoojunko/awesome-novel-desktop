"""写作知识库 API 端点——挂 /api/kb 前缀。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user
from db import get_db
from kb import service as knowledge_service
from kb.concepts import CONCEPTS, THEMES
from kb.migrate_library import ensure_legacy_migrated
from kb.service import (
    create_entry,
    delete_entry,
    genre_counts,
    get_entry,
    list_entries,
    list_libraries,
    update_entry,
)
from library.service import ensure_genre_backfill
from models.kb import KbBookBinding, KbBookEntry, KbEntry, KbPref
from novels.service import get_novel

router = APIRouter(prefix="/api/kb", tags=["kb"])


def _user(dep: dict) -> str:
    return dep["id"]


def _entry_dict(e: KbEntry, *, has_avatar: bool = False) -> dict[str, Any]:
    """条目 API 形状（用户条目与基线条目 MergedEntry 共用）。

    基线层来源标签「官方精选」随层派生：src_kind="baseline" 只出现在响应里，
    永不落 kb_entries（knowledge-base delta 明文）。layer/official_update 供 B6
    前端只读操作面与「官方有新版」提示使用。
    """
    from kb.merged import has_official_update

    def _iso(v):
        return v.isoformat() if v is not None else ""

    layer = getattr(e, "layer", "user")
    return {
        "id": e.id,
        "genre": e.genre,
        "concept": e.concept,
        "concept_id": e.concept_id,
        "title": e.title,
        "instruction": e.instruction,
        "payload": json.loads(e.payload_json),
        "example": e.example,
        "negative_example": e.negative_example,
        "when": json.loads(e.when_json),
        "evidence": e.evidence,
        "rev": e.rev,
        "status": e.status,
        "src_kind": e.src_kind,
        "src_novel_name": e.src_novel_name,
        "created_at": _iso(e.created_at),
        "updated_at": _iso(e.updated_at),
        "layer": layer,
        "src_key": getattr(e, "src_key", ""),
        "overlaid": bool(getattr(e, "overlaid", False)),
        "hidden": bool(getattr(e, "hidden", False)),
        "official_update": has_official_update(e) if layer == "baseline" else False,
        # 角色设定条目与角色库同源（kb_entries）：有字节出图、无字节前端出姓氏占位
        "has_avatar": bool(has_avatar) and e.concept == "角色设定",
    }


# ─── 官方精选同步状态（c-kb-baseline）：未就绪可重试 ───────


@router.get("/baseline/status")
async def baseline_status_api(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """基线层就绪状态（设备级；不要求登录态才有数据，这里只是展示口）。

    `last_sync` 透出最近一次同步摘要（accepted/skipped/carried/promoted）：
    skipped>0 表示包里有本端读不懂的条目（已沿用旧层原文，≠下架），便于发现两端口径漂移。
    """
    import json as _json

    from kb.baseline import LAST_SYNC_KEY, VERSION_KEY
    from models.app_meta import AppMeta
    from models.kb import KbBaselineEntry

    meta = await db.get(AppMeta, VERSION_KEY)
    version = int(meta.value) if meta and str(meta.value).isdigit() else 0
    n = (
        await db.execute(select(func.count(KbBaselineEntry.entry_id)))
    ).scalar_one()
    last = await db.get(AppMeta, LAST_SYNC_KEY)
    try:
        last_sync = _json.loads(last.value) if last and last.value else {}
    except ValueError:
        last_sync = {}
    return {
        "ok": True,
        "data": {"version": version, "entries": int(n or 0), "last_sync": last_sync},
    }


@router.post("/baseline/sync")
async def baseline_sync_api(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动重试同步（启动补偿失败后的重试面；幂等，失败保旧层）。"""
    from kb.baseline import sync_baseline

    result = await sync_baseline(db)
    return {"ok": True, "data": result}


# ─── 题材栏 ──────────────────────────────────────────────

@router.get("/genres")
async def get_genres(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    # 题材回填挂点（c-library-genre-gate 跟进）：本端点与条目列表并行发起，计数
    # 若先算会漏掉刚回填的条目——这里同挂一次，保证首屏计数与列表同口径（幂等自熄）
    await ensure_genre_backfill(db, uid)
    counts = await genre_counts(db, user_id=uid)
    items = []
    for t in THEMES:
        items.append({"name": t, "count": counts.get(t, 0)})
    if "" in counts:
        items.append({"name": "跨题材通用", "count": counts[""], "key": ""})
    return {"ok": True, "data": items}


# ─── 条目列表 ─────────────────────────────────────────────

@router.get("/entries")
async def list_entries_api(
    genre: str = "",
    concept: str = "",
    src: str = "",
    q: str = "",
    cursor: str = "",
    limit: int = 30,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    # 老版角色库存量一次性迁移挂点（c-kb-library-once-migration）：升级账号首次
    # 触达知识库读面即整账号搬入；幂等自熄，失败降级不阻断（详见 ensure 文档）
    await ensure_legacy_migrated(db, user_id=uid)
    # 题材回填挂点（c-library-genre-gate）：来源可解的空题材条目补题材，幂等自熄
    await ensure_genre_backfill(db, uid)
    entries, next_cursor = await list_entries(
        db, user_id=uid, genre=genre, concept=concept,
        src=src, q=q, cursor=cursor, limit=limit,
    )
    from library.service import avatar_presence

    presence = await avatar_presence(db, entries)
    return {
        "ok": True,
        "data": {
            "entries": [
                _entry_dict(e, has_avatar=presence.get(e.id, False)) for e in entries
            ],
            "next_cursor": next_cursor,
        },
    }


# ─── 条目详情 ─────────────────────────────────────────────

@router.get("/entries/{entry_id}")
async def get_entry_api(
    entry_id: str,
    include_merged: bool = False,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    e = await get_entry(db, user_id=uid, entry_id=entry_id, include_merged=include_merged)
    if not e:
        # 基线层条目：代理 id 落 kb_baseline_entries（merged 域回读，含副本/hide 判定）
        from kb.merged import get_merged_entry

        base = await get_merged_entry(db, user_id=uid, entry_id=entry_id)
        if not base:
            raise HTTPException(404, "Entry not found")
        return {"ok": True, "data": _entry_dict(base)}
    from library.service import avatar_presence

    presence = await avatar_presence(db, [e])
    data = _entry_dict(e, has_avatar=presence.get(e.id, False))
    if e.status == "merged":
        # c-kb-organize 追溯：合并指向＋保留条目摘要
        from models.kb import KbEntryMerge

        m = (
            await db.execute(select(KbEntryMerge).where(KbEntryMerge.merged_id == e.id))
        ).scalar_one_or_none()
        surv = await db.get(KbEntry, m.surviving_id) if m else None
        data["merged_into"] = (
            {"surviving_id": m.surviving_id, "title": surv.title if surv else ""}
            if m and surv
            else None
        )
    return {"ok": True, "data": data}


# ─── 手录 ─────────────────────────────────────────────────

class CreateEntryRequest(BaseModel):
    genre: str = ""
    concept: str = ""
    concept_id: str = ""
    title: str = ""
    payload: dict[str, Any] = {}
    instruction: str = ""
    example: str = ""
    negative_example: str = ""
    when_json: dict[str, Any] = {}


@router.post("/entries")
async def create_entry_api(
    body: CreateEntryRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    entry, gate, _error = await create_entry(
        db,
        user_id=uid,
        genre=body.genre,
        concept=body.concept,
        concept_id=body.concept_id,
        title=body.title,
        payload=body.payload,
        instruction=body.instruction,
        example=body.example,
        negative_example=body.negative_example,
        when_json=body.when_json,
        src_kind="manual",
    )
    # 失败统一看 entry is None（service 的情节拒收/payload/闸门臂 error 恒 None，
    # 错误明细在 gate.errors——真机 500 实锤后修正的接法）
    if entry is None:
        first = next(iter(gate.errors.values()), "入库校验未通过")
        raise HTTPException(422, detail={"message": first, "errors": gate.errors, "warnings": gate.warnings})
    return {"ok": True, "data": _entry_dict(entry)}


# ─── 概念元数据 ────────────────────────────────────────────

@router.get("/concepts")
async def get_concepts(
    genre: str = "",
    user: dict = Depends(get_current_user),
):
    """概念元数据——前端按此生成手录动态字段。"""
    from kb.payloads import _PAYLOAD_MODELS
    result = []
    for name in CONCEPTS:
        model_cls = _PAYLOAD_MODELS.get(name)
        fields = []
        if model_cls:
            for fname, fprop in model_cls.model_fields.items():
                fields.append({
                    "key": fname,
                    "required": fprop.is_required(),
                    "max_length": fprop.metadata[0].max_length if fprop.metadata and hasattr(fprop.metadata[0], 'max_length') else None,
                })
        result.append({
            "name": name,
            "fields": fields,
            "readonly": name == "情节",
        })
    return {"ok": True, "data": {"concepts": result, "themes": THEMES}}


# ─── 库列表 ──────────────────────────────────────────────

@router.get("/libraries")
async def list_libraries_api(
    genre: str = "",
    novel_id: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    libs = await list_libraries(db, user_id=uid, genre=genre)
    # 几本书启用（库卡亮相批3）：绑定行按库分组计数（跨书）
    bound_counts: dict[str, int] = {
        row[0]: row[1]
        for row in (
            await db.execute(
                select(KbBookBinding.library_id, func.count(KbBookBinding.id))
                .where(KbBookBinding.enabled.is_(True))
                .group_by(KbBookBinding.library_id)
            )
        ).all()
    }
    # 成员数（含场景条目）：auto 库按 (user,genre,concept) 计数；手动圈选库走 items
    from models.kb import KbLibraryItem

    entry_counts: dict[str, int] = {}
    for l in libs:
        if l.rule_kind == "auto":
            n = (
                await db.execute(
                    select(func.count(KbEntry.id)).where(
                        KbEntry.user_id == uid,
                        KbEntry.genre == l.genre,
                        KbEntry.concept == l.concept,
                        KbEntry.status == "active",
                    )
                )
            ).scalar_one()
        else:
            n = (
                await db.execute(
                    select(func.count(KbLibraryItem.id)).where(KbLibraryItem.library_id == l.id)
                )
            ).scalar_one()
        entry_counts[l.id] = int(n or 0)
    items = []
    for l in libs:
        # 本书是否已启用（库卡「本书已启用」徽章；novel_id 缺省＝账号级浏览）
        bound = 0
        if novel_id:
            bound = 1 if (
                await db.execute(
                    select(KbBookBinding.id).where(
                        KbBookBinding.novel_id == novel_id,
                        KbBookBinding.library_id == l.id,
                        KbBookBinding.enabled.is_(True),
                    )
                )
            ).scalar_one_or_none() else 0
        items.append(
            {
                "id": l.id,
                "genre": l.genre,
                "concept": l.concept,
                "name": l.name,
                "purpose": l.purpose,
                "contract": l.contract,
                "enabled": l.enabled,
                "entry_count": entry_counts.get(l.id, 0),
                "bound_novels": bound_counts.get(l.id, 0),
                "bound_in_book": bound,
            }
        )
    return {"ok": True, "data": items}


# ─── 全局图（c-kb-organize 批7：聚合＋下钻；关系边随 AI 整理二阶段）──


@router.get("/graph/aggregate")
async def graph_aggregate_api(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """聚合视图：题材×概念格子节点（默认首屏 ≤80 节点内）＋题材—格子层级边。"""
    uid = _user(user)
    counts = await genre_counts(db, user_id=uid)
    # 格子计数：用户条目 ∪ 基线层（与题材栏/下钻同口径；只算用户段会让纯基线
    # 账号的图谱空白、混合账号的节点数与格子和对不上）
    from kb.merged import baseline_cell_counts

    rows = (
        await db.execute(
            select(KbEntry.genre, KbEntry.concept, func.count(KbEntry.id)).where(
                KbEntry.user_id == uid, KbEntry.status == "active"
            ).group_by(KbEntry.genre, KbEntry.concept)
        )
    ).all()
    cells: dict[tuple[str, str], int] = {(g, c): int(n) for g, c, n in rows}
    for key, n in (await baseline_cell_counts(db, user_id=uid)).items():
        cells[key] = cells.get(key, 0) + n
    nodes = []
    links = []
    for (genre, concept), n in cells.items():
        gid = f"genre:{genre or '_general'}"
        cid = f"cell:{genre or '_general'}:{concept}"
        nodes.append({"id": cid, "kind": "cell", "genre": genre or "", "concept": concept, "count": int(n)})
        links.append({"source": gid, "target": cid})
    seen = set()
    for lnk in links:
        gid = lnk["source"]
        if gid in seen:
            continue
        seen.add(gid)
        gname = "" if gid == "genre:_general" else gid.removeprefix("genre:")
        nodes.append({
            "id": gid, "kind": "genre", "genre": gname, "concept": "",
            "count": int(counts.get(gname, 0)),
        })
    return {"ok": True, "data": {"nodes": nodes, "links": links}}


@router.get("/graph/cell")
async def graph_cell_api(
    genre: str = "",
    concept: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """下钻：一个格子里的条目节点（悬停邻域高亮在前端；条目—格子边前端补）。"""
    uid = _user(user)
    entries, _cursor = await list_entries(db, user_id=uid, genre=genre, concept=concept, limit=100)
    nodes = [
        {
            "id": e.id,
            "kind": "entry",
            "genre": e.genre,
            "concept": e.concept,
            "title": e.title or e.instruction[:20],
            "scope": "scene" if json.loads(e.when_json or "{}") else "base",
        }
        for e in entries
    ]
    return {"ok": True, "data": {"nodes": nodes}}


# ─── 角色库迁移（c-kb-character-migration 批6）──────────────


@router.post("/migrate-library")
async def migrate_library_api(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """角色库全量 → 知识库条目（幂等，可重复执行）。"""
    from kb.migrate_library import migrate_character_library

    result = await migrate_character_library(db, user_id=_user(user))
    return {"ok": True, "data": result}


# ─── 条目编辑/删除（c-kb-character-migration 刀2a）──────────


class UpdateEntryRequest(BaseModel):
    rev: int | None = None
    title: str | None = None
    instruction: str | None = None
    payload: dict[str, Any] | None = None
    example: str | None = None
    negative_example: str | None = None
    when_json: dict[str, Any] | None = None


@router.patch("/entries/{entry_id}")
async def update_entry_api(
    entry_id: str,
    body: UpdateEntryRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    entry, gate, error = await update_entry(
        db, user_id=uid, entry_id=entry_id,
        rev=body.rev, title=body.title, instruction=body.instruction,
        payload=body.payload, example=body.example,
        negative_example=body.negative_example, when_json=body.when_json,
    )
    if error:
        if error["code"] == "not_found":
            raise HTTPException(404, "Entry not found")
        if error["code"] == "rev_conflict":
            raise HTTPException(409, detail={"message": "内容已被另一处改过，刷新后再试", "code": "rev_conflict", "rev": error["current_rev"]})
        if error["code"] == "payload":
            raise HTTPException(422, detail={"message": error.get("message") or "内容校验未通过"})
        raise HTTPException(422, detail={"message": "入库校验未通过", "errors": gate.errors, "warnings": gate.warnings})
    return {"ok": True, "data": _entry_dict(entry)}


@router.delete("/entries/{entry_id}")
async def delete_entry_api(
    entry_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    removed = await delete_entry(db, user_id=_user(user), entry_id=entry_id)
    if not removed:
        raise HTTPException(404, "Entry not found")
    return {"ok": True, "data": {"deleted": entry_id}}


# ─── 基线条目覆盖（c-kb-baseline 批B）：写时复制 ───────────


class BaselineOverrideRequest(BaseModel):
    action: str  # hide | edit
    instruction: str = ""


@router.put("/entries/{entry_id}/baseline-override")
async def set_baseline_override_api(
    entry_id: str,
    body: BaselineOverrideRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """隐藏／存副本（编辑基线＝在用户层物化副本，官方原件不变）。

    只读层条目 SHALL 无编辑与删除：本端点是基线层唯一写口，且只写用户层。
    """
    from kb.merged import set_overlay

    result = await set_overlay(
        db, user_id=_user(user), entry_id=entry_id,
        action=body.action, instruction=body.instruction,
    )
    if result.get("error") == "not_found":
        raise HTTPException(404, "Entry not found")
    if result.get("error") == "action":
        raise HTTPException(422, detail={"message": "不支持的覆盖动作"})
    if result.get("error") == "gate":
        raise HTTPException(422, detail={"message": result.get("message") or "内容校验未通过"})
    return {"ok": True, "data": {"entry_id": entry_id, "action": body.action}}


@router.delete("/entries/{entry_id}/baseline-override")
async def clear_baseline_override_api(
    entry_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """恢复默认／恢复官方版：删覆盖记录，原件重新透出（基线层零变化）。"""
    from kb.merged import clear_overlay

    result = await clear_overlay(db, user_id=_user(user), entry_id=entry_id)
    if result.get("error") == "not_found":
        raise HTTPException(404, "Entry not found")
    return {"ok": True, "data": {"entry_id": entry_id, "restored": True}}


# ─── 原型使用计数（c-kb-character 批4）─────────────────────


@router.post("/entries/{entry_id}/prototype-use")
async def prototype_use_api(
    entry_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用作原型计数回写：KbPref.adopt_count 累加（账号级，跨书共享）。"""
    uid = _user(user)
    e = await get_entry(db, user_id=uid, entry_id=entry_id)
    if not e or e.concept != "角色设定":
        raise HTTPException(404, "原型不存在")
    from datetime import datetime

    pref = (
        await db.execute(select(KbPref).where(KbPref.user_id == uid, KbPref.entry_id == entry_id))
    ).scalar_one_or_none()
    if pref:
        pref.adopt_count += 1
        pref.last_used_at = datetime.utcnow()
    else:
        pref = KbPref(user_id=uid, entry_id=entry_id, weight=1.0, adopt_count=1, last_used_at=datetime.utcnow())
        db.add(pref)
    await db.commit()
    return {"ok": True, "data": {"entry_id": entry_id, "adopt_count": pref.adopt_count}}


# ─── 书内绑定（c-kb-snapshot 批3：启用落设定）──────────────


class BindRequest(BaseModel):
    novel_id: str = ""
    library_id: str = ""


@router.post("/bindings")
async def bind_library_api(
    body: BindRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    project = await get_novel(db, body.novel_id, uid)
    if not project:
        raise HTTPException(404, "Project not found")
    from kb.snapshot import bind_library

    binding, info, error = await bind_library(
        db,
        user_id=uid,
        novel_id=body.novel_id,
        root_path=project.root_path,
        library_id=body.library_id,
    )
    if error:
        raise HTTPException(404, error)
    return {"ok": True, "data": {"binding_id": binding.id, **info}}


@router.get("/bindings")
async def list_bindings_api(
    novel_id: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    project = await get_novel(db, novel_id, uid)
    if not project:
        raise HTTPException(404, "Project not found")
    from kb.snapshot import list_bindings

    return {"ok": True, "data": await list_bindings(db, novel_id=novel_id)}


@router.post("/bindings/{binding_id}/sync")
async def sync_binding_api(
    binding_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    binding = (
        await db.execute(
            select(KbBookBinding).where(KbBookBinding.id == binding_id)
        )
    ).scalar_one_or_none()
    if not binding:
        raise HTTPException(404, "Binding not found")
    project = await get_novel(db, binding.novel_id, uid)
    if not project:
        raise HTTPException(404, "Project not found")
    from kb.snapshot import sync_binding

    result = await sync_binding(db, binding, project.root_path)
    if result.get("error"):
        raise HTTPException(409, result["error"])
    return {"ok": True, "data": result}


@router.delete("/bindings/{binding_id}")
async def unbind_api(
    binding_id: str,
    novel_id: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = _user(user)
    project = await get_novel(db, novel_id, uid)
    if not project:
        raise HTTPException(404, "Project not found")
    from kb.snapshot import unbind

    removed = await unbind(db, novel_id=novel_id, binding_id=binding_id)
    if not removed:
        raise HTTPException(404, "Binding not found")
    return {"ok": True, "data": {"unbound": binding_id}}


@router.post("/entries/{entry_id}/pref")
async def set_pref_api(
    entry_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """有用/没用回写（c-kb-write-block C3）：kb_prefs 账号级 (user_id, entry_id)。

    useful=True→adopt_count+1，否则 drop_count+1；weight 存当前有用率
    （采纳/(采纳+弃用)，下限 0.2）。可重复调用＝可改口。
    基线条目同样可反馈（反馈记在代理 id 上，供官方修订聚合，c-kb-baseline 批B）。"""
    from models.kb import KbEntry, KbPref

    uid = _user(user)
    # 双域（c-kb-book-scope 批B）：副本 id 优先查书级（novel_id 归属校验防跨书打标），
    # miss 回退账号级（存量语义）

    copy = (
        await db.execute(
            select(KbBookEntry).where(
                KbBookEntry.id == entry_id,
                KbBookEntry.user_id == uid,
                KbBookEntry.status == "active",
            )
        )
    ).scalar_one_or_none()
    entry = (
        await db.execute(
            select(KbEntry).where(
                KbEntry.id == entry_id, KbEntry.user_id == uid, KbEntry.status == "active"
            )
        )
    ).scalar_one_or_none() if copy is None else copy
    if entry is None:
        from kb.merged import get_merged_entry

        if await get_merged_entry(db, user_id=uid, entry_id=entry_id) is None:
            raise HTTPException(404, "Entry not found")
    useful = bool(body.get("useful"))
    pref = (
        await db.execute(
            select(KbPref).where(KbPref.user_id == uid, KbPref.entry_id == entry_id)
        )
    ).scalar_one_or_none()
    if pref is None:
        pref = KbPref(user_id=uid, entry_id=entry_id)
        db.add(pref)
    if useful:
        pref.adopt_count = (pref.adopt_count or 0) + 1
    else:
        pref.drop_count = (pref.drop_count or 0) + 1
    total = (pref.adopt_count or 0) + (pref.drop_count or 0)
    pref.weight = max(0.2, (pref.adopt_count or 0) / total) if total else 1.0
    pref.last_used_at = func.now()
    await db.commit()
    return {
        "ok": True,
        "data": {
            "entry_id": entry_id,
            "adopt_count": pref.adopt_count,
            "drop_count": pref.drop_count,
            "useful_rate": round(pref.weight, 3),
        },
    }


@router.get("/match-runs")
async def match_runs_api(
    novel_id: str = "",
    chapter_ref: str = "",
    limit: int = 10,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """选择运行清单（c-kb-write-block C3）：逐条目留痕供前端只读区与反馈回显。"""
    from models.kb import KbMatchItem, KbMatchRun

    uid = _user(user)
    # kb_match_runs 无 user_id 列（书级级联）——归属经 Novel join 认证
    from models.project import Novel as _Novel

    stmt = (
        select(KbMatchRun)
        .join(_Novel, _Novel.id == KbMatchRun.novel_id)
        .where(_Novel.user_id == uid)
    )
    if novel_id:
        stmt = stmt.where(KbMatchRun.novel_id == novel_id)
    if chapter_ref:
        stmt = stmt.where(KbMatchRun.chapter_ref == chapter_ref)
    stmt = stmt.order_by(KbMatchRun.created_at.desc(), KbMatchRun.id.desc()).limit(max(1, min(limit, 50)))
    runs = (await db.execute(stmt)).scalars().all()
    out = []
    for r in runs:
        items = (
            await db.execute(
                select(KbMatchItem).where(KbMatchItem.run_id == r.id).order_by(KbMatchItem.id)
            )
        ).scalars().all()
        out.append(
            {
                "run_id": r.id,
                "novel_id": r.novel_id,
                "chapter_ref": r.chapter_ref,
                "brief_hash": r.brief_hash,
                "scene": r.scene,
                "emotion": r.emotion,
                "chapter_pos": r.chapter_pos,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "items": [
                    {
                        "clause": i.clause,
                        "entry_id": i.entry_id,
                        "decision": i.decision,
                        "score": i.score,
                        "reason": i.reason,
                    }
                    for i in items
                ],
            }
        )
    return {"ok": True, "data": {"runs": out}}


# ─── 知识整理（c-kb-organize 批C：手动触发/状态/待确认清单/采纳与反馈/条目图） ──


@router.post("/organize/run")
async def organize_run_api(
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动整理一次（幂等：该题材 running 中返回提示不重复跑）。full=True 走全量深度。"""
    from kb.organize import run_manual

    genre = str(body.get("genre") or "").strip()
    if not genre:
        raise HTTPException(400, "缺 genre")
    result = await run_manual(
        db, user_id=_user(user), genre=genre, full=bool(body.get("full"))
    )
    if not result.get("ok") and result.get("code") == "running":
        return {"ok": True, "data": {"skipped": True, "message": result["message"]}}
    if not result.get("ok"):
        raise HTTPException(502, result.get("message") or "整理失败")
    return {"ok": True, "data": result}


@router.get("/organize/status")
async def organize_status_api(
    genre: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from kb.organize import organize_status

    if not genre:
        raise HTTPException(400, "缺 genre")
    return {"ok": True, "data": await organize_status(db, user_id=_user(user), genre=genre)}


@router.get("/organize/findings")
async def organize_findings_api(
    genre: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """待确认清单：pending 关系＋四类建议汇聚（作家逐条采纳/忽略）。"""
    from kb.organize import list_pending

    return {"ok": True, "data": await list_pending(db, user_id=_user(user), genre=genre)}


@router.post("/organize/findings/{finding_id}/adopt")
async def organize_finding_adopt_api(
    finding_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """采纳建议（merge/reclass/quality 动数据；subconcept 仅落状态）。"""
    from kb.organize import adopt_finding

    ok, message = await adopt_finding(db, user_id=_user(user), finding_id=finding_id)
    if not ok:
        raise HTTPException(404 if message == "not_found" else 409, message)
    return {"ok": True, "data": {"message": message}}


@router.post("/organize/findings/{finding_id}/ignore")
async def organize_finding_ignore_api(
    finding_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """忽略建议：同签名不再提出（条目实质更新后可再提）。"""
    from kb.organize import ignore_finding

    if not await ignore_finding(db, user_id=_user(user), finding_id=finding_id):
        raise HTTPException(404, "not_found")
    return {"ok": True, "data": {"message": "已忽略"}}


@router.post("/relations/{relation_id}/adopt")
async def organize_relation_adopt_api(
    relation_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """待确认关系 → 生效（进全局图与计数）。"""
    from kb.organize import adopt_pending_relation

    ok, message = await adopt_pending_relation(db, user_id=_user(user), relation_id=relation_id)
    if not ok:
        raise HTTPException(404 if message == "not_found" else 409, message)
    return {"ok": True, "data": {"message": message}}


@router.post("/relations/{relation_id}/reject")
async def organize_relation_reject_api(
    relation_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """否决待确认关系（archived，不删行）。"""
    from kb.organize import reject_pending_relation

    ok, message = await reject_pending_relation(db, user_id=_user(user), relation_id=relation_id)
    if not ok:
        raise HTTPException(404 if message == "not_found" else 409, message)
    return {"ok": True, "data": {"message": message}}


@router.get("/entries/{entry_id}/relations")
async def entry_relations_api(
    entry_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """条目详情的关系列表（active＋pending；merged 条目附合并指向）。"""
    from kb.organize import entry_relations

    data = await entry_relations(db, user_id=_user(user), entry_id=entry_id)
    if data.get("error"):
        raise HTTPException(404, "Entry not found")
    return {"ok": True, "data": data}


@router.post("/relations/{relation_id}/feedback")
async def organize_relation_feedback_api(
    relation_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """「这条不对」：落签名反馈，下次整理降低同类候选权重；关系本体不动。"""
    from kb.organize import relation_feedback

    ok, message = await relation_feedback(db, user_id=_user(user), relation_id=relation_id)
    if not ok:
        raise HTTPException(404, "not_found")
    return {"ok": True, "data": {"message": message}}


@router.get("/graph/entries")
async def graph_entries_api(
    genre: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """条目图：题材内 active 条目为节点、active 关系为边（≤500 按置信降序）。"""
    from kb.organize import graph_entries

    return {"ok": True, "data": await graph_entries(db, user_id=_user(user), genre=genre)}

@router.post("/book-scope/import")
async def import_book_scope_api(
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """存量书补平（c-kb-book-scope 批C）：按书题材把账号库「命中＋通用」增量导入
    书级副本（幂等，只补新条）。非流式出口（来源行一键导入）。"""
    from models.project import Novel as _Novel

    uid = _user(user)
    novel_id = str(body.get("novel_id") or "")
    novel = await db.get(_Novel, novel_id)
    if novel is None or novel.user_id != uid or novel.status == "deleted":
        raise HTTPException(404, "Book not found")
    from kb.book_scope import import_genre_knowledge, novel_genre

    result = await import_genre_knowledge(
        db, novel_id=novel_id, user_id=uid, genre=await novel_genre(novel.root_path)
    )
    return {"ok": True, "data": result}


@router.post("/book-scope/import/stream")
async def import_book_scope_stream_api(
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """题材知识导入进度流（c-kb-book-scope 弹窗二选一）：SSE 逐概念组下发进度。

    事件：phase(copy,total) → phase(copy,concept,done,total)×N → phase(baseline)
    → done{imported,skipped,...}；流内失败以 error 事件收尾（前端可读）。"""
    from fastapi.responses import StreamingResponse

    from models.project import Novel as _Novel

    uid = _user(user)
    novel_id = str(body.get("novel_id") or "")
    novel = await db.get(_Novel, novel_id)
    if novel is None or novel.user_id != uid or novel.status == "deleted":
        raise HTTPException(404, "Book not found")
    from kb.book_scope import novel_genre, stream_import_genre_knowledge

    genre = await novel_genre(novel.root_path)

    async def _gen():
        try:
            async for ev in stream_import_genre_knowledge(
                db, novel_id=novel_id, user_id=uid, genre=genre
            ):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001 —— 流内失败以事件收尾，不静默断流
            yield (
                "data: "
                + json.dumps(
                    {"type": "error", "message": str(e) or "导入失败"},
                    ensure_ascii=False,
                )
                + "\n\n"
            )

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/book-scope/decline")
async def book_scope_decline_api(
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """弹窗二选一里的「我自己设定」：落 declined 标记，设定页不再自动弹窗
    （来源行保留手动导入出口）。"""
    from models.project import Novel as _Novel

    uid = _user(user)
    novel_id = str(body.get("novel_id") or "")
    novel = await db.get(_Novel, novel_id)
    if novel is None or novel.user_id != uid or novel.status == "deleted":
        raise HTTPException(404, "Book not found")
    from kb.book_scope import write_import_declined

    declined = bool(body.get("declined", True))
    await write_import_declined(novel.root_path, declined)
    return {"ok": True, "data": {"declined": declined}}


@router.get("/book-scope/diff")
async def book_scope_diff_api(
    novel_id: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """「库有 N 条新增」差异计数＋导入决策（c-kb-book-scope）：题材命中未复制的
    active 条目数；declined=作家已选过「我自己设定」。"""
    from models.project import Novel as _Novel

    uid = _user(user)
    novel = await db.get(_Novel, novel_id)
    if novel is None or novel.user_id != uid or novel.status == "deleted":
        raise HTTPException(404, "Book not found")
    from kb.book_scope import load_import_state, novel_genre, read_import_declined

    genre = await novel_genre(novel.root_path)
    # 差异＝merged 视图（用户条目∪基线层）里尚未复制进本书的条数——与导入同一口径
    _sources, todo = await load_import_state(
        db, novel_id=novel_id, user_id=uid, genre=genre
    )
    new_count = len(todo)
    declined = await read_import_declined(novel.root_path)
    return {
        "ok": True,
        "data": {"new_count": int(new_count or 0), "declined": declined},
    }


# ── 知识 v2：归档/恢复/实例（c-kb-knowledge-v2）─────────────────────────


@router.post("/entries/{entry_id}/archive")
async def archive_entry_api(
    entry_id: str,
    user: Annotated[dict, Depends(_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ok = await knowledge_service.archive_knowledge(db, user_id=_user(user), entry_id=entry_id)
    if not ok:
        return JSONResponse(status_code=404, content={"ok": False, "error": "知识不存在或已归档"})
    return {"ok": True, "entry_id": entry_id}


@router.post("/entries/{entry_id}/restore")
async def restore_entry_api(
    entry_id: str,
    user: Annotated[dict, Depends(_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ok = await knowledge_service.restore_knowledge(db, user_id=_user(user), entry_id=entry_id)
    if not ok:
        return JSONResponse(status_code=404, content={"ok": False, "error": "知识不存在或未归档"})
    return {"ok": True, "entry_id": entry_id}


@router.get("/entries/{entry_id}/instances")
async def list_instances_api(
    entry_id: str,
    user: Annotated[dict, Depends(_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from models.kb import KbKnowledgeInstance
    from sqlalchemy import select

    rows = (await db.execute(
        select(KbKnowledgeInstance)
        .where(KbKnowledgeInstance.knowledge_id == entry_id)
        .order_by(KbKnowledgeInstance.sort)
    )).scalars().all()
    return {"ok": True, "instances": [
        {"id": r.id, "text": r.text, "source_kind": r.source_kind,
         "source_novel": r.source_novel, "source_chapter": r.source_chapter,
         "quote": r.quote, "sort": r.sort}
        for r in rows
    ]}


@router.post("/entries/{entry_id}/instances")
async def add_instance_api(
    entry_id: str,
    user: Annotated[dict, Depends(_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: dict[str, Any] = Body(...),
):
    inst = await knowledge_service.add_instance(
        db, knowledge_id=entry_id,
        text=body.get("text", ""),
        source_kind=body.get("source_kind", "拆书"),
        source_novel=body.get("source_novel", ""),
        source_chapter=body.get("source_chapter", ""),
        quote=body.get("quote", ""),
        sort=body.get("sort", 0),
    )
    return {"ok": True, "instance": {"id": inst.id, "text": inst.text}}
