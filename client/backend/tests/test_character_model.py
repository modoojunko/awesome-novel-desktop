"""领域单源 settings/character_model.py 的行为测试（tasks 2.2）。"""

from settings.character_model import (
    CHAR_CHECK_STATUS,
    COG_FILL_KEYS,
    COG_KEYS,
    COG_REQUIRED,
    DOSSIER_FIELDS,
    DOSSIER_FILL_KEYS,
    WRITE_STATE_KEYS,
    apply_character_fills,
    book_characters_gate,
    card_gaps,
    check_items,
    compute_targets,
    gate_fingerprint,
)


def _full_card(role: str = "主角", name: str = "林拾") -> dict:
    return {
        "name": name,
        "role": role,
        "persona": "青梧宗杂役，记性过人。",
        "dossier": {k: "x" for k in DOSSIER_FILL_KEYS},
        "cog": {k: "y" for k in COG_KEYS},
    }


class TestConstants:
    def test_shape_counts(self):
        assert len(DOSSIER_FIELDS) == 8
        assert len(DOSSIER_FILL_KEYS) == 6  # gender/age 不进 AI 候选
        assert len(COG_KEYS) == 30
        assert set(COG_REQUIRED) == {"w5", "p3", "p4"}
        assert len(COG_FILL_KEYS) == 10  # 6 主格 + w5/p3/p4 + p6
        assert set(COG_FILL_KEYS) == {"w1", "s1", "v1", "p2", "b1", "e3", "w5", "p3", "p4", "p6"}
        assert WRITE_STATE_KEYS == ("w1", "s1", "v1", "p2", "b1", "e3")
        assert CHAR_CHECK_STATUS == ("ok", "warn", "conflict", "miss")

    def test_author_only_fields(self):
        author_only = {f["k"] for f in DOSSIER_FIELDS if f["author_only"]}
        assert author_only == {"gender", "age"}

    def test_check_items_variant(self):
        power_names = [name for name, _ in check_items(True)]
        real_names = [name for name, _ in check_items(False)]
        assert "世界 × 能力上限" in power_names
        assert "世界 × 现实规则" in real_names
        assert len(power_names) == len(real_names) == 6


class TestGate:
    def test_full_card_passes(self):
        gate = book_characters_gate([_full_card()])
        assert gate == {"ok": True, "no_protagonist": False, "missing": []}

    def test_no_protagonist(self):
        card = _full_card(role="配角")
        gate = book_characters_gate([card])
        assert gate["no_protagonist"] is True and gate["ok"] is False

    def test_later_confirm_names_gaps_per_card(self):
        prot = _full_card()
        side = _full_card(role="配角", name="苏晚芜")
        del side["cog"]["p4"]
        gate = book_characters_gate([prot, side])
        assert gate["ok"] is False
        assert gate["missing"] == [{"name": "苏晚芜", "fields": ["能力代价"]}]

    def test_extra_only_needs_plot(self):
        prot = _full_card()
        extra = {"name": "路人甲", "role": "路人", "dossier": {"plot": "背景"}, "cog": {}}
        gate = book_characters_gate([prot, extra])
        assert gate["ok"] is True

        extra_empty = {"name": "路人乙", "role": "路人", "dossier": {}, "cog": {}}
        gate2 = book_characters_gate([prot, extra_empty])
        assert gate2["ok"] is False
        assert gate2["missing"] == [{"name": "路人乙", "fields": ["剧情定位"]}]

    def test_first_confirm_only_needs_name_and_persona(self):
        prot = _full_card()
        for k in list(prot["dossier"]):
            prot["dossier"][k] = ""
        for k in list(prot["cog"]):
            prot["cog"][k] = ""
        gate = book_characters_gate([prot], first=True)
        assert gate["ok"] is True

    def test_card_gaps_lists_six_fields(self):
        empty = {"name": "", "role": "主角", "persona": "", "dossier": {}, "cog": {}}
        gaps = card_gaps(empty)
        assert gaps == [
            "角色名称", "一句话人设", "剧情定位", "核心认知盲区", "能力上限", "能力代价",
        ]

    def test_fingerprint_changes_only_on_gate_fields(self):
        base = [_full_card()]
        fp1 = gate_fingerprint(base)
        # 改非门禁格 → 指纹不变
        changed_look = _full_card()
        changed_look["dossier"]["look"] = "换了发型"
        assert gate_fingerprint([changed_look]) == fp1
        # 改门禁格 → 指纹变
        changed_w5 = _full_card()
        changed_w5["cog"]["w5"] = "新的盲区"
        assert gate_fingerprint([changed_w5]) != fp1
        # 路人卡不进指纹
        with_extra = base + [{
            "name": "路人", "role": "路人", "seq": 9,
            "dossier": {"plot": "x"}, "cog": {},
        }]
        assert gate_fingerprint(with_extra) == fp1


class TestTargetsAndApply:
    def test_targets_use_server_side_empty(self):
        dossier = {"race": "人族"}
        cog = {"w1": "知道些"}
        assert compute_targets(dossier, cog, "", "persona") == ["persona"]
        assert compute_targets(dossier, cog, "已有", "persona") == []
        t_dossier = compute_targets(dossier, cog, "", "dossier")
        assert "race" not in t_dossier and set(t_dossier) == set(DOSSIER_FILL_KEYS) - {"race"}
        t_cog = compute_targets(dossier, cog, "", "cog")
        assert "w1" not in t_cog and len(t_cog) == 9

    def test_apply_skips_filled_and_unknown(self):
        card = {"dossier": {"race": "人族"}, "cog": {}}
        new_card, applied, skipped = apply_character_fills(
            card, "dossier",
            {"race": "妖族", "look": "瘦高", "gender": "男", "nope": "x"},
        )
        assert new_card["dossier"]["race"] == "人族"  # 非空拒写
        assert new_card["dossier"]["look"] == "瘦高"
        assert applied == [{"key": "look", "value": "瘦高"}]
        reasons = {s["key"]: s["reason"] for s in skipped}
        assert reasons["race"] == "already_filled"
        assert reasons["gender"] == "author_only"
        assert reasons["nope"] == "unknown_key"
        assert "gender" not in new_card["dossier"]  # 永不写入

    def test_apply_blank_value_discarded(self):
        card = {"cog": {}}
        _card, applied, skipped = apply_character_fills(card, "cog", {"w5": "   "})
        assert applied == [] and skipped[0]["reason"] == "unknown_key"

    def test_apply_does_not_mutate_input(self):
        card = {"cog": {}}
        _new, _applied, _skipped = apply_character_fills(card, "cog", {"w5": "盲区"})
        assert card["cog"] == {}
