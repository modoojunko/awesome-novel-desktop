"""AI prompt 模板 + 分层边界门禁 + R9/R10 边界（tasks 9.2.8/9.2.11/9.2.17）。

- prompt 模板：`settings_intro_*` / `settings_genre_*` 存在、占位符齐全、不写模型名
- 分层边界（D11 三条禁令，用静态扫描替代裸 grep）
- R9：`genre_profile` 不参与题材判定/写作注入
- R10：`project_settings('ai-model')` 标记行不写入 ai_state
"""

import re
from pathlib import Path
from typing import ClassVar

from genres.vocab_presets import VOCAB_PRESETS
from prompts import load
from settings.ai_router import GENRE_FIELDS, INTRO_ACTIONS

_BACKEND = Path(__file__).resolve().parents[1]


class TestPromptTemplates:
    def test_intro_templates_exist_with_placeholders(self):
        for action in INTRO_ACTIONS:
            text = load(f"settings_intro_{action}")
            assert "{title}" in text and "{content}" in text
            if action == "fill":
                assert "{missing_segments}" in text
            # 模板必须写明「只输出 JSON」与单源占位（段名/禁忌在 introspect 里）
            assert "JSON" in text

    def test_introspect_has_six_segments_and_taboo_rules(self):
        text = load("settings_intro_introspect")
        for name in ("主角身份", "本来的生活", "突发状况", "必须面对的矛盾", "不做的后果", "做了的可能结局"):
            assert name in text, f"体检模板缺段名：{name}"
        for rule in ("设定集腔", "作者自白", "剧透"):
            assert rule in text

    def test_introspect_has_title_check(self):
        """D21：体检含标题对照（fit 三值 + 候选 ≤3 + 只提示不代改）。"""
        text = load("settings_intro_introspect")
        assert "标题对照" in text
        for v in ("mismatch", "generic"):
            assert v in text
        assert "由作者自己决定" in text  # 拍板：不做一键改
        assert "title_check" in text
        # verdict 口径不受标题影响（独立提示行）
        assert "只看六段与禁忌" in text

    def test_genre_templates_exist_with_placeholders(self):
        for field in GENRE_FIELDS:
            text = load(f"settings_genre_{field}")
            assert "{title}" in text and "{synopsis}" in text
            # 题材必须进题材类提示词（用户 2026-09-10）：AI 助手此前完全不知道
            # 本书是什么题材，产出只能靠书名硬猜，只能写出通用空话。
            assert "{theme}" in text and "{theme_desc}" in text and "{theme_example}" in text
            # 当前值：02 拆成 current_note（作者那句话）+ current_value（短标签），其余仍是 current
            assert "{current}" in text or "{current_note}" in text
            assert "JSON" in text

    def test_candidates_are_injected_not_hand_copied(self):
        """候选池动态注入（{candidate_list}），模板里不得再手抄候选词。

        手抄必然漂移：改了 vocab 表忘了改模板 → 模型给出池外候选 → 归一化兜底 →
        静默降级成"自定义"。故用本用例钉住。
        """
        from genres.vocab_presets import VOCAB_PRESETS

        labels = [e["label"] for e in VOCAB_PRESETS]
        assert len(labels) >= 15
        for field in GENRE_FIELDS:
            text = load(f"settings_genre_{field}")
            # 判定「手写清单」＝同一行里出现 ≥2 个候选 label（示例里单引一个不算）
            for line in text.splitlines():
                hits = [lb for lb in labels if lb in line]
                assert len(hits) < 2, f"settings_genre_{field} 手写了候选清单：{line}"
        # 三类候选都由占位符承接（含 id 清单——模型要按 id 回填 tagId）
        cp = load("settings_genre_core_promise")
        assert "{candidate_list}" in cp
        fl = load("settings_genre_forbidden_list")
        assert "{forbidden_candidates}" in fl and "{forbidden_ids}" in fl
        bf = load("settings_genre_battlefield")
        assert "{battlefield_candidates}" in bf and "{battlefield_ids}" in bf

    def test_core_promise_supports_multi_point_switch(self):
        """{multi_point} 开关与「禁止另起炉灶」约束（用户 2026-09-10 参考稿）。"""
        text = load("settings_genre_core_promise")
        assert "{multi_point}" in text
        assert "最多返回 3 个独立看点" in text or "最多返回 3" in text
        assert "禁止完全另起炉灶" in text

    def test_templates_do_not_name_models(self):
        """prompt 层模型无关（D11 ⑦）：模板内不得出现具体模型名。"""
        names = ("gpt-", "claude-", "deepseek", "qwen", "glm-", "kimi", "haiku", "sonnet")
        for field in GENRE_FIELDS:
            text = load(f"settings_genre_{field}").lower()
            for n in names:
                assert n not in text, f"settings_genre_{field} 出现模型名 {n}"
        for action in INTRO_ACTIONS:
            text = load(f"settings_intro_{action}").lower()
            for n in names:
                assert n not in text, f"settings_intro_{action} 出现模型名 {n}"


