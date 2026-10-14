"""图谱装配（c-deconstruct-book 阶段三）——deconstruct-graph/6 契约的代码投影。

- 装配＝**管线阶段三**（全部维度归并完成后、置 completed 之前）：输入 cards.entries＋十维终稿
  ＋一次地点归并调用（`deconstruct_place`）产物 → 结构化图谱，缓存 `dims_json["graph"]`
  （append-only：id 按确定性排序分配；缓存存在即不重算）。
- 模型不产 id/章号/计数（评审纪律）：id 装配层分配；首现章＝min(引用章) 代码盖章；
  `chapters.who/at` 与 `links` 基线「到过」由 presence 派生；`events`＝mainplot arcs 投影。
- 降级（评审 P0：图谱病着也要出）：数据问题记 `meta.warnings` 照常出图；结构性异常由调用方
  记 `graph_error`，导出端报可读 400。
- quote 原文回验：去空白/标点的模糊匹配，失败剥 quote 留关系并聚合留痕。
"""

from __future__ import annotations

import json
import math
import re

# 封闭关系类型表（与 docs/design-c/contracts/deconstruct-graph-6.schema.json 同源；改动先改契约）
REL_TYPES: dict[str, list[str]] = {
    "亲缘": ["亲子", "夫妻", "兄弟姊妹", "收养"],
    "情感": ["爱慕", "挚友", "恩义", "敌对"],
    "从属": ["师徒", "主从", "同门", "同僚"],
    "利益": ["合作", "利用", "依附", "契约"],
    "物属": ["持有", "守护", "指向"],
}
REL_RULE = (
    "封闭 enum：edges.kind 只准从这里逐字选；清单外走 {kind:\"自定义\", raw:\"原文措辞\"} 逃生口，"
    "高频者经人工晋升入表。同义归并口径：宿怨/构陷之恨→敌对；救命之情/感恩→恩义；统领驱使→主从。"
    "方向：恩义/爱慕/主从/利用=单向，其余双向；同人多重关系保留多条边。"
)
REL_BOUNDARY = "边＝稳定关系（跨章存续）；动作＝事件（作证/施压/截杀/收留/递帖归 events 与 presence，不占 kind）。"
META_RULE = "章号/首现/who/at/『到过』基线一律代码盖章或派生；模型只产文本与关系；契约冻结后只增不改（additive only）"

_FLAT_KINDS = {k for group in REL_TYPES.values() for k in group}
_ITEM_KINDS = {"持有", "守护", "指向"}
_UPGRADE_KINDS = {"据地", "寄居", "隐于", "活动于"}
_ROLE_ORDER = {"主角": 0, "配角": 1, "反派": 2}
_TIME_TAGS = {"回忆", "插叙", "它线"}
_BIG = 10**6

_PUNCT_RE = re.compile(r"[\s，。！？、；：「」『』“”\"'（）()【】—…·.,!?;:]+")


def _clean(s: object) -> str:
    return str(s or "").strip()


def _as_ch(v: object) -> int | None:
    """章号容错解析：'第3章'/'3'/3 → 3；失败 None。"""
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else None


def _as_int(v: object) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _norm(s: str) -> str:
    return _PUNCT_RE.sub("", s)


def place_merge_input(cards: dict) -> list[str]:
    """逐章「地点＋在场」合并段（喂 deconstruct_place；代码盖【第N章】前缀）。"""
    frags: list[str] = []
    for no, card in sorted(cards.items(), key=lambda kv: int(kv[0] or 0)):
        if not isinstance(card, dict):
            continue
        pl = card.get("places") if isinstance(card.get("places"), list) else []
        pr = card.get("presence") if isinstance(card.get("presence"), list) else []
        if not pl and not pr:
            continue
        frags.append(
            f"【第{no}章】places={json.dumps(pl, ensure_ascii=False)} "
            f"presence={json.dumps(pr, ensure_ascii=False)}"
        )
    return frags


