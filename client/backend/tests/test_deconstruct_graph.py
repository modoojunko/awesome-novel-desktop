"""图谱装配器单元（deconstruct/graph.py）——阶段三纯函数：id 盖章/派生/warnings/降级契约。

判例口径：模型只产文本与关系；章号/首现/who/at/到过基线/events 一律代码盖章或派生；
kind 封闭表校验（清单外拒入）；quote 原文回验（失败剥除留关系）；parent 环检测。
"""

from __future__ import annotations

from deconstruct.graph import assemble


def _card(summary="", places=None, presence=None, chars=None):
    return {"summary": summary, "intro": [], "genre": [], "world": [], "characters": chars or [],
            "relations": [], "mainplot": [], "structure": [], "style": [], "techniques": [],
            "foreshadow": [], "places": places or [], "presence": presence or []}


_CARDS = {
    "1": _card("渡口救恩", places=[{"name": "竹湾渡口", "parent": "青溪县", "note": "渡口"}],
               presence=[{"who": "林晚", "where": "竹湾渡口"}, {"who": "阿蓟", "where": "竹湾渡口"}]),
    "2": _card("柳家寄居", places=[{"name": "柳家小院", "parent": "青溪县", "note": ""}],
               presence=[{"who": "柳氏", "where": "柳家小院"}, {"who": "阿蓟", "where": ""}]),
}

_PM = {
    "places": [
        {"name": "青溪县", "aliases": [], "parent": "", "note": "主舞台"},
        {"name": "竹湾渡口", "aliases": ["渡口"], "parent": "青溪县", "note": "", "evidence_ch": "第1章"},
        {"name": "柳家小院", "aliases": [], "parent": "青溪县", "note": ""},
    ],
    "links": [{"who": "林晚", "where": "竹湾渡口", "kind": "据地", "evidence": "林晚世代摆渡", "ch": "第1章"}],
}

_SRC = "第1章 初见\n林晚在渡口救人。\n第2章 重逢\n柳氏收留阿蓟。"


def _products():
    return {
        "characters": {"data": {"characters": [
            {"name": "林晚", "role": "主角", "plot": "渡口救人", "evidence_ch": "第1章"},
            {"name": "阿蓟", "role": "配角", "plot": "受救", "evidence_ch": "第1章"},
            {"name": "柳氏", "role": "配角", "plot": "收留阿蓟", "evidence_ch": "第2章"},
            {"name": "裴衡", "role": "反派", "plot": "旧案主谋", "evidence_ch": "第1章"},
        ]}},
        "world": {"data": {"factions": [{"name": "盐帮", "note": "私盐"}]}},
        "relations": {"data": {
            "edges": [
                {"from": "林晚", "to": "阿蓟", "rel_type": "恩义", "evidence_ch": "第1章", "quote": "林晚在渡口救人"},
                {"from": "裴衡", "to": "盐帮", "rel_type": "主从", "evidence_ch": "第1章"},
                {"from": "林晚", "to": "阿蓟", "rel_type": "作证", "evidence_ch": "第2章"},
                {"from": "林晚", "to": "神秘罗盘", "rel_type": "持有", "evidence_ch": "第2章"},
                {"from": "裴衡", "to": "柳氏", "rel_type": "宿怨", "evidence_ch": "第2章"},
                {"from": "林晚", "to": "柳氏", "rel_type": "其他", "raw": "点头之交", "evidence_ch": "第2章"},
            ],
            "factions": [{"name": "盐帮", "members": ["裴衡"], "stance": "受驱使"}],
        }},
        "mainplot": {"data": {"arcs": [{"title": "救恩", "ch_start": 1, "ch_end": 2,
                                        "summary": "林晚救阿蓟，牵出旧案", "confidence": "high"}]}},
        "foreshadow": {"data": {"hooks": [{"desc": "罗盘", "plant_ch": "第1章", "payoff_ch": None}]}},
        "intro": {"data": {"intro": "渡口救人牵旧案"}},
    }


def _g(**over):
    kw = {"book_name": "雪落无声", "chapter_count": 2, "words": 100, "cards": _CARDS,
          "products": _products(), "place_merge": _PM, "source_text": _SRC}
    kw.update(over)
    return assemble(**kw)


def _kinds(g, kind):
    return [w for w in g["meta"]["warnings"] if w["kind"] == kind]


def _lbl_pid(g):
    return {n["label"]: n["id"] for n in g["nodes"]}


def _lbl_wid(g):
    return {p["label"]: p["id"] for p in g["places"]}


