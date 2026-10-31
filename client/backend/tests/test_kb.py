"""写作知识库 · 单元测试（闸门/推断/payload/默认库）。"""

import pytest

from kb.concepts import CONCEPTS, THEMES, normalize_emotion, normalize_scene
from kb.gates import check_gates
from kb.infer import infer_concept
from kb.payloads import validate_payload

# ─── 概念推断 ─────────────────────────────────────────────────

class TestInferConcept:
    def test_打斗手法(self):
        assert infer_concept("打斗句子要短") == "手法"

    def test_世界设定(self):
        assert infer_concept("灵气复苏的规则体系") == "世界设定"

    def test_角色(self):
        assert infer_concept("落魄天才的角色底子") == "角色设定"

    def test_空文本兜底手法(self):
        assert infer_concept("") == "手法"

    def test_无关键词兜底手法(self):
        assert infer_concept(" abc xyz ") == "手法"

    def test_多关键词取最高分(self):
        r = infer_concept("打斗手法配合文风节奏")
        assert r in ("手法", "文笔")


# ─── 场面/情绪归类 ────────────────────────────────────────────

class TestNormalizeScene:
    def test_精确命中(self):
        assert normalize_scene("打斗") == "打斗"

    def test_别名命中(self):
        assert normalize_scene("交手") == "打斗"
        assert normalize_scene("出招") == "打斗"

    def test_文本包含(self):
        assert normalize_scene("两人在雨巷交手") == "打斗"

    def test_未命中返回空(self):
        assert normalize_scene("吃饭睡觉") == ""

    def test_空文本返回空(self):
        assert normalize_scene("") == ""


class TestNormalizeEmotion:
    def test_精确命中(self):
        assert normalize_emotion("燃") == "燃"

    def test_别名命中(self):
        assert normalize_emotion("热血") == "燃"

    def test_未命中返回空(self):
        assert normalize_emotion("吃饭") == ""


# ─── payload 校验 ──────────────────────────────────────────────

class TestValidatePayload:
    def test_手法合法(self):
        r = validate_payload("手法", {"instruction": "x", "scene": "打斗"})
        assert r["instruction"] == "x"
        assert r["scene"] == "打斗"

    def test_手法缺scene报错(self):
        with pytest.raises(ValueError, match="scene"):
            validate_payload("手法", {"instruction": "x"})

    def test_文笔rule合法(self):
        r = validate_payload("文笔", {"slot": "rule", "rule": "一句不超过22字"})
        assert r["rule"] == "一句不超过22字"

    def test_文笔slot与字段不匹配报错(self):
        with pytest.raises(ValueError, match="rule"):
            validate_payload("文笔", {"slot": "rule"})  # 缺 rule 字段

    def test_世界constraint带hard(self):
        r = validate_payload("世界设定", {"part": "constraint", "content": "断剑之誓", "hard": True})
        assert r["hard"] is True

    def test_角色archetype必填(self):
        with pytest.raises(ValueError, match="archetype"):
            validate_payload("角色设定", {})

    def test_未知概念报错(self):
        with pytest.raises(ValueError, match="未知概念"):
            validate_payload("未知", {})

    def test_未知字段拒收(self):
        with pytest.raises(ValueError):
            validate_payload("手法", {"instruction": "x", "scene": "打斗", "unknown_key": "val"})


# ─── 入库闸门 ──────────────────────────────────────────────────

class TestCheckGates:
    def test_合法条目通过(self):
        r = check_gates(
            concept="手法", instruction="先给果再补因。",
            payload={"instruction": "先给果再补因。", "scene": "打斗"},
        )
        assert r.ok is True

    def test_指令为空拦截(self):
        r = check_gates(concept="手法", instruction="", payload={})
        assert r.ok is False
        assert "instruction" in r.errors

    def test_指令超长拦截(self):
        r = check_gates(concept="手法", instruction="a" * 250, payload={})
        assert r.ok is False
        assert "instruction" in r.errors

    def test_原文闸拦截(self):
        original = "断剑先落地，血溅三尺，出招之后才补因果，满地霜华未扫。"
        r = check_gates(
            concept="手法", instruction="先给果再补因。",
            payload={"instruction": "先给果再补因。", "scene": "打斗", "sample": original},
            example=original[:30],
            original_texts=[original],
        )
        assert r.needs_rewrite is True

    def test_红线闸拦截破折号停顿(self):
        r = check_gates(
            concept="手法", instruction="用破折号制造停顿——那就是转折",
            payload={"instruction": "用破折号制造停顿——那就是转折", "scene": "打斗"},
        )
        assert any("反AI" in w for w in r.warnings)

    def test_when_json世界设定拒收(self):
        r = check_gates(
            concept="世界设定", instruction="舞台设定",
            payload={"part": "stage", "content": "南崖剑宗"},
            when_json={"scene": "打斗"},
        )
        assert r.ok is False
        assert "when_json" in r.errors

    def test_指令句末断_有句号通过(self):
        r = check_gates(concept="手法", instruction="先给果再补因。", payload={})
        assert r.ok is True
        assert not any("句末" in w for w in r.warnings)

    def test_指令句末断_无句号给warning不拦截(self):
        r = check_gates(concept="手法", instruction="先给果再补因", payload={})
        assert r.ok is True  # 240 字内短指令不因缺句号被拦截
        assert any("句末" in w or "断" in w for w in r.warnings)


# ─── 概念注册表 ────────────────────────────────────────────────

class TestConceptRegistry:
    def test_六概念封闭(self):
        assert len(CONCEPTS) == 6

    def test_题材21类(self):
        assert len(THEMES) == 21
