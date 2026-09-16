"""伏笔领域单源 settings/hooks_model.py 的行为测试（foreshadow-settings-v2 tasks 1.1）。

前端镜像常量（src/lib/hooksModel.ts）与 parity 测试随前端批 1 PR 落地
（沿 test_shared_constants_parity 先例）；本文件先钉住后端单源契约。
"""

import pytest

from settings.hooks_model import (
    DESCRIPTION_MAX,
    HOOK_STATUSES,
    HOOK_TYPE_KEYS,
    HOOK_TYPES,
    PAYOFF_NOTE_MAX,
    PRIORITY_LABELS,
    normalize_priority,
    priority_label,
    type_label,
)


class TestConstants:
    def test_type_vocabulary(self):
        """9 type slug 白名单（spec 冻结序）。"""
        assert HOOK_TYPE_KEYS == (
            "mystery", "threat", "promise", "clue", "relationship",
            "power", "emotion", "choice", "desire",
        )
        assert len(HOOK_TYPES) == 9
        assert all(set(f) == {"k", "label"} for f in HOOK_TYPES)

    def test_status_vocabulary(self):
        """三态单列；mentioned 不是状态（归档留痕走独立列）。"""
        assert HOOK_STATUSES == ("active", "resolved", "abandoned")

    def test_length_discipline(self):
        assert DESCRIPTION_MAX == 300
        assert PAYOFF_NOTE_MAX == 300

    def test_priority_labels_unique(self):
        assert PRIORITY_LABELS == {1: "高", 2: "中", 3: "低"}


class TestNormalizePriority:
    @pytest.mark.parametrize("raw,expected", [
        (1, 1), (2, 2), (3, 3),
        ("1", 1), ("2", 2), ("3", 3),
        ("high", 1), ("medium", 2), ("low", 3),
        ("HIGH", 1), (" Low ", 3),
        ("高", 1), ("中", 2), ("低", 3),
    ])
    def test_mixed_shapes_normalized(self, raw, expected):
        assert normalize_priority(raw) == expected

    @pytest.mark.parametrize("raw", [0, 4, -1, "0", "4", "highly", "", None, [], True, 1.5])
    def test_invalid_rejected(self, raw):
        with pytest.raises(ValueError):
            normalize_priority(raw)

    def test_label_mapping(self):
        assert priority_label(1) == "高"
        assert priority_label("3") == "低"
        assert priority_label("bogus") == ""  # 非法 → 丢弃标注（返回空串）
        assert priority_label(None) == ""

    def test_type_label(self):
        assert type_label("mystery") == "悬念"
        assert type_label("desire") == "渴望钩"
        assert type_label("unknown_slug") == "unknown_slug"  # 未知值原样兜底
        assert type_label("") == ""