class TestLayeringBoundaryGate:
    """D11 三条禁令（可 grep 门禁）——静态扫描，豁免清单写在本测试内。"""

    # 豁免：客户端层定义、测试、建书期预填、suggest-meta（无 novel_id）
    EXEMPT_FILES: ClassVar[set[str]] = {
        "ai_client.py",
        "ai_prefill.py",
    }
    EXEMPT_REL: ClassVar[set[str]] = {
        "novels/router.py",  # suggest-meta 建书期
    }
    BUSINESS_DIRS: ClassVar[tuple[str, ...]] = (
        "write",
        "settings",
        "chapters",
        "prompt",
        "archive",
        "story",
        "novels",
    )

    def _iter_py(self):
        for path in _BACKEND.rglob("*.py"):
            rel = path.relative_to(_BACKEND)
            if any(part in {".venv", "__pycache__", "tests", ".mimosa"} for part in rel.parts):
                continue
            yield path, rel.as_posix()

    def test_no_bare_get_ai_client_in_business_layer(self):
        offenders = []
        for path, rel in self._iter_py():
            if path.name in self.EXEMPT_FILES or rel in self.EXEMPT_REL:
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if re.search(r"\bget_ai_client\(", line):
                    offenders.append(f"{rel}:{i}")
        assert not offenders, f"业务层禁裸 get_ai_client()：{offenders}"

    def test_business_layer_does_not_self_check_membership(self):
        offenders = []
        for path, rel in self._iter_py():
            if not rel.startswith(self.BUSINESS_DIRS):
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if re.search(r"check_permission\(|is_member", line):
                    offenders.append(f"{rel}:{i}")
        assert not offenders, f"业务层禁自判会员：{offenders}"

    def test_usage_records_real_model_not_alias(self):
        """计量层记实际模型 id——`model="haiku"` 只允许出现在 chat() 的符号别名位。"""
        offenders = []
        for path, rel in self._iter_py():
            if path.name in self.EXEMPT_FILES:
                continue
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r"record_usage\((.{0,400}?)\)", text, re.DOTALL):
                if 'model="haiku"' in m.group(1):
                    offenders.append(rel)
        assert not offenders, f"record_usage 记了符号别名：{offenders}"

    def test_vocab_ids_stable_slugs(self):
        for entry in VOCAB_PRESETS:
            assert re.fullmatch(r"(promise|forbidden|battlefield):[a-z0-9-]+", entry["id"])


class TestR9R10:
    def test_r9_genre_profile_not_a_genre_source(self):
        """R9：writing-style.genre_profile 只是建书提示，不参与题材判定/注入。"""
        import inspect

        import genres.service as svc
        from workflow import readiness

        assert "genre_profile" not in inspect.getsource(svc.resolve_genre_context)
        assert "genre_profile" not in inspect.getsource(svc.build_genre_section)
        assert "genre_profile" not in inspect.getsource(readiness._check_genre)

    def test_r10_ai_model_marker_not_in_ai_state(self):
        """R10：`project_settings('ai-model')` 是确认标记行，不写入 ai_state。"""
        import inspect

        import ai_state

        src = inspect.getsource(ai_state)
        assert "project_settings" not in src
        assert "ai-model.yaml" not in src


