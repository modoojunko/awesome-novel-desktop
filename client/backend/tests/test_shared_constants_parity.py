"""前后端共享常量 parity（genre-signup-redesign tasks 6.3/6.4）。

「后端下发 + 前端镜像」机制的对拍测试：前端镜像文件是 TS，无法 import，
故用正则抽取常量逐项比对。任一不一致 = 采纳写回的 tagId/段名在后端查不到
（注入退化成裸 slug / 体检行名对不上），必须让 CI 拦住。

覆盖：
- `genres/vocab_presets.py::VOCAB_PRESETS` ↔ `lib/genreVocab.ts::GENRE_VOCAB`
- `settings/ai_router.py::INTRO_SEGMENT_NAMES` ↔ `lib/introTemplate.ts::INTRO_SEGMENTS`
- `settings/ai_router.py::INTRO_TABOO_RULES` ↔ `lib/introTemplate.ts::TABOO_RULES`
- 口味联动引用的 tagId 必须都在候选源里（防手改漏配）
"""

import re
from pathlib import Path

from genres.vocab_presets import VOCAB_PRESETS
from settings.ai_router import INTRO_SEGMENT_NAMES, INTRO_TABOO_RULES

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib"


def _read(name: str) -> str:
    return (_FRONTEND / name).read_text(encoding="utf-8")


class TestVocabParity:
    def test_ids_labels_kinds_match(self):
        src = _read("genreVocab.ts")
        pairs = re.findall(r'v\("(\w+)",\s*"([\w-]+)",\s*"([^"]+)",\s*(\d+)\)', src)
        frontend = [
            {"id": f"{kind}:{slug}", "kind": kind, "label": label, "sort": int(sort)}
            for kind, slug, label, sort in pairs
        ]
        assert frontend == VOCAB_PRESETS, (
            "前后端候选源不一致——以 genres/vocab_presets.py 为准同步 lib/genreVocab.ts"
        )

    def test_vocab_ids_are_stable_slugs(self):
        """tagId 禁序号（index 会漂移导致已存数据指向错误标签）。"""
        for entry in VOCAB_PRESETS:
            assert re.fullmatch(r"(promise|forbidden|battlefield):[a-z0-9-]+", entry["id"])

    def test_flavor_refs_exist_in_vocab(self):
        src = _read("genreVocab.ts")
        refs = set(re.findall(r'"((?:promise|forbidden|battlefield):[\w-]+)"', src))
        known = {e["id"] for e in VOCAB_PRESETS}
        assert refs <= known, f"口味联动引用了不存在的候选：{refs - known}"


class TestIntroTemplateParity:
    def test_segment_names_match(self):
        src = _read("introTemplate.ts")
        names = re.findall(r'name:\s*"([^"]+)"', src)
        assert tuple(names) == INTRO_SEGMENT_NAMES, (
            "六段名前后端不一致——体检行名必须逐字对齐"
        )

    def test_taboo_rules_match(self):
        src = _read("introTemplate.ts")
        block = re.search(r"TABOO_RULES\s*=\s*\[(.*?)\]", src, re.DOTALL)
        assert block, "找不到 TABOO_RULES"
        rules = tuple(re.findall(r'"([^"]+)"', block.group(1)))
        assert rules == INTRO_TABOO_RULES

    def test_dont_do_third_item_differs_from_taboo(self):
        """「别踩」第三条＝写死结局，与体检禁忌「剧透」用途不同，不得合并。"""
        src = _read("introTemplate.ts")
        block = re.search(r"DONT_DO\s*=\s*\[(.*?)\]", src, re.DOTALL)
        assert block, "找不到 DONT_DO"
        body = block.group(1)
        assert "写死结局" in body, "「别踩」第三条应为写死结局"
        # 体检禁忌第三元是「剧透」——两者不得合并（用途不同）
        assert INTRO_TABOO_RULES[2] == "剧透"
        assert "剧透" not in body


class TestThemeCatalogParity:
    """题材目录（01 格「什么题材」）前后端逐字一致。

    不一致 = 作者选中的题材在后端 `theme_or_none` 校验不过（400「未知的题材」），
    或子类被拒（400「没有这个子类」）。
    """

    def _frontend_themes(self) -> list[dict]:
        src = _read("themeCatalog.ts")
        block = re.search(r"THEMES:\s*ThemeEntry\[\]\s*=\s*\[(.*?)\n\];", src, re.DOTALL)
        assert block, "找不到 THEMES"
        out = []
        for name, subs in re.findall(
            r'\{\s*name:\s*"([^"]+)",\s*subTypes:\s*\[([^\]]*)\]\s*,?\s*\}', block.group(1)
        ):
            out.append(
                {"name": name, "sub_types": re.findall(r'"([^"]+)"', subs)}
            )
        return out

    def test_names_and_sub_types_match(self):
        from genres.theme_catalog import THEMES

        assert self._frontend_themes() == THEMES, (
            "题材目录前后端不一致——以 genres/theme_catalog.py 为准同步 lib/themeCatalog.ts"
        )

    def test_validation_helpers_agree_on_membership(self):
        from genres.theme_catalog import THEME_NAMES, sub_types_of

        assert len(THEME_NAMES) == 20
        assert sub_types_of("仙侠/修真") == ["古典仙侠", "凡人流", "仙魔大战", "种田修仙"]
        assert sub_types_of("不存在的题材") == []
