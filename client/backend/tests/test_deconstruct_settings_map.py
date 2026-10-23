"""拆书产物 → 开书设定的投影契约（c-deconstruct-settings-contract）。

判例：产物 JSON/md 是分析稿（证据章号/confidence/原文未明确保留），设定 KV
是操作稿（只留可执行文本）。所有断言都盯「设定值」——源产物不得被改写。
"""

from __future__ import annotations

import copy
import re

from deconstruct import settings_map as sm

_ARTIFACT = re.compile(
    r"(?:【[^】]{0,50}章】|[（(][^）)]*第\s*[0-9][0-9,，、\-—~～至\s]*章[^）)]*[）)]"
    r"|第\s*[0-9][0-9,，、\-—~～至\s]*章|原文未明确|confidence|evidence_ch)",
    re.IGNORECASE,
)


def _clean(text) -> None:
    assert not _ARTIFACT.search(str(text or "")), f"设定文本仍含分析工件：{text!r}"


def test_clean_settings_text_strips_evidence_and_analysis():
    text = (
        "恐惧与调侃交替，如第17、49、55章（第76章）。"
        "老吴告知（第3章），confidence: low，note: 分歧见第4章与第121章"
    )
    out = sm.clean_settings_text(text)
    assert out == "恐惧与调侃交替。老吴告知"
    _clean(out)

    assert sm.clean_settings_text("原文未明确") == ""
    assert sm.clean_settings_text("未采用全知视角，原文未明确反例") == "未采用全知视角"
    # 连续章号引用整段剥，不留「和」「至」残渣；纯标点残渣归空
    for raw in (
        "见第1章和第2章。",
        "如第1章、第2章。",
        "第1章至第258章",
        "第1章到第258章",
        "第1章—第258章",
        "。",
    ):
        assert sm.clean_settings_text(raw) == "", raw
    # 证据后的指代尾巴随引用一起剥
    assert sm.clean_settings_text("如第3章所述，短句为主。") == "短句为主。"
    assert sm.clean_settings_text("见第3章所示。") == ""
    assert sm.clean_settings_text("第3章里的短句为主。") == "短句为主。"
    # 多行文本先折叠再剥：独立行的 confidence/note 尾巴也不能漏
    assert sm.clean_settings_text("正文。\nconfidence: low\nnote: 分歧") == "正文。"
    assert sm.clean_settings_text("正文。\nnote: 分歧") == "正文。"


def test_merge_relation_labels_overflow():
    rel, note = sm.merge_relation_labels(
        ["同僚", "恩义", "生死相托的旧日同僚", "势不两立的债主"], "强派开车"
    )
    assert rel == "同僚、恩义、生死相托的旧日同僚"
    assert len(rel) <= 20
    assert note == "强派开车；另含关系：势不两立的债主"
    assert sm.merge_relation_labels([], "") == ("关系", "")

    # note 已满 300 字：新类型优先保留，不能被 [:300] 截掉
    rel2, note2 = sm.merge_relation_labels(
        ["同僚", "生死相托的旧日同僚", "势不两立的世仇债主"], "甲" * 300
    )
    assert rel2 == "同僚、生死相托的旧日同僚"
    assert "另含关系：势不两立的世仇债主" in note2
    assert len(note2) <= 300


def test_clean_settings_text_sentence_clip():
    text = "第一句完整。第二句也很完整。第三句会被截断"
    out = sm.clean_settings_text(text, 18)
    assert out == "第一句完整。第二句也很完整。"
    assert sm.clean_settings_text("   ", 10) == ""


def test_style_body_new_contract():
    data = {
        "role": "第一人称限知叙述，紧贴主角李耀",
        "rules": [
            {"name": "短句急收", "how": "惊悚段用短句加速，如第10、71章", "confidence": "high"},
        ],
        "craft": [{"name": "反差写法", "how": "轻松段与惊悚段对照，如第3章"}],
        "examples": [
            {"example": "我心里一紧。", "evidence_ch": "第2章"},
            {"example": "他脚下没有影子。", "evidence_ch": "第75章"},
        ],
        "taboo": [{"name": "全知视角", "how": "始终锁在第一人称限知，原文未明确反例"}],
    }
    body = sm.style_body(data)
    assert body["role"] == "第一人称限知叙述，紧贴主角李耀"
    assert body["rules"] == [
        "短句急收：惊悚段用短句加速",
        "避免全知视角：始终锁在第一人称限知",
    ]
    assert body["craft"] == ["反差写法：轻松段与惊悚段对照"]
    assert body["few_shot_examples"] == ["我心里一紧。", "他脚下没有影子。"]
    for text in [body["role"], *body["rules"], *body["craft"], *body["few_shot_examples"]]:
        _clean(text)


