"""拆书产物 → 知识库映射/收录（c-kb-import）测试。

映射口径按真机产物形状（pipeline 写的 {dim: {file, data}}）钉死：
techniques.data=reader_needs/techniques/borrowable/avoid、style.data=role/rules/craft/
examples/taboo、world.data=no_power/stage/power/cost/history/factions/constraints/extra、
characters.data.characters[]、genre.data.genre。
"""

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select as sel

from db import async_session
from kb.deconstruct_import import (
    collect_task_to_kb,
    genre_from_products,
    map_deconstruct_products,
)
from kb.payloads import validate_payload
from models.kb import KbEntry, KbEntryTag, KbKnowledge, KbLibrary

PRODUCTS = {
    "genre": {"file": "题材.md", "data": {"genre": "灵异志怪", "tags": ["灵异"]}},
    "intro": {"file": "简介.md", "data": {"intro": "夜班公交撞鬼"}},
    "techniques": {
        "file": "写作技法.md",
        "data": {
            "reader_needs": [
                {
                    "need": "在庸常生活里体验可控的恐怖",
                    "how": "把公交夜班、面馆等日常场景作为灵异舞台",
                    "example": "夜班车过水库，李耀盯着水面看了很久才踩油门",
                    "evidence_ch": "第2章",
                    "transferable": "都市题材通用",
                }
            ],
            "techniques": [
                {
                    "name": "信息差递进式强派任务",
                    "emotion_chain": "放松—意外—不安—恐惧",
                    "repro_steps": ["先抛补助诱人", "再补一句是个夜班"],
                    "swappable": "任务类型可换",
                    "no_copy": "原作的司机—水库组合不可照搬",
                    "example": "先给补助再补一句是个夜班",
                    "evidence_ch": "第1章",
                    "confidence": "high",
                }
            ],
            "borrowable": [
                {"item": "以日常场景作为灵异舞台", "evidence_ch": "第2章", "note": "",
                 "example": "面馆老板擦杯子时说今晚别接末班车"}
            ],
            "avoid": [
                {"item": "中段密集使用同一句式", "evidence_ch": "第98章", "note": "死法疲劳",
                 "example": "连用三次『今晚的月亮像盘子』"}
            ],
        },
    },
    "style": {
        "file": "写作文风.md",
        "data": {
            "role": "第一人称限知，紧贴司机",
            "rules": [
                {"name": "口语自述", "how": "用第一人称口语叙述，夹杂自嘲", "evidence_ch": "第1章"}
            ],
            "craft": [{"name": "感官堆叠", "how": "叠加声音、气味与触感"}],
            "examples": [
                {"example": "我三十出头，是一个公交车司机。\n　　在公司车队里，也是最年轻的司机。", "evidence_ch": "第1章"}
            ],
            "taboo": [{"name": "长段静描", "how": "不用整页环境描写"}],
        },
    },
    "world": {
        "file": "世界设定.md",
        "data": {
            "no_power": "存在大量民间法术、邪祟与鬼魂规则",
            "stage": "以东北某城市及郊区为主舞台",
            "power": [{"name": "13路末班车诅咒", "rule": "十年一换司机、与司机绑定契约"}],
            "cost": [{"name": "司机契约", "rule": "继续开车必死之信"}],
            "history": [{"name": "十年前车祸", "note": "三任司机载人冲入水库"}],
            "factions": [{"name": "13路车队", "note": "队长强派夜班"}],
            "constraints": [{"name": "天黑锁门", "note": "活物在外过夜必死"}],
            "extra": [{"key": "黑色手链", "value": "刘云波所赠保平安之物"}],
        },
    },
    "characters": {
        "file": "角色设定.md",
        "data": {
            "characters": [
                {
                    "name": "李耀",
                    "aliases": ["我", "小李"],
                    "role": "主角",
                    "persona": "十三路末班车司机，胆小多疑却重情执拗",
                    "gender": "男",
                    "age": "三十出头",
                    "look": "原文未明确",
                    "speech": "话少孤僻，嘴硬爱吐槽",
                    "background": "被队长强派13路夜班",
                    "plot": "第1章被强派夜班",
                    "evidence_ch": "第2章",
                }
            ]
        },
    },
    "mainplot": {"file": "主线剧情.md", "data": {"fullstory": "追查十年前车祸真相"}},
    "structure": {"file": "章卷结构.md", "data": {"volumes": []}},
}


