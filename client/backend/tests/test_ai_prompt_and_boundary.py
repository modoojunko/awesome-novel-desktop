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

_BACKEND = Path(__file__).resolve().parents[1]


# TestPromptTemplates（intro/genre 模板正文断言）已迁提示词仓（c-prompt-source-flip
# tests/test_templates_extra.py TestIntroGenreTemplates）。


class TestLayeringBoundaryGate:
    """D11 三条禁令（可 grep 门禁）——静态扫描，豁免清单写在本测试内。"""

    # 豁免：客户端层定义、测试、建书期预填、suggest-meta（无 novel_id）
    EXEMPT_FILES: ClassVar[set[str]] = {
        "ai_client.py",
        
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


# TestPolishPromptQuality（简介润色质量契约）已迁提示词仓（同上
# TestIntroPolishQuality）。


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


class TestVocabIdFuzzyMapping:
    """模型写岔的 tagId：少写/多写一个词要在边界处修正，别落成英文自定义文本。

    实测（2026-09-10）：模型把 forbidden:no-deus-ex-machina 写成
    forbidden:no-deus-machina，旧逻辑查不到候选 → 当 custom_text 存了下来 →
    界面上显示英文 slug（用户反馈「AI 建议给出来的是英文」）。
    """

    def test_missing_word_maps_back(self):
        from settings.ai_router import _vocab_id

        assert _vocab_id("forbidden", "forbidden:no-deus-machina") == (
            "forbidden:no-deus-ex-machina"
        )
        assert _vocab_id("forbidden", "no-deus-machina") == "forbidden:no-deus-ex-machina"

    def test_plural_tolerated(self):
        from settings.ai_router import _vocab_id

        assert _vocab_id("battlefield", "battlefield:resource") == "battlefield:resources"

    def test_exact_still_first(self):
        from settings.ai_router import _vocab_id

        assert _vocab_id("forbidden", "forbidden:no-free-powerup") == (
            "forbidden:no-free-powerup"
        )

    def test_unknown_id_stays_unknown(self):
        from settings.ai_router import _vocab_id

        assert _vocab_id("forbidden", "forbidden:totally-unknown") is None

    def test_slug_shaped_unknown_not_stored_as_custom_text(self):
        """查不到的 id 不得落成自定义文本——存下来只会在界面上显示英文。"""
        from settings.ai_router import _normalize_vocab_list

        out = _normalize_vocab_list(
            "forbidden",
            [
                {"tagId": "forbidden:no-deus-machina"},  # 近似 → 落 tagId
                {"tagId": "forbidden:totally-unknown"},  # 真未知 → 丢弃
                {"text": "禁主角靠灵根觉醒翻盘"},  # 中文自定义 → 保留
                {"text": "no time travel please"},  # 英文但不像 slug → 保留
            ],
            100,
        )
        assert {"tagId": "forbidden:no-deus-ex-machina"} in out
        assert {"text": "禁主角靠灵根觉醒翻盘"} in out
        assert {"text": "no time travel please"} in out
        assert not any("forbidden:totally" in str(x) for x in out)