def test_style_body_legacy_shape_and_shapes():
    data = {
        "narration": "全书采用第一人称限知视角，紧贴李耀。第二句不该进身份。",
        "dialogue": "对话是信息推进主力（第12章）。",
        "rhythm": "日常与惊悚双线交替【第20章】。",
        "features": [{"name": "章末钩子", "example": "结尾短句急转留悬念（第19章）"}],
    }
    body = sm.style_body(data)
    assert body["role"] == "全书采用第一人称限知视角，紧贴李耀。"
    assert body["rules"] == ["对话：对话是信息推进主力。", "节奏：日常与惊悚双线交替。"]
    assert body["craft"] == ["章末钩子：结尾短句急转留悬念"]
    assert "few_shot_examples" not in body

    # 数组写成字符串/单对象时按一条处理，不逐字符拆
    body = sm.style_body({
        "role": "第一人称限知。另有第二句。",
        "rules": "短句为主，少用长句（第4章）",
        "craft": {"name": "雨意象", "how": "以雨串场（第7章）"},
    })
    assert body["role"] == "第一人称限知。"
    assert body["rules"] == ["短句为主，少用长句"]
    assert body["craft"] == ["雨意象：以雨串场"]


def test_style_body_does_not_mutate_source():
    data = {
        "role": "第一人称（第1章）",
        "rules": [{"name": "短句", "how": "惊悚段加速（第2章）"}],
        "examples": [{"example": "原句。", "evidence_ch": "第3章"}],
    }
    before = copy.deepcopy(data)
    sm.style_body(data)
    assert data == before


def test_world_body_extra_key_value_and_history_origin():
    data = {
        "no_power": "有超凡设定",
        "stage": "主舞台（第1、2章）",
        "power": [{"name": "鬼魂", "rule": "人死后成鬼（第45章）"}],
        "cost": [{"name": "绑定", "rule": "离开即死（第20章）"}],
        "history": [{"name": "旧案", "note": "三任司机出事（第1、2章）", "evidence_ch": "第1章"}],
        "factions": [{"name": "公交公司", "note": "队长强派（第1章）"}],
        "constraints": [{"name": "必须开车", "note": "不能辞职（第20章）"}],
        "extra": [{"key": "13路", "value": "夜班郊区线（第4章）"}],
    }
    body = sm.world_body(data)
    assert body["no_power"] is False
    assert body["stage"] == "主舞台"
    assert body["power"] == "鬼魂：人死后成鬼"
    assert body["extra"] == [{"key": "13路", "value": "夜班郊区线"}]
    assert body["history"][0]["value"] == "三任司机出事"
    assert body["history"][0]["origin"] == "第1章"  # 设定模型的显式证据字段
    for text in [
        body["stage"], body["power"], body["cost"],
        body["history"][0]["value"], body["factions"][0]["note"],
        body["constraints"][0]["value"], body["extra"][0]["value"],
    ]:
        _clean(text)


def test_mainplot_intro_genre_structure():
    mp = sm.mainplot_body({
        "fullstory": "李耀被强派夜班（第1-3章），一路查到真相（第258章）。",
        "ending": {"scene": "末班车驶向黎明（第258章）", "hero": "原文未明确", "tone": "开放"},
    })
    assert mp["fullstory"] == "李耀被强派夜班，一路查到真相。"
    assert mp["ending"] == {"scene": "末班车驶向黎明", "hero": "", "tone": "开放"}
    _clean(mp["fullstory"])

    meta = sm.intro_genre_body(
        {"intro": "一个夜班司机的故事（第1章—第258章）。"},
        {"genre": "灵异志怪", "promise": "带读者进入鬼怪世界（第1、10章）。", "tags": ["灵异"]},
    )
    assert meta["synopsis"] == "一个夜班司机的故事。"
    assert meta["genre"] == "灵异志怪"
    assert meta["promise_note"] == "带读者进入鬼怪世界。"
    assert meta["core_promise"] and meta["forbidden"] and meta["battlefield"]
    assert 1 <= meta["cost_ratio"] <= 10

    vol = sm.structure_volume({"title": "原文未明确（材料仅见第1-258章未分卷）", "ch_range": "第1-258章"})
    assert vol == {"title": "", "summary": "第1-258章"}


