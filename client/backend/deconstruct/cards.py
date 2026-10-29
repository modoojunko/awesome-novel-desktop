"""拆书产物角色卡投影（c-character-library / c-charlib-deconstruct-exit 共用单源）。

分析稿 → 操作稿的唯一投影：证据剥除、人设兜底合成、角色定位白名单归一、
跨批同名合并、路人过滤。建书（apply.import_book）与角色库收录（library 域）
SHALL 共用本模块，禁止各写一套清洗（否则「清单上看到的角色」与「落卡结果」漂移）。

`card_to_book_payload`：扁平投影卡 → create_character 载荷（name/role/persona/
aliases/dossier 八格组装）——两处调用方共用同一条组装路径。
"""

from __future__ import annotations

import re

from deconstruct import settings_map as sm

# 角色 role 白名单映射（character_model.ROLES = 主角/配角/反派/路人）
ROLE_MAP = {"主角": "主角", "反派": "反派", "核心": "配角", "配角": "配角", "功能": "配角", "路人": "路人"}
# 越界归一扫描序（真机 13路 258 章实测：模型会写「核心反派」「反派→求助者」这类
# 复合 role）——主角/反派优先于核心/配角，防「核心反派」错标配角
ROLE_SCAN_ORDER = ("主角", "反派", "配角", "核心", "功能", "路人")

_EVIDENCE_RE = re.compile(r"【[^】]{0,50}章】")
_SENT_END = "。！？；!?！？"


def role_normalize(raw: str) -> str:
    """产物 role → 白名单四档：精确映射优先，越界值按包含词扫描，兜底配角。"""
    if raw in ROLE_MAP:
        return ROLE_MAP[raw]
    for key in ROLE_SCAN_ORDER:
        if key in raw:
            return ROLE_MAP[key]
    return "配角"


def clean_para(text, limit: int) -> str:
    """设定正文清洗：剥证据章标（【第N章】类分析工件）＋句界截断。"""
    text = _EVIDENCE_RE.sub("", str(text or "")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last = max(cut.rfind(ch) for ch in _SENT_END)
    return cut[: last + 1] if last >= limit // 2 else cut


def cards_from_products(characters_product: dict) -> list[dict]:
    """characters 维度产物 → 操作稿角色卡列表（路人不入、同名合并、证据剥离）。"""
    raw = characters_product if isinstance(characters_product, dict) else {}
    cards: list[dict] = []
    for c in raw.get("characters") or []:
        if not isinstance(c, dict):
            continue
        # 别名：新契约＝aliases 数组；旧产物＝alias 字符串（顿号/斜杠分隔）双认
        raw_aliases = c.get("aliases")
        if isinstance(raw_aliases, list):
            aliases = [str(a).strip() for a in raw_aliases if str(a or "").strip()]
        else:
            aliases = [a.strip() for a in re.split(r"[、/／]", str(c.get("alias", "") or "")) if a.strip()]
        look = str(c.get("look", "")).strip()
        # plot 是角色页「关键行动」：正文里的证据先洗净，末尾保留一条 evidence_ch
        # 供回查（#906 拍板）；其余格一律不进证据/分析尾巴。
        plot_txt = sm.clean_settings_text(c.get("plot"), None).strip()

        def _cell(v) -> str:
            return sm.clean_settings_text(v, 300)

        persona = _cell(c.get("persona", ""))
        if not persona:
            # persona＝写章必带的全卡摘要：产物缺格/模型没产出时（真机实测常见），
            # 从背景或关键行动合成一句话速写兜底——角色页人设不留空
            basis = sm.clean_settings_text(c.get("background"), None).strip()
            if not basis:
                basis = plot_txt
            if basis:
                persona = sm.clean_settings_text(basis, 60)

        evidence = str(c.get("evidence_ch", "")).strip()
        plot = plot_txt
        if plot_txt and evidence and evidence != "原文未明确":
            plot = clean_para(f"{plot_txt}（{evidence}）", 300)

        cards.append(
            {
                "name": str(c.get("name", ""))[:30],
                "role": role_normalize(str(c.get("role", "配角"))),
                "persona": persona,
                "plot": plot,
                "background": _cell(c.get("background", "")),
                "aliases": aliases[:20],
                # 产物有的格子全带（材料没写的字段产物侧已是「原文未明确」，这里置空不编造）
                "faction": _cell(c.get("faction", "")),
                "look": _cell(look),
                "speech": _cell(c.get("speech", "")),
                "gender": _cell(c.get("gender", "")),
                "age": _cell(c.get("age", "")),
                "race": _cell(c.get("race", "")),
                "confidence": str(c.get("confidence", "")),
            }
        )
    return dedupe_cards([c for c in cards if str(c.get("role", "")) != "路人"])


def dedupe_cards(cards: list[dict]) -> list[dict]:
    """同名卡归并：L1 分批各拆各的，核心角色跨批重复（13路实测 135→去重后 ~80）——
    按主名归组、可信度排序，字段非空者优先合并；路人已在调用侧过滤。"""
    conf_rank = {"high": 0, "mid": 1, "low": 2}
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for c in cards:
        name = c["name"]
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append(c)
    out: list[dict] = []
    for name in order:
        group = sorted(groups[name], key=lambda c: conf_rank.get(c.get("confidence", ""), 1))
        base: dict = {k: v for k, v in group[0].items() if str(v or "").strip()}
        for other in group[1:]:
            for k, v in other.items():
                if k != "confidence" and not str(base.get(k, "")).strip() and str(v or "").strip():
                    base[k] = v
        out.append(base)
    return out


# 书内 dossier 八格（扁平投影卡 → create_character dossier）
_DOSSIER_KEYS = ("plot", "background", "faction", "look", "speech", "gender", "age", "race")


def card_to_book_payload(card: dict, index: int) -> dict:
    """扁平投影卡 → create_character 载荷（建书与库收录共同体的那条组装路径）。

    名字空档用「未命名{i}」兜底（DB 空名会撞 UNIQUE）；调用方各自处理撞名后缀与
    主角位冲突语义（建书：每书一位主角；用到新书：落配角留痕）。
    """
    name = str(card.get("name") or "").strip() or f"未命名{index}"
    return {
        "name": name,
        "role": ROLE_MAP.get(str(card.get("role", "")), "配角"),
        "persona": str(card.get("persona", ""))[:300] or None,
        "aliases": card.get("aliases") or None,
        "dossier": {
            k: str(card.get(k, ""))[:300]
            for k in _DOSSIER_KEYS
            if str(card.get(k, "")).strip()
        },
    }