class TestPolishPromptQuality:
    """润色模板质量契约（用户反馈「当前润色很差」后重写，2026-09-10）。

    可判定项：占位符完整、硬性规则齐全、禁忌黑名单具象、自检清单在、few-shot 对照在，
    且 **few-shot 自身不违反规则 1（不新增原文没有的信息）**——示例违规会教坏模型。
    """

    def _t(self) -> str:
        return load("settings_intro_polish")

    def test_placeholders(self):
        t = self._t()
        assert "{title}" in t and "{content}" in t

    def test_hard_rules_present(self):
        t = self._t()
        for rule in ("完整保留全部原始设定", "不新增", "不删减", "不改人称", "字数 ≤ 原文的 90%",
                     "多用短句", "不写死结局"):
            assert rule in t, f"缺硬性规则：{rule}"

    def test_hook_rule_rejects_resume_opening(self):
        t = self._t()
        assert "第一句必须是危机或反差钩子" in t
        assert "履历式开头" in t

    def test_taboo_blacklist_is_concrete(self):
        t = self._t()
        words = ("浮生", "流年", "凡尘", "孑然", "寂寥", "命运齿轮", "瞳孔骤缩", "气场全开")
        missing = [w for w in words if w not in t]
        assert not missing, f"禁忌黑名单缺词：{missing}"
        for pat in ('"不是X，而是Y"', "不仅…更是", "在这个…的世界里"):
            assert pat in t, f"缺 AI 平滑句式：{pat}"

    def test_self_check_list_present(self):
        t = self._t()
        assert "自检" in t and "逐条过" in t

    def test_few_shot_pair_present(self):
        t = self._t()
        assert "示例" in t and "原文：" in t and "改后：" in t

    def test_few_shot_does_not_invent_facts(self):
        """示例里不得出现原文没有的数字/地点——否则示例本身违反规则 1。"""
        t = self._t()
        block = t.split("示例", 1)[1]
        for fabricated in ("七天", "出租屋", "三天", "五年后"):
            assert fabricated not in block, f"示例新增了原文没有的信息：{fabricated}"

    def test_json_contract_only(self):
        t = self._t()
        assert '"original"' in t and '"polished"' in t
        assert "markdown" in t  # polished 内不得含 markdown 标记


class TestThemeAnchorAndMultiPoint:
    """题材锚点注入 + 多看点归一化（用户 2026-09-10 参考稿）。"""

    def test_theme_anchor_uses_sub_then_theme(self):
        from settings.ai_router import _theme_anchor

        desc, ex = _theme_anchor("仙侠/修真", "凡人流")
        assert "资质平平" in desc and "凡人修仙传" in ex  # 子类优先（更贴）
        desc2, ex2 = _theme_anchor("仙侠/修真", "")
        assert "修行阶次" in desc2 and "《凡人修仙传》" in ex2  # 只选大类 → 大类解读 + 前两个子类案例
        assert _theme_anchor("", "") == ("", "")
        assert _theme_anchor("不存在", "") == ("", "")

    def test_as_bool_is_literal_safe(self):
        from settings.ai_router import _as_bool

        for v in (True, "true", "TRUE", "1", "yes", "on"):
            assert _as_bool(v) is True
        for v in (False, None, "", "false", "0", "no", 0):
            assert _as_bool(v) is False

    def test_multi_point_returns_list_with_validation(self):
        from settings.ai_router import _normalize_genre_value

        out = _normalize_genre_value(
            "core_promise",
            [
                {"value": "以弱破强的痛快", "note": "读者要看到弱者用脑子翻盘"},
                {"value": "绝处逢生的紧张", "note": "读者想看一次次死里逃生"},
                {"value": "算无遗策的掌控感", "note": "读者想看布局收网"},
                {"value": "第四条应被截掉", "note": "超上限"},
            ],
        )
        assert isinstance(out, list) and len(out) == 3
        assert out[0]["value"] == "以弱破强的痛快"

    def test_multi_point_drops_empty_items(self):
        from settings.ai_router import _normalize_genre_value

        out = _normalize_genre_value(
            "core_promise",
            [{"value": "", "note": ""}, "不是对象", {"value": "绝处逢生的紧张", "note": ""}],
        )
        assert out == [{"value": "绝处逢生的紧张", "note": ""}]

    def test_multi_point_all_invalid_is_502(self):
        import pytest
        from fastapi import HTTPException

        from settings.ai_router import _normalize_genre_value

        with pytest.raises(HTTPException) as e:
            _normalize_genre_value("core_promise", [{"value": "", "note": ""}])
        assert e.value.status_code == 502

    def test_single_object_path_unchanged(self):
        """旧调用（multi_point=false）出参形状不变——完全兼容。"""
        from settings.ai_router import _normalize_genre_value

        assert _normalize_genre_value("core_promise", {"value": "v", "note": "n"}) == {
            "value": "v",
            "note": "n",
        }
        assert _normalize_genre_value("core_promise", "只有一句话") == {
            "value": "只有一句话",
            "note": "",
        }