def test_assemble_core():
    g = _g()
    assert g["contract"] == "deconstruct-graph/6"
    assert g["logline"] == "渡口救人牵旧案"  # intro 终稿派生
    pid, wid = _lbl_pid(g), _lbl_wid(g)

    # places：归属解析＋首现盖章
    dukou = next(p for p in g["places"] if p["label"] == "竹湾渡口")
    assert dukou["parent"] == wid["青溪县"] and dukou["ch"] == 1
    assert next(p for p in g["places"] if p["label"] == "柳家小院")["ch"] == 2

    # nodes：人物角色/势力/物品（物属边端点自动立户）
    assert pid["林晚"] and next(n for n in g["nodes"] if n["label"] == "林晚")["role"] == "主角"
    assert next(n for n in g["nodes"] if n["label"] == "神秘罗盘")["type"] == "item"
    assert next(n for n in g["nodes"] if n["label"] == "盐帮")["type"] == "faction"

    # edges：封闭表校验＋quote 回验＋w 共场派生
    kinds = {e["kind"] for e in g["edges"]}
    assert {"恩义", "主从", "持有", "自定义"} <= kinds
    assert "作证" not in kinds and "宿怨" not in kinds  # 动作词/清单外拒入
    en = next(e for e in g["edges"] if e["kind"] == "恩义")
    assert en["from"] == pid["林晚"] and en["to"] == pid["阿蓟"]
    assert en["ch"] == 1 and en["w"] == 1 and en["quote"] == "林晚在渡口救人"
    assert next(e for e in g["edges"] if e["kind"] == "自定义")["raw"] == "点头之交"

    # links：到过基线＋归并升级
    lk = {(l["who"], l["where"]): l for l in g["links"]}
    assert lk[(pid["林晚"], wid["竹湾渡口"])]["kind"] == "据地"
    assert lk[(pid["林晚"], wid["竹湾渡口"])]["quote"] == "林晚世代摆渡"
    assert lk[(pid["阿蓟"], wid["竹湾渡口"])]["kind"] == "到过"

    # chapters：who/at 派生；空 where → null（未知区）
    ch2 = g["chapters"][1]
    aji_entry = next(p for p in ch2["presence"] if p["who"] == pid["阿蓟"])
    assert aji_entry["where"] is None
    assert set(ch2["who"]) == {pid["柳氏"], pid["阿蓟"]}  # 柳氏在院；阿蓟在场未定位（where=null）

    # events：arcs 投影（at=区间众数；members=区间在场∩提及名）
    ev = g["events"][0]
    assert ev["ch"] == [1, 2] and ev["at"] == wid["竹湾渡口"]
    assert set(ev["members"]) == {pid["林晚"], pid["阿蓟"]}
    assert [c["ev"] for c in g["chapters"]] == ["e1", "e1"]

    # hooks 与 meta 完成度
    assert g["hooks"][0]["status"] == "未收" and g["hooks"][0]["plant"] == 1
    assert g["meta"]["completion"] == {"chapters": 2, "presence_total": 4, "presence_placed": 3}

    # warnings：两类拒边聚合
    assert _kinds(g, "edge_rejected")[0]["count"] == 2
    assert not _kinds(g, "quote_unverified")

    # layout：net 全节点、scene 全地点（父框并集包含子框）
    assert set(g["layout"]["net"]) == {n["id"] for n in g["nodes"]}
    assert set(g["layout"]["scene"]) == set(wid.values())


def test_parent_cycle_dropped():
    pm = {"places": [
        {"name": "甲地", "aliases": [], "parent": "乙地", "note": ""},
        {"name": "乙地", "aliases": [], "parent": "甲地", "note": ""},
    ], "links": []}
    cards = {"1": _card("开场", places=[{"name": "甲地", "parent": "乙地", "note": ""}],
                        presence=[{"who": "林晚", "where": "甲地"}])}
    g = _g(cards=cards, place_merge=pm, chapter_count=1)
    assert _kinds(g, "parent_cycle_dropped"), "成环须留痕"
    assert all(p["parent"] is None for p in g["places"]), "环上归属全部降级置空"


def test_quote_unverified_stripped():
    g = _g(source_text="第1章 初见\n河水冰冷。\n第2章 重逢\n无。")
    en = next(e for e in g["edges"] if e["kind"] == "恩义")
    assert "quote" not in en, "回验失败须剥 quote 留关系"
    assert _kinds(g, "quote_unverified")[0]["count"] == 1


def test_place_autocreated_when_merge_missing():
    g = _g(place_merge=None)
    assert _kinds(g, "place_autocreated"), "无归并产物时按卡片原名立户留痕"
    assert any(p["label"] == "竹湾渡口" for p in g["places"])


def test_card_missing_degraded():
    cards = {"1": _CARDS["1"]}  # 第2章缺卡
    g = _g(cards=cards)
    assert _kinds(g, "card_missing")[0]["count"] == 1
    assert g["chapters"][1]["presence"] == [] and g["chapters"][1]["beat"] == ""