def _map(products=None, genre="", src_ref=None):
    return map_deconstruct_products(
        "u-map", "task-1", genre, products if products is not None else PRODUCTS,
        src_ref=src_ref,
    )


def test_genre_from_products_normalizes_catalog_name():
    assert genre_from_products(PRODUCTS) == "志怪/民俗灵异"
    assert genre_from_products({}) == ""


def test_maps_real_product_shapes_into_five_concepts():
    entries, warnings = _map(genre="志怪/民俗灵异")
    assert warnings == ["原文示范段 1 条不入库（逐字原文，版权红线）"]  # 原文示范段不收
    by_concept: dict[str, list[KbEntry]] = {}
    for entry in entries:
        by_concept.setdefault(entry.concept, []).append(entry)
        assert entry.src_kind == "deconstruct"
        assert entry.src_ref == "task-1"
        assert entry.genre == "志怪/民俗灵异"
        assert "\n" not in entry.instruction  # 写法块结构消毒：指令必须单行
        # 知识文案第一要求：念得通顺——句末必须收口
        assert entry.instruction.endswith(("。", "！", "？", "…")), entry.instruction
        # 每条 payload 必须过消费端强校验（选择器/写法块读的就是这些键）
        validate_payload(entry.concept, json.loads(entry.payload_json))

    # 手法：techniques 1 + borrowable 1 + avoid 1 + reader_needs 1
    assert len(by_concept["手法"]) == 4
    # 文风：role 1 + rules 1（场景规则归文风——boss 承接表）；文笔：craft 1 + taboo 1
    assert len(by_concept["文风"]) == 2
    assert len(by_concept["文笔"]) == 2
    # 世界：stage + no_power + power + cost + history + factions + constraints + extra
    assert len(by_concept["世界设定"]) == 8
    assert len(by_concept["角色设定"]) == 1
    # 情节消费链未建：mainplot/structure 不收
    assert "情节" not in by_concept


def test_technique_payload_carries_steps_and_evidence():
    entries, _ = _map()
    tech = next(e for e in entries if e.title == "信息差递进式强派任务" and e.concept == "手法")
    payload = json.loads(tech.payload_json)
    assert payload["scene"] == "日常"
    assert payload["steps"] == ["先抛补助诱人", "再补一句是个夜班"]
    assert payload["confidence"] == "high"
    assert "第1章" in tech.evidence
    assert tech.negative_example.startswith("原作的司机")


def test_technique_every_entry_carries_example():
    """boss 2026-11-08：每个手法都要求要有原文的案例——四族条目全带 example。"""
    entries, _ = _map()
    techs = [e for e in entries if e.concept == "手法"]
    assert len(techs) == 4
    assert all(e.example.strip() for e in techs), [
        (e.title, e.example) for e in techs if not e.example.strip()
    ]
    # 读者需求：新契约 example 优先于 transferable
    need = next(e for e in techs if e.title.startswith("读者需求"))
    assert "水库" in need.example and need.example != "都市题材通用"
    # 评审 P2：证据串与主卡同语义——quote 源是原文例，不是 note 理由
    bor = next(e for e in techs if e.title == "以日常场景作为灵异舞台")
    assert "面馆老板" in bor.evidence
    avo = next(e for e in techs if e.title.startswith("避免："))
    assert "月亮像盘子" in avo.evidence


def test_reader_needs_example_falls_back_to_transferable():
    """老产物（无 example）读者需求回落 transferable，不回归。"""
    old = json.loads(json.dumps(PRODUCTS))
    del old["techniques"]["data"]["reader_needs"][0]["example"]
    entries, _ = _map(products=old)
    need = next(e for e in entries if e.concept == "手法" and e.title.startswith("读者需求"))
    assert need.example == "都市题材通用"


def test_world_constraints_use_singular_part_and_hard_flag():
    entries, _ = _map()
    hard = next(e for e in entries if e.concept == "世界设定" and "天黑锁门" in e.title)
    payload = json.loads(hard.payload_json)
    assert payload["part"] == "constraint"
    assert payload["hard"] is True
    # 2026-11-08 结构化：名字/内容分立（title=name、instruction=名字：内容）
    assert payload["name"] == "天黑锁门"
    assert payload["content"] == "活物在外过夜必死"
    assert hard.instruction == "天黑锁门：活物在外过夜必死。"  # _mk_entry 句末收口补句号
    # 兜底分区名不会被写成非法的 constraints
    worlds = [json.loads(e.payload_json) for e in entries if e.concept == "世界设定"]
    assert all(w["part"] != "constraints" for w in worlds)

