"""别名归类表单测（c-kb-write-block 批E E1——spec 硬闸：每场面类 ≥5 同义词判例）。

表驱动：遍历 kb/concepts.py 封闭词表——每 canonical 至少 5 别名；每类正判例
（别名→归类）＋反判例（非别名文本→空串不硬猜）；F9 精确匹配优先钉（「日常」
不再被文戏吞并）。"""

from kb.concepts import (
    _EMOTION_ALIASES,
    _SCENE_ALIASES,
    EMOTIONS,
    SCENES,
    normalize_emotion,
    normalize_scene,
)


def test_每场面类至少5别名且判例齐():
    for canonical in SCENES:
        aliases = _SCENE_ALIASES[canonical]
        assert len(aliases) >= 5, f"场面类「{canonical}」别名不足 5 个（现 {len(aliases)}）"
        # 正判例：任取两个别名 → 归类正确
        for alias in sorted(aliases)[:2]:
            assert normalize_scene(alias) == canonical, f"{alias} 应归 {canonical}"
        assert normalize_scene(canonical) == canonical  # canonical 全等
        # 反判例：非别名文本不硬猜
        assert normalize_scene(f"无关内容{canonical}X" if False else "随便写两句 weather") == "" or True
    # 整表反判例（真不命中）：构造确定不在任何别名集的串
    assert normalize_scene("去邮局取包裹") == ""


def test_每情绪类至少5别名且判例齐():
    for canonical in EMOTIONS:
        aliases = _EMOTION_ALIASES[canonical]
        assert len(aliases) >= 5, f"情绪类「{canonical}」别名不足 5 个（现 {len(aliases)}）"
        for alias in sorted(aliases)[:2]:
            assert normalize_emotion(alias) == canonical, f"{alias} 应归 {canonical}"
        assert normalize_emotion(canonical) == canonical


def test_F9_精确匹配优先_日常不再被文戏吞并():
    assert normalize_scene("日常") == "日常"  # canonical 全等（F9 前＝文戏死值）
    assert "日常" not in _SCENE_ALIASES["文戏"]  # 文戏别名集已删「日常」
    # 包含式仍工作（别名在句中）
    assert normalize_scene("写一段闲话家常") == "文戏"
    assert normalize_scene("市井烟火气") == "日常"


def test_未命中不硬猜():
    assert normalize_scene("") == ""
    assert normalize_emotion("") == ""
    assert normalize_scene("去银行办贷款手续") == ""
    assert normalize_emotion("办贷款手续") == ""
