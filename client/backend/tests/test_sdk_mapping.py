"""SDK 独立单测（c-knowledge-source-align 一期）：不经 C 端任何模块——
知识仓同法调 SDK，证明自包含（构建 CI 单仓可跑）。"""

import json
import sys
from pathlib import Path

import pytest

SDK_DIR = Path(__file__).resolve().parent.parent / "vendor_sdk"
sys.path.insert(0, str(SDK_DIR))

import novel_deconstruct_sdk as sdk  # noqa: E402, I001 — SDK 依赖 sys.path 注入，排序后置是有意行为


PRODUCTS = {
    "genre": {"file": "题材.md", "data": {"genre": "灵异志怪"}},
    "techniques": {
        "file": "写作技法.md",
        "data": {
            "techniques": [
                {
                    "name": "信息差强派任务",
                    "emotion_chain": "放松—意外—不安",
                    "repro_steps": ["先抛补助诱人", "再补一句是个夜班"],
                    "example": "先给补助再补一句是个夜班",
                    "evidence_ch": "第1章",
                    "confidence": "high",
                    "kind": "大招",
                }
            ],
            "borrowable": [{"item": "日常场景作灵异舞台", "example": "面馆老板擦杯子",
                            "evidence_ch": "第2章"}],
        },
    },
}


def test_sdk_自包含_全字段透传():
    entries, warnings = sdk.map_deconstruct_products("u1", "t1", "志怪/民俗灵异", PRODUCTS)
    assert warnings == [], warnings
    tech = entries[0]
    # EntryData 全字段（v2 口径：example/evidence/confidence/kind 透传）
    assert tech.example == "先给补助再补一句是个夜班", tech.example
    assert "第1章" in tech.evidence
    payload = json.loads(tech.payload_json)
    assert payload["confidence"] == "high" and payload["kind"] == "大招", payload
    assert payload["steps"] == ["先抛补助诱人", "再补一句是个夜班"]


def test_sdk_genre_归一_走SDK内词表():
    assert sdk.genre_from_products(PRODUCTS) == "志怪/民俗灵异"


def test_sdk_taxonomy_注入式():
    # CI 单仓无知识仓 sibling——树文件在才跑挂靠断言；不在＝零树口径（合法态）
    tree_path = Path(__file__).resolve().parents[4] / "awesome-novel-knowledge" / "taxonomy" / "taxonomy.json"
    if not tree_path.is_file():
        pytest.skip("无知识仓检出（CI 单仓）——零树降级口径单独验证")
    idx = sdk.TaxonomyIndex.from_file(tree_path)
    hit = idx.node_for("手法", "写法")
    assert hit and hit[0] == "tech_more", hit
    assert sdk.TaxonomyIndex.empty().node_for("手法", "写法") is None

def test_sdk_零树口径_空索引node_for返None():
    # 零内嵌降级：空索引（CDN 未同步/树缺位）node_for 恒 None——总结/提炼走自建
    idx = sdk.TaxonomyIndex.empty()
    assert idx.is_empty()
    assert idx.node_for("手法", "大招") is None
    assert idx.parent_chain("tech_more") == []


STYLE_QUOTE_PRODUCTS = {
    "style": {
        "file": "文风.md",
        "data": {
            "role": "第三人称限知",
            "rules": [
                # ① quote 进 evidence_json.quotes，loc 取条目章证据
                {"name": "短句对话", "how": "对峙用短句", "quote": "把刀放下。",
                 "evidence_ch": "第17章", "confidence": "high"},
                # ③ 无 quote → 无 quotes 键，evidence 走 evidence_ch 兜底
                {"name": "长句铺陈", "how": "铺垫用长句", "evidence_ch": "第18章"},
                # ⑤ 字符串型 rule（非 dict）不炸
                "裸串规则原样成条",
            ],
            # ② craft 无 evidence_ch → quotes[0].loc 空串；④ quote >200 截到 200
            "craft": [{"name": "感官堆叠", "how": "叠加声味触", "quote": "q" * 300,
                       "confidence": "mid"}],
        },
    },
}


def test_sdk_文风文笔_quote接入evidence():
    """例句口径翻案（boss 2026-11-10）：rules/craft/taboo 的 item.quote 进
    evidence_json.quotes 随条目走；无 quote 不产 quotes 键；异常形状不炸。"""
    entries, warnings = sdk.map_deconstruct_products("u1", "t1", "志怪/民俗灵异", STYLE_QUOTE_PRODUCTS)
    assert warnings == [], warnings
    by_title = {e.title: e for e in entries}

    rule = json.loads(by_title["短句对话"].evidence_json or "{}")
    assert rule.get("quotes") == [{"loc": "第17章", "text": "把刀放下。"}], rule
    assert "把刀放下。" in by_title["短句对话"].evidence

    assert "quotes" not in json.loads(by_title["长句铺陈"].evidence_json or "{}")
    assert "第18章" in by_title["长句铺陈"].evidence  # evidence_ch 兜底不丢

    craft = json.loads(by_title["感官堆叠"].evidence_json or "{}")
    q0 = craft["quotes"][0]
    assert q0["loc"] == "" and q0["text"] == "q" * 200, q0  # 无章号＋截 200

    assert any(e.title == "裸串规则原样成条" or e.title.startswith("场景规则")
               for e in entries), [e.title for e in entries]


