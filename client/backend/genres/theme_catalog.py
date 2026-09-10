"""题材目录（大类 + 子类）——题材面板第 01 格「什么题材？」的唯一候选源。

用户 2026-09-10 拍板：题材的第一个问题是**题材本身**（仙侠/悬疑/年代/科幻/权谋…），
不再是口味胶囊。目录是**封闭目录**（用户给定、不可自建），故直接以**中文名**为存储值
（不另造 slug：名字即稳定键，省掉 id↔名 两处漂移；与旧 `genres.id` 那种 slug 目录不同，
那张表是用户可自建的候选源）。写入时按本目录校验，不在目录内 → 400。

前端镜像 `client/frontend/src/lib/themeCatalog.ts`（逐字一致，`test_shared_constants_parity.py` 对拍）。
"""

THEMES: list[dict] = [
    {
        "name": "都市",
        "sub_types": [
            "都市生活",
            "都市职场",
            "商战",
            "都市情感",
            "家庭伦理",
            "市井烟火",
            "都市群像",
        ],
    },
    {
        "name": "年代文",
        "sub_types": ["民国", "建国初期", "70年代", "80年代", "90年代", "改革开放年代"],
    },
    {"name": "乡土/乡村", "sub_types": ["乡村振兴", "乡土人情", "农村家族故事"]},
    {
        "name": "刑侦/现实犯罪",
        "sub_types": ["本格刑侦", "社会派犯罪", "连环案", "罪案人性挖掘"],
    },
    {"name": "校园长篇", "sub_types": ["青春成长", "校园群像", "教育困境"]},
    {"name": "谍战", "sub_types": ["民国谍战", "现代谍战"]},
    {"name": "军事", "sub_types": ["现代军旅", "古代战争", "战争史诗"]},
    {"name": "体育", "sub_types": ["足球", "篮球", "赛车", "田径", "乒乓"]},
    {"name": "美食", "sub_types": ["市井美食", "美食传承", "美食创业"]},
    {
        "name": "正史历史小说",
        "sub_types": ["先秦", "秦汉", "唐宋", "明清历史演义"],
    },
    {"name": "架空古王朝", "sub_types": ["权谋", "宫斗", "宅斗", "古言种田"]},
    {
        "name": "穿越历史",
        "sub_types": ["穿真实朝代", "穿虚构王朝（穿越架空古言）"],
    },
    {
        "name": "仙侠/修真",
        "sub_types": ["古典仙侠", "凡人流", "仙魔大战", "种田修仙"],
    },
    {"name": "玄幻", "sub_types": ["东方史诗玄幻", "武魂流", "异兽流", "王朝争霸"]},
    {"name": "志怪/民俗灵异", "sub_types": ["民俗怪谈", "单元精怪故事"]},
    {"name": "西式奇幻", "sub_types": ["史诗奇幻", "低魔奇幻", "黑暗奇幻"]},
    {
        "name": "科幻",
        "sub_types": ["硬科幻", "软科幻", "星际", "赛博朋克", "近未来", "时间旅行"],
    },
    {"name": "末世/废土", "sub_types": ["丧尸末世", "天灾末世", "核战后废土"]},
    {"name": "无限流", "sub_types": ["副本闯关", "空间解密"]},
    {"name": "游戏文", "sub_types": ["网游（虚拟头盔）", "游戏异界"]},
]

THEME_NAMES: tuple[str, ...] = tuple(t["name"] for t in THEMES)


def sub_types_of(theme: str) -> list[str]:
    """某大类的子类清单；未知大类返回空。"""
    for entry in THEMES:
        if entry["name"] == theme:
            return list(entry["sub_types"])
    return []


def theme_or_none(value: str | None) -> str | None:
    """大类名校验：空值→None，不在目录→抛 ValueError（调用方转 400）。"""
    name = (value or "").strip()
    if not name:
        return None
    if name not in THEME_NAMES:
        raise ValueError(f"未知的题材：{name}")
    return name


def sub_type_or_none(theme: str | None, value: str | None) -> str | None:
    """子类名校验：须属于所选大类；无大类时子类无意义（返回 None）。"""
    sub = (value or "").strip()
    if not sub:
        return None
    if not theme:
        return None
    if sub not in sub_types_of(theme):
        raise ValueError(f"「{theme}」没有这个子类：{sub}")
    return sub