class _Warnings:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, kind: str, msg: str, place: str | None = None) -> None:
        item: dict = {"kind": kind, "msg": msg}
        if place:
            item["place"] = place
        self.items.append(item)

    def count(self, kind: str, n: int, msg: str) -> None:
        if n > 0:
            self.items.append({"kind": kind, "msg": msg, "count": n})


def _assign_ids(names: list[str], prefix: str) -> dict[str, str]:
    """确定性 id 分配（评审：label 排序＋序号，装配层负责，模型不产 id）。"""
    return {name: f"{prefix}{i + 1:02d}" for i, name in enumerate(sorted(names))}


def _prod(products: dict, dim: str) -> dict:
    obj = products.get(dim)
    data = obj.get("data") if isinstance(obj, dict) else None
    return data if isinstance(data, dict) else {}


def _dicts(seq) -> list[dict]:
    return [x for x in seq if isinstance(x, dict)] if isinstance(seq, list) else []


def assemble(
    *,
    book_name: str,
    chapter_count: int,
    words: int,
    cards: dict,
    products: dict,
    place_merge: dict | None = None,
    source_text: str | None = None,
) -> dict:
    """cards＋归并终稿＋地点归并 → graph/6 图谱（含 meta.warnings 与 layout）。"""
    w = _Warnings()

    # ── 0) 卡片归一（缺失/畸形降级）──
    norm: dict[str, dict] = {}
    missing = 0
    for no in range(1, chapter_count + 1):
        card = cards.get(str(no))
        if isinstance(card, dict):
            norm[str(no)] = card
        else:
            norm[str(no)] = {}
            missing += 1
    w.count("card_missing", missing, f"{missing} 章无卡片数据（按空卡降级出图）")

    chars = [c for c in _dicts(_prod(products, "characters").get("characters")) if _clean(c.get("name"))]
    char_by_name = {_clean(c["name"]): c for c in chars}
    world = _prod(products, "world")
    foreshadow = _prod(products, "foreshadow")
    rels = _prod(products, "relations")
    rel_edges = _dicts(rels.get("edges"))
    arc_list = _dicts(_prod(products, "mainplot").get("arcs"))

    # ── 1) 在场归一（who/where/t；空串→null）──
    presence_by_ch: dict[int, list[dict]] = {}
    for no_s, card in norm.items():
        entries: list[dict] = []
        for p in _dicts(card.get("presence")):
            who = _clean(p.get("who"))
            if not who:
                continue
            where = p.get("where")
            where = None if where in (None, "", "原文未明确") else _clean(where)
            entry: dict = {"who": who, "where": where}
            if p.get("t") in _TIME_TAGS:
                entry["t"] = p["t"]
            entries.append(entry)
        presence_by_ch[int(no_s)] = entries

    # ── 2) 实体名收集（人物/势力/地点）与 id 分配 ──
    person_names = set(char_by_name)
    for entries in presence_by_ch.values():
        for e in entries:
            person_names.add(e["who"])

    faction_names = {_clean(f.get("name")) for f in _dicts(world.get("factions"))}
    faction_names |= {_clean(f.get("name")) for f in _dicts(rels.get("factions"))}
    faction_names.discard("")

    item_names: set[str] = set()
    auto_nodes = 0
    for e in rel_edges:
        kind = _clean(e.get("rel_type"))
        for end_key in ("from", "to"):
            nm = _clean(e.get(end_key))
            if not nm or nm in person_names or nm in faction_names:
                continue
            if kind in _ITEM_KINDS:
                item_names.add(nm)
            else:
                person_names.add(nm)
                auto_nodes += 1
    w.count("node_autocreated", auto_nodes, f"{auto_nodes} 个关系端点不在性格册，按名补立人物户")

    # 地点名册：place_merge 优先，union 卡片引用补户
    pm = place_merge if isinstance(place_merge, dict) else {}
    place_entries: dict[str, dict] = {}
    for p in _dicts(pm.get("places")):
        name = _clean(p.get("name"))
        if name:
            place_entries[name] = {
                "aliases": [_clean(a) for a in (p.get("aliases") or []) if isinstance(a, str) and _clean(a)],
                "parent": _clean(p.get("parent")),
                "note": _clean(p.get("note")),
            }
    place_ref: dict[int, set[str]] = {no: set() for no in presence_by_ch}
    for no_s, card in norm.items():
        no = int(no_s)
        for pl in _dicts(card.get("places")):
            nm = _clean(pl.get("name"))
            if nm:
                place_ref.setdefault(no, set()).add(nm)
        for e in presence_by_ch.get(no, []):
            if e["where"]:
                place_ref.setdefault(no, set()).add(e["where"])
    auto_places = 0
    for refs in place_ref.values():
        for nm in refs:
            if nm not in place_entries:
                place_entries[nm] = {"aliases": [], "parent": "", "note": ""}
                auto_places += 1
    w.count("place_autocreated", auto_places, f"{auto_places} 个地点未在归并名册中，按卡片原名立户（未归并）")
    for name, entry in list(place_entries.items()):
        pname = entry["parent"]
        if pname and pname not in place_entries:
            place_entries[pname] = {"aliases": [], "parent": "", "note": "（由 parent 引用立户）"}

    alias_to_name: dict[str, str] = {}
    for name, entry in place_entries.items():
        alias_to_name.setdefault(name, name)
        for a in entry["aliases"]:
            alias_to_name.setdefault(a, name)

    place_id = _assign_ids(list(place_entries), "p")

    def _place_of(name: str) -> str | None:
        return place_id.get(alias_to_name.get(name, name))

    # 首现＝min(引用章) 代码盖章；纯 parent 户继承子代最早章
    place_first: dict[str, int | None] = {}
    for name in place_entries:
        chs = [no for no, refs in place_ref.items()
               if name in refs or any(_place_of(x) == place_id[name] for x in refs)]
        place_first[name] = min(chs) if chs else None
    for name in place_entries:
        if place_first[name] is None:
            kids = [place_first[k] for k, v in place_entries.items() if v["parent"] == name and place_first.get(k)]
            place_first[name] = min(kids) if kids else None
    first_by_pid = {place_id[nm]: (place_first[nm] or _BIG) for nm in place_entries}

    # parent 解析＋环检测（有环边降 null 留痕）
    place_parent: dict[str, str | None] = {}
    for name, entry in place_entries.items():
        pname, seen = entry["parent"], {name}
        ok = True
        while pname:
            if pname in seen:
                ok = False
                break
            seen.add(pname)
            pname = place_entries.get(pname, {}).get("parent", "")
        if not ok:
            w.add("parent_cycle_dropped", f"parent 成环，{name} 的归属边降级置空", place=name)
            place_parent[name] = None
        else:
            place_parent[name] = place_id.get(entry["parent"]) if entry["parent"] else None

    person_id = _assign_ids(list(person_names), "n")
    faction_id = _assign_ids(list(faction_names), "f")
    item_id = _assign_ids(list(item_names), "i")

    def resolve_any(name: str) -> str | None:
        return person_id.get(name) or faction_id.get(name) or item_id.get(name)

    # ── 3) 节点 ──
    appear: dict[str, set[int]] = {nm: set() for nm in person_id}
    for nm, c in char_by_name.items():
        ch = _as_ch(c.get("evidence_ch"))
        if ch:
            appear[nm].add(ch)
    for no, entries in presence_by_ch.items():
        for e in entries:
            appear.setdefault(e["who"], set()).add(no)

    rel_fac_members: dict[str, set[str]] = {}
    for f in _dicts(rels.get("factions")):
        nm = _clean(f.get("name"))
        if nm in faction_id:
            rel_fac_members.setdefault(nm, set()).update(_clean(m) for m in (f.get("members") or []) if _clean(m))
    fac_appear: dict[str, set[int]] = {nm: set() for nm in faction_id}
    for no, entries in presence_by_ch.items():
        present = {e["who"] for e in entries}
        for fac, members in rel_fac_members.items():
            if present & members:
                fac_appear[fac].add(no)

    nodes: list[dict] = []
    for nm in sorted(person_id, key=lambda x: (_ROLE_ORDER.get(_clean(char_by_name.get(x, {}).get("role")), 9), x)):
        c = char_by_name.get(nm, {})
        node: dict = {"id": person_id[nm], "type": "person", "label": nm}
        if _clean(c.get("role")) in _ROLE_ORDER:
            node["role"] = _clean(c.get("role"))
        ap = sorted(appear.get(nm, set()))
        if ap:
            node["appear"] = ap
        bio = _clean(c.get("plot")) or _clean(c.get("background"))
        if bio:
            node["bio"] = bio[:120]
        nodes.append(node)
    for nm in sorted(faction_id):
        node = {"id": faction_id[nm], "type": "faction", "label": nm}
        ap = sorted(fac_appear.get(nm, set()))
        if ap:
            node["appear"] = ap
        nodes.append(node)
    for nm in sorted(item_id):
        nodes.append({"id": item_id[nm], "type": "item", "label": nm})

    places_out = [
        {"id": place_id[nm], "label": nm, "parent": place_parent.get(nm),
         "ch": place_first.get(nm) or 1, "note": place_entries[nm]["note"]}
        for nm in sorted(place_entries, key=lambda x: (first_by_pid[place_id[x]], x))
    ]

    # ── 4) presence → chapters（who/at 派生）──
    where_unresolved = 0
    ch_who: dict[int, set[str]] = {}
    chapters_out: list[dict] = []
    for no in range(1, chapter_count + 1):
        presence_out: list[dict] = []
        who_ids: list[str] = []
        at_ids: list[str] = []
        for e in presence_by_ch.get(no, []):
            pid = person_id.get(e["who"])
            if pid is None:
                continue
            wid = _place_of(e["where"]) if e["where"] else None
            if e["where"] and wid is None:
                where_unresolved += 1
            entry: dict = {"who": pid, "where": wid}
            if e.get("t"):
                entry["t"] = e["t"]
            presence_out.append(entry)
            if pid not in who_ids:
                who_ids.append(pid)
            if wid and wid not in at_ids:
                at_ids.append(wid)
        ch_who[no] = set(who_ids)
        chapters_out.append({
            "no": no, "beat": _clean(norm[str(no)].get("summary"))[:120],
            "at": at_ids, "who": who_ids, "presence": presence_out,
        })
    w.count("presence_where_unresolved", where_unresolved,
            f"{where_unresolved} 条在场的地点名无法解析，where 置 null（未知区）")

    # ── 5) events＝mainplot arcs 投影 ──
    events_out: list[dict] = []
    arc_ranges: list[tuple[str, int, int]] = []
    arcs_bad = 0
    for i, arc in enumerate(arc_list, start=1):
        title = _clean(arc.get("title"))
        start, end = _as_ch(arc.get("ch_start")), _as_ch(arc.get("ch_end"))
        if not title or start is None or end is None:
            arcs_bad += 1
            continue
        start, end = max(1, min(start, end)), min(chapter_count, max(start, end))
        if start > end:
            arcs_bad += 1
            continue
        summary = _clean(arc.get("summary"))
        in_range: set[str] = set()
        for no in range(start, end + 1):
            in_range |= ch_who.get(no, set())
        if summary:
            mentioned = {pid for nm, pid in person_id.items() if nm in summary}
            members = sorted(in_range & mentioned) or sorted(in_range)
        else:
            members = sorted(in_range)
        counts: dict[str, int] = {}
        first_seen: dict[str, int] = {}
        for no in range(start, end + 1):
            for e in presence_by_ch.get(no, []):
                wid = _place_of(e["where"]) if e["where"] else None
                if wid:
                    counts[wid] = counts.get(wid, 0) + 1
                    first_seen.setdefault(wid, no)
        at = min(counts, key=lambda x: (-counts[x], first_seen.get(x, _BIG), x)) if counts else None
        eid = f"e{i}"
        events_out.append({"id": eid, "title": title, "ch": [start, end], "at": at,
                           "members": members, "note": summary})
        arc_ranges.append((eid, start, end))
    w.count("arcs_invalid", arcs_bad, f"{arcs_bad} 条主线弧段字段不齐，已跳过")
    if arc_list and not events_out:
        w.add("events_empty", "主线弧段全部无效，events 为空数组（契约保形）")

    def ev_of(no: int) -> str | None:
        for eid, s, e in arc_ranges:
            if s <= no <= e:
                return eid
        return None
    for ch in chapters_out:
        ch["ev"] = ev_of(ch["no"])

    # ── 6) edges（kind 封闭表校验＋w 共场派生＋quote 回验）──
    edge_rejected = ch_missing = quote_failed = 0
    norm_text = _norm(source_text) if source_text else None
    edges_out: list[dict] = []
    for e in rel_edges:
        fid = resolve_any(_clean(e.get("from")))
        tid = resolve_any(_clean(e.get("to")))
        if not fid or not tid:
            edge_rejected += 1
            continue
        raw_kind = _clean(e.get("rel_type"))
        if raw_kind in _FLAT_KINDS:
            kind, raw = raw_kind, ""
        elif raw_kind in ("其他", ""):
            kind, raw = "自定义", _clean(e.get("raw")) or _clean(e.get("note")) or "未命名关系"
        else:
            edge_rejected += 1
            continue
        ch = _as_ch(e.get("evidence_ch"))
        if ch is None:
            ch_missing += 1
            continue
        quote = _clean(e.get("quote"))
        if quote and norm_text is not None and _norm(quote) not in norm_text:
            quote = ""
            quote_failed += 1
        common = sum(1 for who in ch_who.values() if fid in who and tid in who)
        edge: dict = {"from": fid, "to": tid, "kind": kind, "ch": max(1, ch), "w": max(1, common)}
        if raw:
            edge["raw"] = raw[:120]
        if quote:
            edge["quote"] = quote[:200]
        edges_out.append(edge)
    w.count("edge_rejected", edge_rejected, f"{edge_rejected} 条边因端点无法解析或 kind 不在封闭表被拒")
    w.count("edge_ch_missing", ch_missing, f"{ch_missing} 条边缺证据章号被拒")
    w.count("quote_unverified", quote_failed, f"{quote_failed} 条 quote 未通过原文回验，已剥除（关系保留）")

    # ── 7) links：presence 派生「到过」基线＋归并升级 ──
    baseline: dict[tuple[str, str], dict] = {}
    for no, entries in presence_by_ch.items():
        for e in entries:
            if not e["where"]:
                continue
            pid = person_id.get(e["who"])
            wid = _place_of(e["where"])
            if not pid or not wid:
                continue
            key = (pid, wid)
            if key not in baseline:
                baseline[key] = {"who": pid, "where": wid, "kind": "到过", "ch": no}
            else:
                baseline[key]["ch"] = min(baseline[key]["ch"], no)
    links_map = dict(baseline)
    up_bad = 0
    for l in _dicts(pm.get("links")):
        pid = person_id.get(_clean(l.get("who")))
        wid = _place_of(_clean(l.get("where")))
        kind = _clean(l.get("kind"))
        if not pid or not wid or kind not in _UPGRADE_KINDS:
            up_bad += 1
            continue
        ch = _as_ch(l.get("ch"))
        if ch is None or not (1 <= ch <= chapter_count):
            base = links_map.get((pid, wid))
            if not base:
                up_bad += 1
                continue
            ch = base["ch"]
        link: dict = {"who": pid, "where": wid, "kind": kind, "ch": ch}
        ev = _clean(l.get("evidence"))
        if ev:
            link["quote"] = ev[:200]
        links_map[(pid, wid)] = link
    w.count("place_link_invalid", up_bad, f"{up_bad} 条人—地升级条目无法解析，已忽略")
    links_out = [links_map[k] for k in sorted(links_map)]

    # ── 8) hooks ──
    hooks_out: list[dict] = []
    hooks_bad = 0
    for h in _dicts(foreshadow.get("hooks")):
        desc = _clean(h.get("desc"))
        plant = _as_ch(h.get("plant_ch")) if h.get("plant_ch") not in (None, "", "原文未明确") else None
        if not desc or plant is None:
            hooks_bad += 1
            continue
        payoff = _as_ch(h.get("payoff_ch")) if h.get("payoff_ch") not in (None, "", "原文未明确") else None
        hooks_out.append({"desc": desc[:120], "plant": max(1, plant),
                          "payoff": payoff, "status": "已收" if payoff else "未收"})
    w.count("hooks_invalid", hooks_bad, f"{hooks_bad} 条伏笔字段不齐，已跳过")

    # ── 9) meta ＋ layout（确定性：net 环形、scene 网格＋父框并集）──
    presence_total = sum(len(ch["presence"]) for ch in chapters_out)
    presence_placed = sum(1 for ch in chapters_out for p in ch["presence"] if p["where"])
    meta = {
        "rule": META_RULE,
        "completion": {"chapters": chapter_count, "presence_total": presence_total,
                       "presence_placed": presence_placed},
        "warnings": w.items,
    }

    net_order = ([n["id"] for n in nodes if n["type"] == "person"]
                 + [n["id"] for n in nodes if n["type"] == "faction"]
                 + [n["id"] for n in nodes if n["type"] == "item"])
    net: dict[str, list[int]] = {}
    if net_order:
        if len(net_order) == 1:
            net[net_order[0]] = [430, 230]
        else:
            for i, nid in enumerate(net_order):
                ang = 2 * math.pi * i / len(net_order) - math.pi / 2
                net[nid] = [int(430 + 180 * math.cos(ang)), int(230 + 180 * math.sin(ang))]

    children: dict[str, list[str]] = {}
    for nm, entry in place_entries.items():
        if entry["parent"]:
            children.setdefault(entry["parent"], []).append(place_id[nm])
    leaves = sorted((pid for pid in place_id.values() if pid not in children),
                    key=lambda pid: (first_by_pid.get(pid, _BIG), pid))
    scene: dict[str, list[int]] = {}
    cw, chh, gap = 200, 140, 24
    for i, pid in enumerate(leaves):
        r, c = divmod(i, 4)
        scene[pid] = [20 + c * (cw + gap), 30 + r * (chh + gap), cw, chh]

    def _union(boxes: list[list[int]]) -> list[int] | None:
        if not boxes:
            return None
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
        return [x0 - 18, y0 - 30, (x1 - x0) + 36, (y1 - y0) + 48]

    for _ in range(len(place_entries) + 1):  # 自底向上迭代至收敛（纯确定性）
        changed = False
        for nm, entry in place_entries.items():
            p_id = place_id[entry["parent"]] if entry["parent"] else None
            if not p_id:
                continue
            kids = [pid for pid in children.get(entry["parent"], []) if pid in scene]
            box = _union([scene[pid] for pid in kids])
            if box and scene.get(p_id) != box:
                scene[p_id] = box
                changed = True
        if not changed:
            break
    for nm in place_entries:
        scene.setdefault(place_id[nm], [20, 30, cw, chh])

    return {
        "contract": "deconstruct-graph/6",
        "meta": meta,
        "book": book_name,
        "stats": {"chapters": chapter_count, "words": words},
        "logline": _clean(_prod(products, "intro").get("intro")) or (events_out[0]["note"] if events_out else ""),
        "relTypes": {**REL_TYPES, "_rule": REL_RULE, "_boundary": REL_BOUNDARY},
        "places": places_out,
        "nodes": nodes,
        "edges": edges_out,
        "links": links_out,
        "events": events_out,
        "chapters": chapters_out,
        "hooks": hooks_out,
        "layout": {"net": net, "scene": scene,
                   "note": "渲染器输入：确定性坐标（规则布局），可再生成，语义 lint 不校验"},
    }