def test_style_rules_and_craft_structured_fields():
    """文风规则/文笔写法：name/how/章证据/可信度分立（boss 2026-11-08「数据不行」拍板）。"""
    import copy
    products = copy.deepcopy(PRODUCTS)
    products["style"]["data"]["rules"] = [{
        "name": "战斗短句", "how": "战斗场面短句连发。（第76、198章；confidence:high）",
    }]
    products["style"]["data"]["craft"] = [{
        "name": "具象比喻", "how": "用现实物象比喻超常事物。（第377章；confidence:mid）",
    }]
    entries, _ = map_deconstruct_products("u", "t", "都市", products)
    rule = next(e for e in entries if e.concept == "文风" and e.title == "战斗短句")
    rp = json.loads(rule.payload_json)
    assert rp["name"] == "战斗短句"
    assert rp["how"] == "战斗场面短句连发。", rp["how"]  # 正文净化：锚与可信度剥出
    assert rp["evidence_ch"] == "第76、198章"
    assert rp["confidence"] == "high"
    craft = next(e for e in entries if e.concept == "文笔" and e.title == "具象比喻")
    cp = json.loads(craft.payload_json)
    assert cp["name"] == "具象比喻"
    assert cp["how"] == "用现实物象比喻超常事物。"
    assert cp["evidence_ch"] == "第377章"
    assert cp["confidence"] == "mid"

def test_world_metadata_stripped_from_content_into_fields():
    """正文粘尾的章证据/可信度剥出分立（「（第41章；confidence:mid）」实锤）。"""
    import copy
    products = copy.deepcopy(PRODUCTS)
    products["world"]["data"]["constraints"] = [{
        "name": "夜半不出警",
        "note": "怀远路派出所内部规矩。（第41章；confidence:mid）",
    }]
    entries, _ = map_deconstruct_products("u", "t", "都市", products)
    row = next(e for e in entries if e.concept == "世界设定" and "夜半不出警" in e.title)
    payload = json.loads(row.payload_json)
    assert payload["content"] == "怀远路派出所内部规矩。", payload["content"]
    assert "第" not in payload["content"] and "confidence" not in payload["content"]
    assert payload["evidence_ch"] == "第41章"  # 锚内可信度提出后留纯章号
    assert payload["confidence"] == "mid"
    assert row.instruction == "夜半不出警：怀远路派出所内部规矩。"


def test_world_open_anchor_without_closing_paren_stripped():
    """残形锚（缺右括号「（第115、116章。」吞尾剥出）——真机 13路 81/168 条实锤。"""
    import copy
    products = copy.deepcopy(PRODUCTS)
    products["world"]["data"]["constraints"] = [{
        "name": "寡妇庙禁地",
        "note": "村中禁地，寡妇在此上吊。（第115、116、117、118章。",
    }]
    entries, _ = map_deconstruct_products("u", "t", "都市", products)
    row = next(e for e in entries if e.concept == "世界设定" and "寡妇庙" in e.title)
    payload = json.loads(row.payload_json)
    assert payload["content"] == "村中禁地，寡妇在此上吊。", payload["content"]
    assert "第115" in payload["evidence_ch"]

def test_character_payload_keeps_persona_and_aliases():
    entries, _ = _map()
    char = next(e for e in entries if e.concept == "角色设定")
    payload = json.loads(char.payload_json)
    assert payload["archetype"] == "李耀"
    assert payload["persona"].startswith("十三路末班车司机")
    assert payload["aliases"] == ["我", "小李"]
    assert payload["role"] == "主角"
    # 证据＝产物 evidence_ch（不再是静态「拆书·角色设定」标签）
    assert char.evidence == "第2章"


def test_character_evidence_sentinel_and_missing_stay_empty():
    # 「原文未明确」哨兵不进 _ev（否则包成「第原文未明确章」）；缺失同样留空
    products = json.loads(json.dumps(PRODUCTS))
    products["characters"]["data"]["characters"][0]["evidence_ch"] = "原文未明确"
    entries, _ = _map(products)
    char = next(e for e in entries if e.concept == "角色设定")
    assert char.evidence == ""

    products["characters"]["data"]["characters"][0].pop("evidence_ch")
    entries, _ = _map(products)
    char = next(e for e in entries if e.concept == "角色设定")
    assert char.evidence == ""