def test_sdk_去冗余_拼装份与名字头():
    """2026-11-11 真机实锤：详情页 实例/内容/怎么写 三字段同值（payload 拼装份
    text 第三份拷贝）＋「温柔说狠话：温柔说狠话：」双前缀——rules payload 停写
    拼装份、how/content 自带名字头剥除。"""
    products = {
        "style": {"file": "文风.md", "data": {"rules": [
            {"name": "温柔说狠话", "how": "温柔说狠话：对话用礼貌温柔的语气包裹狠辣内容",
             "evidence_ch": "第3章", "confidence": "high"},
        ]}},
        "world": {"file": "世界.md", "data": {"extra": [
            # extra 路径 key：value 拼装会叠两层名字头——while 剥到纯案例
            {"key": "琥珀遗体", "value": "琥珀遗体：树脂封装遗体可高价出售",
             "evidence_ch": "第34章"},
        ]}},
    }
    entries, warnings = sdk.map_deconstruct_products("u1", "t1", "志怪/民俗灵异", products)
    assert warnings == [], warnings

    rule = next(e for e in entries if e.title == "温柔说狠话")
    payload = json.loads(rule.payload_json)
    assert "text" not in payload, payload  # 拼装份不落 payload
    assert payload["how"] == "对话用礼貌温柔的语气包裹狠辣内容", payload  # 名字头剥除
    assert rule.instruction.rstrip("。") == "温柔说狠话：对话用礼貌温柔的语气包裹狠辣内容", rule.instruction
    assert "温柔说狠话：温柔说狠话" not in rule.instruction

    world = next(e for e in entries if e.concept == "世界设定")
    wp = json.loads(world.payload_json)
    assert wp["content"] == "树脂封装遗体可高价出售", wp  # content 纯案例（双层头剥净）
    assert world.instruction.rstrip("。") == "琥珀遗体：树脂封装遗体可高价出售", world.instruction


def test_sdk_角色与世界_quote接入evidence():
    """boss 2026-11-11：角色/世界设定必须有原书段落作证——quote 进
    evidence_json.quotes 随条目走（基线 example 列消费）；裸串 stage 不误取。"""
    products = {
        "world": {"file": "世界.md", "data": {
            "stage": {"content": "狂欢游戏场各副本", "quote": "玩家被随机投入各副本。"},
            "factions": [{"name": "主神空间", "note": "控制玩家的幕后势力（第2章）", "quote": "你们的积分由主神结算。"}],
            "extra": [{"key": "琥珀遗体", "value": "树脂封装遗体可高价出售", "quote": "琥珀里的遗体卖出天价。"}],
        }},
        "characters": {"file": "角色.md", "data": {"characters": [{
            "name": "童姚", "role": "主角", "persona": "冷静果断的玩家",
            "quote": "童姚不敢耽误，立刻冲了上去。", "evidence_ch": "第1章",
        }]}},
    }
    entries, warnings = sdk.map_deconstruct_products("u1", "t1", "志怪/民俗灵异", products)
    assert warnings == [], warnings
    by_title = {e.title: e for e in entries}

    stage = json.loads(by_title["舞台"].evidence_json or "{}")
    assert stage.get("quotes") == [{"loc": "", "text": "玩家被随机投入各副本。"}], stage

    fac = json.loads(by_title["主神空间"].evidence_json or "{}")
    assert fac["quotes"][0]["text"] == "你们的积分由主神结算。", fac
    assert fac["quotes"][0]["loc"] == "第2章", fac  # 章锚从内容括号剥出

    amber = json.loads(by_title["琥珀遗体"].evidence_json or "{}")
    assert amber["quotes"][0]["text"] == "琥珀里的遗体卖出天价。", amber

    ch = json.loads(by_title["童姚"].evidence_json or "{}")
    assert ch.get("quotes") == [{"loc": "第1章", "text": "童姚不敢耽误，立刻冲了上去。"}], ch


def test_sdk_例句方括号原样保留():
    """【系统播报】形态的原句不能被 _line 的结构标记剥除吃掉（真机实锤：
    世界/力量类 quote 成片丢失）。例句通道走 _qline，方括号原样保留。"""
    products = {"world": {"data": {"power": [
        {"name": "身份代码", "rule": "编号被人知晓后命运被掌控",
         "quote": "【如果身份代码被人知道会怎样？】【您的命运就会被得知编号的人掌控……】"},
    ]}}}
    entries, _ = sdk.map_deconstruct_products("u1", "t1", "悬疑", products)
    e = next(x for x in entries if x.title == "身份代码")
    q = json.loads(e.evidence_json)["quotes"][0]["text"]
    assert q.startswith("【如果身份代码被人知道会怎样？】"), q


def test_sdk_例句哨兵归零():
    """「原文未明确」是占位不是例句——不得进 evidence quotes（否则示例列露出占位串）。"""
    products = {"world": {"data": {"history": [
        {"name": "旧案", "note": "第2章，旧案", "quote": "原文未明确"},
    ]}}}
    entries, _ = sdk.map_deconstruct_products("u1", "t1", "悬疑", products)
    e = next(x for x in entries if x.title == "旧案")
    assert "quotes" not in json.loads(e.evidence_json or "{}")


def test_sdk_角色字段级证据_passthrough与键面过滤():
    """boss 2026-11-11：角色卡每格原句——field_quotes 原样进 payload，
    非档案字段的键与空值被过滤。"""
    products = {"characters": {"data": {"characters": [{
        "name": "梁教授", "role": "主角", "persona": "坐轮椅的老刑警",
        "look": "总穿旧夹克",
        "field_quotes": {"look": "他总穿那件洗得发白的旧夹克。", "bogus": "不该出现", "speech": "  "},
        "evidence_ch": "第1章",
    }]}}}
    entries, _ = sdk.map_deconstruct_products("u1", "t1", "悬疑", products)
    e = next(x for x in entries if x.title == "梁教授")
    payload = json.loads(e.payload_json)
    assert payload["field_quotes"] == {"look": "他总穿那件洗得发白的旧夹克。"}, payload
