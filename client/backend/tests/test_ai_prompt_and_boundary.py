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

    def test_genre_templates_exist_with_placeholders(self):
        for field in GENRE_FIELDS:
            text = load(f"settings_genre_{field}")
            assert "{title}" in text and "{synopsis}" in text and "{current}" in text
            assert "JSON" in text

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
