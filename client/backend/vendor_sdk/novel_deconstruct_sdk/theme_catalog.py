"""题材目录词表快照（SDK 自包含；与 C 端 genres.theme_catalog.THEMES 同源维护——
C 端词表更新时本文件同批更新）。"""

THEME_NAMES: tuple[str, ...] = ('都市', '年代文', '乡土/乡村', '悬疑', '刑侦/现实犯罪', '校园长篇', '谍战', '军事', '体育', '美食', '正史历史小说', '架空古王朝', '穿越历史', '仙侠/修真', '玄幻', '志怪/民俗灵异', '西式奇幻', '科幻', '末世/废土', '无限流', '游戏文', '古代言情', '现代言情', '玄幻言情', '仙侠奇缘', '浪漫青春', '大女主/马甲', '快穿', '耽美', '百合', '武侠', '轻小说/二次元', '系统文', '都市脑洞', '种田基建', '现实题材')


def normalize_theme(raw) -> str:
    """把任意题材文本归一到目录大类名：精确命中优先；否则包含匹配（双向）；
    组件匹配兜底（目录名按「/」拆，任一组分出现在原文即命中，最长组件优先）；
    仍无→空串（调用方按「未分题材」处理）。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    if text in THEME_NAMES:
        return text
    for name in THEME_NAMES:
        if name in text:
            return name
    for name in THEME_NAMES:
        if text in name:
            return name
    best_name, best_len = "", 0
    for name in THEME_NAMES:
        for part in name.split("/"):
            if len(part) >= 2 and part in text and len(part) > best_len:
                best_name, best_len = name, len(part)
    return best_name