def test_technique_lines_compose_repro_steps_and_borrowable():
    rules, craft = sm.technique_lines({
        "techniques": [{
            "name": "身份悬念翻转",
            "repro_steps": ["让读者以为某角色是活人（第3章）", "用第三方证词第一次翻转（第6章）"],
            "emotion_chain": ["怀疑", "惊悚", "反转快感"],
        }],
        "borrowable": [{"item": "开篇用门卫惊恐定格收章（第1章）"}],
        "avoid": [{"item": "靠第三方转告交付关键信息（第164章）"}],
        "reader_needs": [{"need": "身份悬念", "how": "层层翻转"}],
    })
    assert rules == [
        "身份悬念翻转：让读者以为某角色是活人；用第三方证词第一次翻转；情绪链：怀疑→惊悚→反转快感",
        "避免：靠第三方转告交付关键信息",
    ]
    assert craft == ["开篇用门卫惊恐定格收章"]
    for text in [*rules, *craft]:
        _clean(text)


def test_hook_items_keep_plant_payoff_and_note():
    items = sm.hook_items({
        "hooks": [{
            "desc": "三任司机冲水库（第1章）",
            "note": "取档案见日期都是十五（第10章）",
            "type": "mystery", "priority": "high",
            "plant_ch": 1, "payoff_ch": 10, "status": "paid",
        }],
    })
    assert len(items) == 1
    item = items[0]
    assert item["description"] == (
        "三任司机冲水库（取档案见日期都是十五）（埋设于第1章）（收于第10章）"
    )
    assert (item["type"], item["priority"], item["status"]) == ("mystery", 1, "resolved")


def test_genre_extras_fills_legacy_product():
    """旧 genre 产物只有 genre/tags/promise：02–05 也要给非空起点。"""
    meta = sm.intro_genre_body(
        {"intro": "一个夜班司机的故事（第1-258章）。"},
        {
            "genre": "灵异志怪",
            "tags": ["灵异", "悬疑", "解谜"],
            "promise": "跟随主角追查旧案，在惊悚解谜中获得反转快感（第1、10章）。",
        },
        {"fullstory": "李耀一路查真相，直面大患（第258章）。"},
        {"cost": "开此车者被命运绑定，离开即死（第20章）。"},
    )
    assert meta["synopsis"] == "一个夜班司机的故事。"
    assert meta["promise_note"] == "跟随主角追查旧案，在惊悚解谜中获得反转快感。"
    assert meta["core_promise"] == "层层反转的智力快感"
    assert meta["forbidden"] == ["禁天降外援", "禁反派降智"]
    assert meta["cost_ratio"] == 8
    assert meta["battlefield"] == ["查真相", "抗外敌"]
    assert set(meta["inferred"]) == {"core_promise", "forbidden", "cost_ratio", "battlefield"}


def test_genre_extras_prefers_product_fields():
    """产物已给新字段时原样采用，不被启发式覆盖。"""
    meta = sm.intro_genre_body(
        {},
        {
            "genre": "权谋",
            "promise": "朝堂博弈（第1章）。",
            "core_promise": "算无遗策的掌控感",
            "forbidden": ["禁预知破局"],
            "cost_ratio": 5,
            "battlefield": ["爬地位"],
        },
        {},
        {},
    )
    assert meta["core_promise"] == "算无遗策的掌控感"
    assert meta["forbidden"] == ["禁预知破局"]
    assert meta["cost_ratio"] == 5
    assert meta["battlefield"] == ["爬地位"]
    assert meta["inferred"] == []


def test_genre_extras_ignores_broad_single_char_keywords():
    """普通都市文本里的「查看/命令/村庄」不能误判成查真相/高代价/搞基建。"""
    meta = sm.intro_genre_body(
        {},
        {
            "genre": "都市",
            "promise": "她查看手机，有人下达命令，有些感慨，住在村庄，爱情刚起步。",
        },
        None,
        None,
    )
    assert meta["battlefield"] == ["争感情"]
    assert meta["cost_ratio"] == 4
