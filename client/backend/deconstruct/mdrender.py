"""拆书产物渲染单源（c-deconstruct-evidence-report）——作家 md 与证据报告。

- render_md：作家视角 Markdown。证据类字段（EVIDENCE_KEYS：证据章节/可信度/说明/
  原文佐证/原文措辞）是拆书编辑的质检账，作家阅读是噪音（2026-10-26 用户实拆反馈）——
  渲染前一律剥除，页脚章号/可信度口径说明随之退役；列表值（repro_steps/emotion_chain）
  以「；」连接为说人话文本。纯函数：同 data 同字节。
- render_evidence：证据报告视图——条目结论 head＋证据单元格，供应用内弹窗呈现；
  证据不删，搬家到报告（任务资料 data 全量保留，提示词仓契约不变）。
- md_map_from_products：产物 md 读取侧单源——一律由任务资料 data 现渲染。历史任务
  存储的 md 内嵌证据，不再被读取（预览/导出/字符数三读取方零迁移同步变干净）；
  data 缺失时回退存量 md 兜底。

建书/设定页投影不经此处（吃 data，见 settings_map）。
"""

from __future__ import annotations

from models.deconstruct import DIMENSIONS

# 条目级证据字段黑名单：只承担「证明这条结论」职责，永不进作家 md
EVIDENCE_KEYS: frozenset[str] = frozenset({"evidence_ch", "confidence", "note", "quote", "raw"})

# 产物 JSON 键 → 作家中文标签（渲染层单源；未登记的键回退原键展示）
_MD_LABELS: dict[str, str] = {
    "intro": "简介", "confidence": "可信度", "genre": "题材", "tags": "题材标签",
    "promise": "题材承诺", "no_power": "舞台类型", "stage": "地理与舞台",
    "power": "力量体系", "cost": "代价", "history": "大事记", "factions": "势力",
    "constraints": "禁忌铁律", "extra": "其他设定", "key": "名", "value": "内容",
    "characters": "人物卡", "name": "名", "aliases": "别名", "role": "定位",
    "persona": "人物速写", "gender": "性别", "age": "年龄", "race": "种族",
    "faction": "势力·身份", "look": "外貌", "speech": "语言特征",
    "background": "背景", "plot": "关键行动", "evidence_ch": "证据章节",
    "edges": "关系边", "from": "一方", "to": "另一方", "rel_type": "关系类型",
    "stance": "立场", "note": "说明", "quote": "原文佐证", "raw": "原文措辞",
    "members": "成员", "arcs": "剧情弧", "fullstory": "主线全景",
    "summary": "梗概",
    "ending": "结局", "scene": "结尾场景", "hero": "主角结局", "tone": "收束基调",
    "ch_start": "起", "ch_end": "止", "volumes": "分卷", "title": "题",
    "conflict": "冲突", "chapters": "章", "ch_range": "章范围",
    "rules": "写作规则", "craft": "表现手法", "examples": "原文短例",
    "example": "例", "how": "怎么用", "taboo": "避免的写法",
    "hooks": "伏笔", "type": "类型", "priority": "重要度", "desc": "内容",
    "plant_ch": "埋设章", "payoff_ch": "回收章", "status": "状态",
    "result": "结果",
    # 写作技法新契约（呈现说人话：不再裸出英文键）
    "reader_needs": "读者需求", "need": "读者需求", "transferable": "可迁移",
    "techniques": "可复现模块卡", "emotion_chain": "情绪链", "repro_steps": "复现步骤",
    "swappable": "可替换", "no_copy": "勿照搬", "borrowable": "可借鉴套路",
    "avoid": "不建议模仿", "item": "条目",
}
_CONF_CN = {"high": "高", "mid": "中", "low": "低"}
# 同键不同维度的标签：role 在角色卡是「定位」，在文风是「叙事身份」
_DIM_LABEL_OVERRIDES: dict[str, dict[str, str]] = {
    "写作文风": {"role": "叙事身份"},
    "style": {"role": "叙事身份"},
}
# 维度 key → 中文名（DIMENSIONS 顺序即执行序；报告按此序呈现）
_DIM_NAMES: dict[str, str] = {k: cn for k, cn, _ in DIMENSIONS}
# 证据报告条目 head 候选：条目结论的「说法」字段
_HEAD_KEYS: tuple[str, ...] = ("name", "title", "desc", "item", "need")


def _label(dim: str, key: str) -> str:
    return _DIM_LABEL_OVERRIDES.get(dim, {}).get(key) or _MD_LABELS.get(key, key)


def _join_list(value, joiner: str = "；") -> str:
    """列表值 → 说人话单行（SHALL NOT 出现 Python 列表 repr）。"""
    return joiner.join(str(x).strip() for x in value if str(x or "").strip())


def _cell_value(key: str, value) -> str:
    if isinstance(value, (list, tuple)):
        # 章号列表顿号（第1、7、12章口径）；其余列表「；」连接
        text = _join_list(value, "、" if key == "evidence_ch" else "；")
    else:
        text = str(value or "").strip()
    if not text:
        return ""
    if key == "confidence":
        text = _CONF_CN.get(text, text)
    return text


def _md_cell(key: str, value) -> str:
    """单个字段 → 「中文标签：值」；confidence 值翻成高/中/低；空值不给。"""
    text = _cell_value(key, value)
    if not text:
        return ""
    return f"{_MD_LABELS.get(key, key)}：{text}"


