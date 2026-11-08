"""知识提炼（boss 2026-11-08）：把「其他」暂存节点的原始材料消化归类进知识树。

流程（单向，不打圈——树先行，实例永不反过来定义模板）：
1. 取「其他」节点下的实例（fields_json＝拆书产物原始键值，正文「名字：一句话」）；
2. LLM 对照知识树归类：
   a. 树上有家 → 挂已有知识点（格值＝模板映射原始键优先，LLM 补模板缺口）；
   b. 树上没有 → 提议新知识点（名字/定义/模板格）→ 自动建行挂树 → 实例归位；
   c. 撑不起知识的留守其他。
3. 护栏：每轮新节点 ≤3、批量实例 ≤30、单飞（进程锁）、id 逐字校验、LLM 挂了不挪任何东西。
"""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select as sel
from sqlalchemy.ext.asyncio import AsyncSession

from models.kb import KbEntry, KbKnowledgeInstance

logger = logging.getLogger(__name__)

# 护栏（boss 拍板「能识别并添加」——添加要有闸）
MAX_NEW_NODES = 3
MAX_BATCH = 30

# 概念白名单（新节点的 concept 必须落在五维内）
_CONCEPTS = {"手法", "文风", "文笔", "世界设定", "角色设定"}

# 进程内单飞（提炼与总结同题材互斥，防双跑同写同节点行）
_REFINE_LOCKS: dict[tuple[str, str], asyncio.Lock] = {}


def _user_lock(user_id: str, genre: str) -> asyncio.Lock:
    return _REFINE_LOCKS.setdefault((user_id, genre), asyncio.Lock())


def _tree_digest() -> str:
    """知识树 → LLM 文本（每节点一行：key|名字|定义|父名|模板格名）。"""
    from kb.taxonomy import nodes

    ns = nodes()
    by_key = {k: n.get("title", k) for k, n in ns.items()}
    lines = ["key|名字|定义|父节点|模板格"]
    for k, n in ns.items():
        fields = "、".join(f.get("name", "") for f in (n.get("fields") or []))
        parent = by_key.get(n.get("parent", ""), "")
        lines.append(f"{k}|{n.get('title', '')}|{n.get('definition', '')}|{parent}|{fields or '（枝干/暂存，不挂实例）'}")
    return "\n".join(lines)


async def _stage_rows(db: AsyncSession, user_id: str, genre: str) -> tuple[KbEntry | None, list[KbKnowledgeInstance]]:
    """「其他」节点行（不物化——没行就没暂存）＋其下实例（旧→新，截 MAX_BATCH）。"""
    other = (await db.scalars(
        sel(KbEntry).where(
            KbEntry.user_id == user_id,
            KbEntry.genre == genre,
            KbEntry.concept == "",
            KbEntry.origin == "summary",
            KbEntry.title == "其他",
        ).limit(1)
    )).first()
    if other is None:
        return None, []
    rows = (await db.scalars(
        sel(KbKnowledgeInstance)
        .where(KbKnowledgeInstance.knowledge_id == other.id)
        .order_by(KbKnowledgeInstance.created_at.asc())
        .limit(MAX_BATCH)
    )).all()
    return other, rows


async def _llm_refine(user_id: str, genre: str, tree: str, items: list[str]) -> dict:
    """调 kb_refine 模板。返回 {moves, new_nodes}；失败抛异常（由调用方记 error）。"""
    from ai_client import get_ai_client_for_user
    from prompts import load_layers

    system, user_tpl = load_layers("kb_refine")
    usage: dict = {}
    client = await get_ai_client_for_user(user_id)
    raw = await client.chat(
        model="haiku",
        system=system.format(genre=genre),
        messages=[{"role": "user", "content": user_tpl.format(genre=genre, tree=tree, items="\n".join(items))}],
        max_tokens=8000,
        usage=usage,
        operation="kb_refine",
    )
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(cleaned or "{}")
    if not isinstance(data, dict):
        raise TypeError("llm: bad shape")
    return {
        "moves": data.get("moves") if isinstance(data.get("moves"), list) else [],
        "new_nodes": data.get("new_nodes") if isinstance(data.get("new_nodes"), list) else [],
    }