def test_src_ref_override_keeps_task_id_default():
    entries, _ = _map(src_ref="book:abc123")
    assert entries and all(e.src_ref == "book:abc123" for e in entries)
    default_entries, _ = _map()
    assert all(e.src_ref == "task-1" for e in default_entries)


def test_long_instructions_are_single_lined_and_clamped():
    products = {
        "techniques": {
            "data": {
                "techniques": [
                    {
                        "name": "长句",
                        "repro_steps": ["一" * 200, "二" * 200],
                    }
                ]
            }
        }
    }
    entries, _ = _map(products)
    assert len(entries) == 1
    entry = entries[0]
    assert "\n" not in entry.instruction
    assert len(entry.instruction) <= 240


def _collect(uid, task, **kwargs):
    async def _run():
        async with async_session() as db:
            return await collect_task_to_kb(db, uid, task, **kwargs)

    return asyncio.run(_run())


def test_collect_is_idempotent_and_materializes_tags_and_libraries():
    uid = f"kb-batch-{uuid.uuid4()}"
    task = SimpleNamespace(
        id=f"task-{uuid.uuid4()}",
        user_id=uid,
        products_json=json.dumps(PRODUCTS, ensure_ascii=False),
    )

    first = _collect(uid, task)
    assert first["collected"] == first["total_mapped"] > 0
    assert first["skipped"] == 0
    assert first["genre"] == "志怪/民俗灵异"

    second = _collect(uid, task)
    assert second["collected"] == 0
    assert second["skipped"] == first["collected"]

    async def _counts():
        async with async_session() as db:
            rows = (
                await db.execute(sel(KbEntry).where(KbEntry.user_id == uid))
            ).scalars().all()
            tags = (
                await db.execute(sel(KbEntryTag).where(KbEntryTag.user_id == uid))
            ).scalars().all()
            libs = (
                await db.execute(sel(KbLibrary).where(KbLibrary.user_id == uid))
            ).scalars().all()
            return len(rows), len(tags), {(lib.genre, lib.concept) for lib in libs}

    entry_count, tag_count, libraries = asyncio.run(_counts())
    assert entry_count == first["collected"]

    async def _origin_check():
        async with async_session() as db:
            rows = (
                await db.execute(sel(KbEntry).where(KbEntry.user_id == uid))
            ).scalars().all()
            return {e.origin for e in rows}
    # c-kb-summarize：收录落素材行——不物化标签、不长默认库（素材不进选择器/星图）
    assert asyncio.run(_origin_check()) == {"material"}
    assert tag_count == 0
    assert ("志怪/民俗灵异", "手法") not in libraries


def test_collect_genre_override_and_src_ref():
    uid = f"kb-batch-{uuid.uuid4()}"
    task = SimpleNamespace(
        id=f"task-{uuid.uuid4()}",
        user_id=uid,
        products_json=json.dumps(PRODUCTS, ensure_ascii=False),
    )
    result = _collect(uid, task, genre_override="仙侠", src_ref="book:deadbeef")
    assert result["genre"] == "仙侠/修真"

    async def _rows():
        async with async_session() as db:
            return (
                await db.execute(sel(KbEntry).where(KbEntry.user_id == uid))
            ).scalars().all()

    rows = asyncio.run(_rows())
    assert rows and all(r.genre == "仙侠/修真" for r in rows)
    assert all(r.src_ref == "book:deadbeef" for r in rows)


def test_collect_rejects_empty_products():
    task = SimpleNamespace(id="t", user_id="u", products_json="{}")
    with pytest.raises(ValueError):
        _collect("u-empty", task)


def test_collect_dedupes_across_task_id_and_book_fingerprint_refs():
    """界面按 task_id 收过、脚本按书指纹再收：同一份产物不重复入库。"""
    uid = f"kb-batch-{uuid.uuid4()}"
    task = SimpleNamespace(
        id=f"task-{uuid.uuid4()}",
        user_id=uid,
        products_json=json.dumps(PRODUCTS, ensure_ascii=False),
    )
    first = _collect(uid, task)  # 界面口径：src_ref=task_id
    assert first["collected"] > 0

    second = _collect(uid, task, src_ref="book:abcdef0123456789")
    assert second["collected"] == 0
    assert second["skipped"] == first["collected"]


