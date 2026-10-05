"""本书专名名册 + 专名口径规则（c-ai-name-canon）。

**现状（c-prompt-dead-refs-cleanup，2026-10-05）**：
- **名册**（`known_names`/`roster_text`）：唯一活注入腿——填 arc_draft/arc_calibrate/
  arc_check、chapter_archive_extract、settings_characters_check 等模板的 {roster}；
- **规则片段**（`name_canon_text`，`prompts/name_canon.prompt`）：**参考存档，无运行时
  注入点**——prompts/ 已无 {name_rules} 占位符，现行规则是 arc_* 三模板 system 段的
  语境化变体（三处互不逐字一致）；改专名口径去三处内联地改，改本片段不生效。
  恢复单源注入须给 arc_* 加回占位符并重新接线对拍（详见片段头注释）。

历史结论仍成立（2026-09-27 真机实测）：只有抽象规则不给名册时，模型面对作者旧稿
原文会继续沿用未登记专名——名册＋产出申报对拍才是能落地的机制。

题材中立：现实题材无势力/无力量体系时相应集合为空，「没有的类别就退通称」兜底；
不假设任何具体题材、不写死任何具体词。
"""

_CANON_PROMPT = "name_canon"


def name_canon_text() -> str:
    """专名口径片段加载器——**参考存档**（当前零调用方；无 {name_rules} 注入点）。

    剥掉文件头 `## ` 版本注释行（不入提示词）。保留本函数：未来恢复动态注入时，
    先给 arc_* 三模板加回占位符并重接线对拍（见模块 docstring 与片段头注释）。
    """
    from prompts import load

    lines = load(_CANON_PROMPT).splitlines()
    i = 0
    while i < len(lines) and lines[i].lstrip().startswith("##"):
        i += 1
    return "\n".join(lines[i:]).strip()


async def known_names(db, project) -> dict[str, set[str]]:
    """本书已登记专名：`characters`（角色名＋别名）/ `factions`（势力名）/ `places`（地点）。

    地点来源与越纲对拍同口径：各章章纲「地点」字段 ∪ 世界舞台自由文本里圈出的地名短语。
    读不到世界设定不抛（返回空集合）：名册空＝模型退通称（片段里有兜底句）。
    """
    from filesystem.storage import get_storage
    from settings.character_service import list_characters
    from settings.world_model import normalize_world

    chars: set[str] = set()
    try:
        roster = await list_characters(db, project.id)
        for item in roster.get("items", []):
            nm = str(item.get("name") or "").strip()
            # 空名占位卡（`\u0000<hex>`）不是名字：不进名册（否则 NUL 伪名会随名册进提示词）
            if nm and not nm.startswith("\u0000"):
                chars.add(nm)
            for alias in item.get("aliases") or []:
                na = str(alias).strip()
                if na and not na.startswith("\u0000"):
                    chars.add(na)
    except Exception:  # noqa: BLE001, S110 — 名册只服务提示词/对拍，取不到不阻断主流程
        pass

    factions: set[str] = set()
    places: set[str] = set()
    try:
        world_raw = await get_storage().read_yaml(project.root_path, "settings/world-setting.yaml") or {}
        for f in normalize_world(world_raw).get("factions") or []:
            if isinstance(f, dict):
                n = str(f.get("name") or "").strip()
                if n:
                    factions.add(n)
        from chapters.ai_plan import (
            _known_places,  # 懒导入：避免 settings↔chapters 循环
        )

        places = await _known_places(db, project)
    except Exception:  # noqa: BLE001, S110 — 世界设定/地点取不到时名册退化为空，规则里有兜底
        pass

    return {"characters": chars, "factions": factions, "places": places}