def _strip_evidence(item: dict) -> dict:
    """条目剥证据字段；剥完没剩内容字段的条目整体不出。"""
    return {k: v for k, v in item.items() if k not in EVIDENCE_KEYS and v}


def render_md(dim_name: str, data, book_name: str, covered: str) -> str:
    """JSON → Markdown（代码渲染：模型不直出 md）。证据类字段不入作家 md
    （c-deconstruct-evidence-report：2026-10-26 拍板——证据搬家到证据报告）。
    """
    if not isinstance(data, dict):
        data = {"result": data}
    lines = [
        f"# {dim_name}｜{book_name}",
        "",
        f"> 覆盖范围：{covered} · 由拆书任务生成",
        "",
    ]
    for key, value in data.items():
        if key in EVIDENCE_KEYS:
            continue  # 证据类字段（含顶层单值 confidence）一律不入作家 md
        # 无正文不出节：空列表/空对象/空标量只给标题的空节对作家是噪音（评审 P3）
        if not value or (isinstance(value, (dict, list, str)) and not str(value).strip()):
            continue
        if isinstance(value, list):
            rows = [
                item if not isinstance(item, dict) else _strip_evidence(item)
                for item in value
            ]
            rows = [r for r in rows if r]
            if not rows:  # 条目全是证据壳（如只有 evidence_ch/note）→ 整节不出
                continue
            value = rows
        lines.append(f"## {_label(dim_name, key)}")
        lines.append("")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    head_key = next((k for k in ("name", "title", "desc") if str(item.get(k, "")).strip()), "")
                    head = str(item.get(head_key, "")).strip() if head_key else ""
                    body = "；".join(
                        cell for cell in (
                            _md_cell(k, v) for k, v in item.items()
                            if k not in ("name", "title") and v
                        ) if cell
                    )
                    lines.append(f"- {('**' + head + '**　') if head else ''}{body}")
                else:
                    lines.append(f"- {item}")
        elif isinstance(value, dict):
            # 对象值（如 mainplot.ending 三格）：逐字段展开成中文标签行，
            # 不给 Python dict repr（评审 P1：作家看到 {'scene': …} 原文）
            for k, v in value.items():
                cell = _md_cell(k, v)
                if cell:
                    lines.append(f"- {cell}")
        else:
            # 标量节正文＝裸值（标签已在节标题；再带前缀会「标题×2」）
            lines.append(str(value or "").strip())
        lines.append("")
    return "\n".join(lines)


def _evidence_head(item: dict) -> str:
    """条目结论 head：让证据能对回作家 md 里的那条结论。"""
    for k in _HEAD_KEYS:
        text = str(item.get(k, "") or "").strip()
        if text:
            return text
    if "from" in item or "to" in item:  # 关系边：一方 → 另一方
        edge = f"{item.get('from', '')} → {item.get('to', '')}".strip(" →")
        if edge.replace(" ", ""):
            return edge
    for k, v in item.items():  # 兜底：首个内容字段截 40 字
        if k not in EVIDENCE_KEYS:
            text = str(v or "").strip()
            if text:
                return text[:40]
    return ""


def render_evidence(dim: str, data) -> dict:
    """单维度证据视图：{dim, name, confidence, sections:[{title, items:[{head, cells}]}]}。

    只收有证据字段的条目与节；无证据维度 sections 为空、confidence 为空串。
    """
    name = _DIM_NAMES.get(dim, dim)
    if not isinstance(data, dict):
        return {"dim": dim, "name": name, "confidence": "", "sections": []}
    raw_conf = str(data.get("confidence", "")).strip()
    conf_top = _CONF_CN.get(raw_conf, raw_conf) if raw_conf else ""  # 未知档原样回显
    sections: list[dict] = []
    for key, value in data.items():
        if key in EVIDENCE_KEYS or not isinstance(value, list):
            continue
        items: list[dict] = []
        for entry in value:
            if not isinstance(entry, dict):
                continue
            cells = [
                {"label": _MD_LABELS.get(k, k), "value": _cell_value(k, v)}
                for k, v in entry.items()
                if k in EVIDENCE_KEYS and _cell_value(k, v)
            ]
            if not cells:
                continue
            items.append({"head": _evidence_head(entry), "cells": cells})
        if items:
            sections.append({"title": _label(dim, key), "items": items})
    return {"dim": dim, "name": name, "confidence": conf_top, "sections": sections}


def evidence_report(products_raw: dict) -> list[dict]:
    """全任务证据账：按维度执行序排列，只下发有证据内容的维度。"""
    report: list[dict] = []
    for key, _, _ in DIMENSIONS:
        obj = (products_raw or {}).get(key)
        if not isinstance(obj, dict):
            continue
        view = render_evidence(key, obj.get("data"))
        if view["sections"] or view["confidence"]:
            view["file"] = obj.get("file", "")
            report.append(view)
    return report


def md_map_from_products(products_raw: dict, book_name: str, covered: str) -> dict[str, str]:
    """产物 md 读取侧单源：data 现渲染（同 data 同字节），缺失回退存量 md 兜底。"""
    out: dict[str, str] = {}
    for dim, obj in (products_raw or {}).items():
        if not isinstance(obj, dict) or not obj.get("file"):
            continue
        data = obj.get("data")
        if isinstance(data, dict) and data:
            out[obj["file"]] = render_md(_DIM_NAMES.get(dim, dim), data, book_name, covered)
        else:
            out[obj["file"]] = obj.get("md", "")
    return out