async def run_refine(db: AsyncSession, *, user_id: str, genre: str, llm: bool = True) -> tuple[dict | None, str]:
    """提炼一轮：其他 → 树。返回 (summary, error)；单飞命中返 (None, "running")。"""
    lock = _user_lock(user_id, genre)
    if lock.locked():
        return None, "running"
    async with lock:
        return await _refine_on(db, user_id=user_id, genre=genre, llm=llm)


async def _refine_on(db: AsyncSession, *, user_id: str, genre: str, llm: bool) -> tuple[dict | None, str]:
    from kb.summarize import (
        _fields_by_template,
        materialize_node_row,
        materialize_tree_chain,
    )
    from kb.taxonomy import nodes as taxonomy_nodes

    other, staged = await _stage_rows(db, user_id, genre)
    if other is None or not staged:
        return {"staged": 0, "moved": 0, "nodes_created": 0, "kept": 0}, ""

    items = [
        f"{i.id}|{i.text[:160]}|格:{(i.fields_json or '')[:200]}|摘句:{(i.quote or '')[:80]}"
        for i in staged
    ]

    if not llm:
        return {"staged": len(staged), "moved": 0, "nodes_created": 0, "kept": len(staged)}, ""

    try:
        plan = await _llm_refine(user_id, genre, _tree_digest(), items)
    except Exception as exc:  # noqa: BLE001 — LLM 挂了不挪任何东西（fail-soft）
        logger.warning("event=kb.refine.llm_fail user=%s err=%s", user_id, exc)
        return None, f"llm: {exc}"

    staged_ids = {s.id for s in staged}
    staged_map_all = {x.id: x for x in staged}

    # ① 新节点（护栏内）——先有节点后有实例，方向单向；父锚必须落在发版树已有节点
    new_kid: dict[str, str] = {}      # 提案 key → 新行 id
    new_tpl: dict[str, list[dict]] = {}
    created = 0
    for prop in plan["new_nodes"]:
        if created >= MAX_NEW_NODES:
            break
        if not isinstance(prop, dict):
            continue
        title = str(prop.get("title") or "").strip()[:12]
        definition = str(prop.get("definition") or "").strip()[:80]
        parent_key = str(prop.get("parent") or "").strip()
        concept = str(prop.get("concept") or "").strip()
        if not title or not definition or not parent_key or parent_key not in taxonomy_nodes():
            continue
        fields_prop = [f for f in (prop.get("fields") or []) if isinstance(f, dict)][:6]
        try:
            parent_kid = await materialize_tree_chain(db, user_id=user_id, genre=genre, node_key=parent_key)
            pn = taxonomy_nodes()[parent_key]
            kid = await materialize_node_row(
                db, user_id=user_id, genre=genre, concept=concept or pn.get("concept", ""),
                title=title, definition=definition, parent_id=parent_kid,
                schema_json=json.dumps(
                    [{"name": f.get("name", ""), "desc": f.get("desc", "")} for f in fields_prop],
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — 单提案失败不拖垮整轮
            logger.warning("event=kb.refine.node_fail title=%s err=%s", title, exc)
            continue
        created += 1
        raw_key = str(prop.get("key") or "").strip()
        # LLM 自编 key 碰撞（两个提案都叫 n1）＝后者改写 pkey，先建行不丢（评审 P3）
        pkey = raw_key or f"n{created}"
        while pkey in new_kid:
            pkey = f"{pkey or 'n'}x{created}"
        new_kid[pkey] = kid
        new_tpl[pkey] = [{"name": f.get("name", ""), "desc": f.get("desc", "")} for f in fields_prop]

    # ② 归类计划：id 校验＋目标锚定（发版树 key 或本轮新节点 key）
    claims: list[tuple[KbKnowledgeInstance, str, str, dict, str]] = []  # (实例, kid, 模板, LLM格值, 目标名)
    claimed_ids: set[str] = set()  # moves 重复 id 去重（评审 P3：二连挂会 kept 负数）
    # 提案新节点 instances 通道：契约「instances 只是汇总」——汇总 id 也归到新节点
    # （LLM 只填 instances 不重复填 moves 时兜底；评审 P2：死通道会让提炼空转）
    instance_fallback: dict[str, tuple[str, list[dict], str]] = {}  # iid -> (kid, tpl, 目标名)
    for prop in plan["new_nodes"]:
        if not isinstance(prop, dict):
            continue
        raw_key = str(prop.get("key") or "").strip()
        match_key = next((k for k, v in ((k, str(prop.get("key") or "")) for k in [raw_key]) if v), raw_key)
        _kid = new_kid.get(match_key)
        if not _kid:
            continue
        _tpl = new_tpl.get(match_key) or []
        _title = str(prop.get("title") or "")
        for iid in (prop.get("instances") or []):
            iid_s = str(iid)
            if iid_s in staged_ids:
                instance_fallback[iid_s] = (_kid, _tpl, _title)
    for mv in plan["moves"]:
        if not isinstance(mv, dict):
            continue
        iid = str(mv.get("id") or "")
        to = str(mv.get("to") or "")
        llm_fields = mv.get("fields") if isinstance(mv.get("fields"), dict) else {}
        if iid not in staged_ids or iid in claimed_ids:
            continue
        try:
            if to in taxonomy_nodes():
                tpl = taxonomy_nodes()[to].get("fields") or []
                kid = await materialize_tree_chain(db, user_id=user_id, genre=genre, node_key=to)
                target = taxonomy_nodes()[to].get("title", to)
            elif to in new_kid:
                tpl = new_tpl[to]
                kid = new_kid[to]
                target = next((str(p.get("title") or "") for p in plan["new_nodes"]
                               if isinstance(p, dict) and str(p.get("key") or "") == to), to)
            else:
                continue  # 归属目标不存在——留守其他
        except Exception as exc:  # noqa: BLE001 — 单条失败不拖垮整轮
            logger.warning("event=kb.refine.move_fail id=%s err=%s", iid, exc)
            continue
        claimed_ids.add(iid)
        claims.append((staged_map_all[iid], kid, tpl,
                       {str(k): str(v)[:200] for k, v in llm_fields.items()}, target))
    # instances 兜底：moves 没覆盖到的提案 instances（每 iid 只一次）
    for iid, (kid, tpl, title) in instance_fallback.items():
        if iid in claimed_ids:
            continue
        claimed_ids.add(iid)
        claims.append((staged_map_all[iid], kid, tpl, {}, title))

    # ③ 写库：移动实例＋重落格
    #    发版树目标＝模板重映射原始键（确定性）＋LLM 补模板缺口格；
    #    新提案节点＝LLM 格值按提案格过滤（原始键对不上新模板）
    moved = 0
    moves_detail: list[dict] = []
    for s, kid, tpl, llm_fields, target in claims:
        try:
            raw_fields = json.loads(s.fields_json or "{}")
            if not isinstance(raw_fields, dict):
                raw_fields = {}
        except ValueError:
            raw_fields = {}
        if tpl and any(f.get("from") for f in tpl):
            fields = _fields_by_template(tpl, raw_fields, s.text or "")
        else:
            fields = {}
        slot_names = {f["name"] for f in tpl}
        for k, v in llm_fields.items():
            if (not slot_names or k in slot_names) and v and k not in fields:
                fields[k] = v
        s.knowledge_id = kid
        s.fields_json = json.dumps(fields, ensure_ascii=False)
        moved += 1
        moves_detail.append({"from_text": (s.text or "")[:80], "to": target})

    await db.commit()
    new_nodes_detail = []
    for prop in plan["new_nodes"]:
        if not isinstance(prop, dict):
            continue
        pkey = str(prop.get("key") or "")
        if pkey not in new_kid:
            continue
        parent_key = str(prop.get("parent") or "")
        new_nodes_detail.append({
            "title": str(prop.get("title") or "")[:12],
            "parent_title": (taxonomy_nodes().get(parent_key) or {}).get("title", parent_key),
            "definition": str(prop.get("definition") or "")[:80],
            "fields": [f.get("name", "") for f in (prop.get("fields") or []) if isinstance(f, dict)][:6],
        })
    return {
        "staged": len(staged), "moved": moved, "nodes_created": created,
        "kept": len(staged) - moved,
        "details": {"moves": moves_detail[:20], "new_nodes": new_nodes_detail[:MAX_NEW_NODES]},
    }, ""