def test_mapping_when_scope_evidence_and_taboo_copy():
    """真机产物回归：when 只在有场面时收窄、证据章号不双包、忌用名不叠前缀。"""
    products = {
        "techniques": {
            "data": {
                "techniques": [
                    {
                        "name": "先声夺人",
                        "repro_steps": ["先压后放"],
                        "emotion_chain": "压抑—不安",
                        "evidence_ch": "第3章、第9章",
                    }
                ],
                "borrowable": [{"item": "用一句闲话起头", "evidence_ch": "第2章"}],
            }
        },
        "style": {
            "data": {"taboo": [{"name": "忌书面长句", "how": "拆短句", "evidence_ch": "第4章"}]}
        },
    }
    entries, _ = map_deconstruct_products("u-map", "task-x", "悬疑", products)
    by_title = {e.title: e for e in entries}

    tech = by_title["先声夺人"]
    when = json.loads(tech.when_json)
    assert "scene" not in when, "模型没给场面时不得硬填 scene"
    assert when.get("emotion") == "不安", "情绪仍要带上"
    assert tech.evidence.startswith("第3章"), tech.evidence
    assert "第第" not in tech.evidence

    borrow = by_title["用一句闲话起头"]
    assert json.loads(borrow.when_json) == {}, "借用套路保持全章适用"

    taboo = by_title["忌书面长句"]
    assert taboo.instruction.startswith("忌书面长句"), taboo.instruction
    assert "忌用·忌" not in taboo.instruction


def test_taboo_text_fits_payload_limit_after_prefix():
    """忌用前缀参与长度截断：不得因超 160 字被 payload 校验静默丢弃。"""
    products = {
        "style": {
            "data": {"taboo": [{"name": "长" * 40, "how": "短" * 140}]}
        }
    }
    entries, warnings = map_deconstruct_products("u-map", "task-y", "悬疑", products)
    assert entries, warnings
    payload = json.loads(entries[0].payload_json)
    assert len(payload["rule"]) <= 160
    assert entries[0].instruction.startswith("忌用·")


def test_collect_lands_material_not_knowledge_instances():
    """c-kb-summarize：收录落素材行（origin=material），不再建知识＋实例——
    实例与知识由总结管线采纳时产生（替代 81c59fbe「收录即建实例」口径）。"""
    from models.kb import KbKnowledgeInstance

    uid = f"kb-inst-{uuid.uuid4()}"
    task = SimpleNamespace(
        id=f"task-{uuid.uuid4()}",
        user_id=uid,
        products_json=json.dumps(PRODUCTS, ensure_ascii=False),
        book_name="13路末班车",
    )
    first = _collect(uid, task)
    assert first["collected"] > 0

    async def _check():
        async with async_session() as db:
            inst_rows = (
                await db.execute(
                    sel(KbKnowledgeInstance)
                    .join(KbKnowledge, KbKnowledge.id == KbKnowledgeInstance.knowledge_id)
                    .where(KbKnowledge.user_id == uid)
                )
            ).scalars().all()
            entries = (
                await db.execute(sel(KbKnowledge).where(KbKnowledge.user_id == uid))
            ).scalars().all()
            return len(inst_rows), {e.origin for e in entries}

    inst_count, origins = asyncio.run(_check())
    assert inst_count == 0, "收录 SHALL NOT 建实例——实例由总结采纳产生"
    assert origins == {"material"}, "收录产物全部落素材态"


def test_双前缀自愈_星币星币实锤形态():
    """boss 2026-11-09「星币：星币：…」实锤：旧映射 content 自带名字头时
    重复拼名——自愈把实例正文与知识行 instruction 去重。"""
    import asyncio
    from kb.migrate_library import dedupe_dual_prefix, heal_dual_prefix_instances

    assert dedupe_dual_prefix("星币：星币：吉尔伽美什使用后引发厄运延迟") == (
        "星币：吉尔伽美什使用后引发厄运延迟"
    )
    # heal 函数存在且可调（空账号零改动自熄）
    n = asyncio.run(heal_dual_prefix_instances(user_id="no-such-user"))
    assert n == 0