def roster_text(names: dict[str, set[str]]) -> str:
    """名册 → 提示词块：把清单摆出来（只准用表里的）。"""
    rows = (
        ("人物（含别名）", names.get("characters") or set()),
        ("势力 / 组织", names.get("factions") or set()),
        ("地点", names.get("places") or set()),
    )
    lines = ["【本书专名册（产出里提到的人物 / 势力 / 地点，名字只能取这张表）】"]
    for label, items in rows:
        vals = "、".join(sorted(items))
        lines.append(f"- {label}：{vals if vals else '（本书未登记——这一类要提就退到通称，不要新起专名）'}")
    return "\n".join(lines)


# 组织/派系类词尾（确定性扫描用）：产出里以这些字收尾、且不在已知侧的名字，判为"名册外的专名"。
# 为什么需要它：模型自报 names 会**漏报真问题**（2026-09-27 真机实测：旧派系词没申报，
# 反倒把地点误报一串）。对拍不能只依赖自报——加一层与模型无关的扫描。
_ORG_SUFFIXES = (
    # 过泛词尾（局/署/门/社/队）已剔除：实测生成噪声（「结局」「格局」类）
    "派", "会", "团", "教", "帮", "军", "阁", "盟",
    # 「家族」过泛（「血族家族」这类描述词会误报）已剔除
    "议会", "兄弟会", "公国", "王朝", "商会", "协会",
)
# 候选必须是纯汉字（挡掉「，一派」「。结局」这类带标点的跨词切分）
_CJK_RE = None
_SUFFIX_RE = None

# 粘连字：跨词切出来的候选里若含这些高频虚词/动词，说明它不是专名（如「改用议会」「与豢养派」）
_GLUE_CHARS = frozenset("用的了在与和把被对从到是有让给向跟为以及等则又也都就才并而或其此该本他她它我你者个些每各不没未")


def _suffix_re():
    global _SUFFIX_RE
    if _SUFFIX_RE is None:
        import re

        suffix = "|".join(sorted(_ORG_SUFFIXES, key=len, reverse=True))
        _SUFFIX_RE = re.compile(rf"(?:{suffix})")
    return _SUFFIX_RE


def _is_clean_candidate(cand: str) -> bool:
    """候选只在"纯汉字且不含粘连字"时可用（挡标点跨词切分与虚词粘连）。"""
    return bool(cand) and all("\u4e00" <= ch <= "\u9fa5" for ch in cand) and not any(
        ch in _GLUE_CHARS for ch in cand
    )


def suspect_unregistered(
    text: str,
    *,
    names: dict[str, set[str]],
    known_text: str = "",
    limit: int = 8,
) -> list[str]:
    """确定性扫描：产出里像"组织/派系名"、但既不在名册、也没在世界设定原文里出现过的词。

    已知侧＝名册（人物/势力） ∪ `known_text`（世界设定原文——世界块里写过的词算设定内，
    如「主战派」写在势力注记里，素材给了就算数）。地点类不参与扫描：世界里的地名是散文，
    提取面本身模糊，判必误报（2026-09-27 真机实测：地点误报一串）。

    匹配方式：以词尾（派/会/议会/教团…）为锚，向前取 2–6 字窗口，**从最短候选试起**——
    命中名册或设定原文即视为合法（这样「议会内部主战派」会因「主战派」在设定里而放行）；
    全窗口都不命中时，取最短且不含粘连字的候选（「被迫与豢养派」→「豢养派」）。只提醒的
    通道，宁可漏报不误报（真机实测过误报代价：白跑一次纠正轮）。
    """
    known = {n for group in ("characters", "factions") for n in (names.get(group) or set())}
    out: list[str] = []
    raw_text = text or ""
    for m in _suffix_re().finditer(raw_text):
        suffix = m.group(0)
        window = raw_text[max(0, m.start() - 6):m.start()]
        hit = False
        pick = None
        for length in range(2, len(window) + 1):
            cand = window[-length:] + suffix
            if cand in known or (known_text and cand in known_text):
                hit = True
                break
            if pick is None and _is_clean_candidate(cand):
                pick = cand
        if hit or pick is None or pick in out:
            continue
        out.append(pick)
        if len(out) >= limit:
            break
    return out
