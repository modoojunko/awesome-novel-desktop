"""概念注册表——六概念封闭、子概念叶子、场面/情绪封闭词表与别名表。"""

CONCEPTS = ("文风", "文笔", "世界设定", "角色设定", "手法", "情节")

# 消费链未建的概念：手录/推断/全局图拒收创建
READ_ONLY_CONCEPTS = frozenset({"情节"})

# 题材目录（21 类，与 themeCatalog.ts / theme_catalog.py 同源）
THEMES = (
    "都市", "年代文", "乡土/乡村", "悬疑", "刑侦/现实犯罪",
    "校园长篇", "谍战", "军事", "体育", "美食",
    "正史历史小说", "架空古王朝", "穿越历史", "仙侠/修真",
    "玄幻", "志怪/民俗灵异", "西式奇幻", "科幻", "末世/废土",
    "无限流", "游戏文",
)

# 场面封闭词表（章纲归类 / when_json.scene 只能取这些值）
SCENES = ("打斗", "文戏", "开篇", "转折", "收尾", "对峙", "日常")

# 情绪封闭词表
EMOTIONS = ("燃", "冷", "虐", "甜", "疑", "静")

# 章位封闭词表
CHAPTER_POS = ("开头", "中段", "卷末", "any")

# scene 别名表（章纲自由文本 → 封闭值）
_SCENE_ALIASES: dict[str, set[str]] = {
    "打斗": {"打", "打起来", "动手", "交手", "出招", "追逃", "厮杀", "激战", "混战", "迎战", "偷袭", "对决", "交锋", "械斗", "群殴"},
    "文戏": {"聊天", "谈心", "对话", "聊天", "日常", "闲聊", "交流", "谈天", "表白", "告白"},
    "开篇": {"开场", "开局", "开头", "首章", "起手", "登场", "亮相", "引入"},
    "转折": {"反转", "突变", "意外", "翻盘", "急转", "揭底", "揭穿", "揭秘"},
    "收尾": {"收束", "结尾", "落幕", "完结", "收场", "了结", "尾声", "终结"},
    "对峙": {"对峙", "僵持", "冷战", "对视", "沉默", "僵局", "隔阂", "谈判", "博弈"},
    "日常": {"日常", "生活", "烟火", "市井", "柴米油盐", "平凡"},
}

# emotion 别名表
_EMOTION_ALIASES: dict[str, set[str]] = {
    "燃": {"燃", "热血", "激昂", "振奋", "怒", "愤", "炸裂", "爆发", "燃爆"},
    "冷": {"冷", "冷静", "压抑", "沉重", "紧张", "紧绷", "凝重", "肃杀", "阴沉"},
    "虐": {"虐", "心疼", "揪心", "难过", "悲伤", "绝望", "崩溃", "痛苦", "撕裂"},
    "甜": {"甜", "温馨", "暖", "甜蜜", "幸福", "治愈", "松弛", "轻松", "愉快"},
    "疑": {"疑", "悬疑", "猜忌", "怀疑", "不安", "诡异", "蹊跷", "可疑", "费解"},
    "静": {"静", "安静", "平和", "安宁", "沉寂", "寂静", "空灵", "禅意", "超脱"},
}


def normalize_scene(text: str) -> str:
    """章纲文本 → 封闭场面值；未命中返回空串。"""
    t = text.strip()
    if not t:
        return ""
    for canonical, aliases in _SCENE_ALIASES.items():
        if t == canonical or t in aliases:
            return canonical
    for canonical, aliases in _SCENE_ALIASES.items():
        for a in aliases:
            if a in t:
                return canonical
    return ""


def normalize_emotion(text: str) -> str:
    """章纲文本 → 封闭情绪值；未命中返回空串。"""
    t = text.strip()
    if not t:
        return ""
    for canonical, aliases in _EMOTION_ALIASES.items():
        if t == canonical or t in aliases:
            return canonical
    for canonical, aliases in _EMOTION_ALIASES.items():
        for a in aliases:
            if a in t:
                return canonical
    return ""


def infer_concept(text: str) -> str:
    """自由文本 → 概念推断；匹配不出返回默认"手法"。"""
    t = text.strip()
    if not t:
        return "手法"
    # 关键词命中
    hits: dict[str, int] = {}
    keywords: dict[str, list[str]] = {
        "文风": ["声音", "身份", "基调", "叙事", "视角", "冷峻", "克制", "旁白", "口吻"],
        "文笔": ["句式", "节奏", "描写", "修辞", "禁用", "短句", "长句", "比喻", "动词", "对话"],
        "世界设定": ["世界", "设定", "舞台", "力量", "势力", "历史", "铁律", "规则", "体系"],
        "角色设定": ["角色", "人物", "原型", "性格", "底子", "档案", "形象", "塑造"],
        "手法": ["手法", "技巧", "打法", "套路", "先果后因", "悬念", "伏笔", "钩子", "打斗", "文戏"],
        "情节": ["情节", "剧情", "套路", "结构", "节奏", "冲突", "主线", "支线", "卷"],
    }
    for concept, kws in keywords.items():
        score = sum(1 for kw in kws if kw in t)
        if score > 0:
            hits[concept] = score
    if not hits:
        return "手法"
    return max(hits, key=hits.get)


def is_valid_concept(name: str) -> bool:
    return name in CONCEPTS


def is_valid_theme(name: str) -> bool:
    return name in THEMES
