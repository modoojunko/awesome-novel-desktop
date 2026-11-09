"""SDK 独立单测（c-knowledge-source-align 一期）：不经 C 端任何模块——
知识仓同法调 SDK，证明自包含（构建 CI 单仓可跑）。"""

import json
import sys
from pathlib import Path

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
