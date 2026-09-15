"""settings/render.py — writing-style / anti-ai → prompt 字符串渲染（ADR-006）。

设定数据存在 dict/list 双态：模板盘文件 core_principles 为按类别分组的 dict、
前端/AI 保存为 list；depiction_techniques 模板为 {name/description/example}
列表、旧数据/AI 生成为 {category: desc} dict。所有提示词组装统一经此模块
收敛，容忍双态、缺省安全（不抛错、返回空串）。

量化段（style-settings-v2）：BASELINE_ROWS/tolerance_for 单源在
style_quant_model（渲染函数内延迟引用，避免模型↔渲染循环依赖）。
"""


def _as_str_list(v) -> list[str]:
    """str/任意列表 → 去空白字符串列表（本模块内联版，避免反向依赖）。"""
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def _tolerance_for(confidence: int) -> int:
    if confidence >= 70:
        return 10
    if confidence >= 50:
        return 20
    return 30


def flatten_principles(core_principles) -> list[str]:
    """core_principles → 扁平字符串列表。

    dict（模板：global_rules/natural_expression/... 分类）→ 合并全部列表值；
    list（前端/AI 保存）→ 原样返回；缺失/其他类型 → []。
    """
    if isinstance(core_principles, dict):
        out: list[str] = []
        for values in core_principles.values():
            if isinstance(values, list):
                out.extend(str(v) for v in values)
        return out
    if isinstance(core_principles, list):
        return [str(v) for v in core_principles]
    return []


def fmt_mistakes(mistakes) -> str:
    """possible_mistakes → 单行字符串（分号连接）。

    list（模板/前端保存）→ "；".join；str → 原样；缺失 → ""。
    """
    if isinstance(mistakes, list):
        return "；".join(str(m) for m in mistakes)
    if isinstance(mistakes, str):
        return mistakes
    return ""


def depiction_techniques_str(style) -> str:
    """depiction_techniques → 逐行 "- ..." 字符串。

    list[{name/description/example}]（模板）→ 逐条 "- name：description"；
    list[str]（前端表单归一保存）→ 逐行 "- item"；
    dict（旧数据/AI 生成：{category: desc}）→ 逐行 "- category：desc"；
    缺失/空 → ""。
    """
    if not isinstance(style, dict):
        return ""
    techniques = style.get("depiction_techniques")
    if isinstance(techniques, list):
        lines = []
        for t in techniques:
            if isinstance(t, dict):
                name = t.get("name", "")
                description = t.get("description", "")
                if name and description:
                    lines.append(f"- {name}：{description}")
                elif description:
                    lines.append(description)
            elif isinstance(t, str) and t.strip():
                lines.append(f"- {t.strip()}")
        return "\n".join(lines)
    if isinstance(techniques, dict):
        return "\n".join(f"- {k}：{v}" for k, v in techniques.items() if v)
    return ""


def _fmt_list(v) -> str:
    """字符串或字符串列表 → "、"连接字符串。"""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "、".join(str(x) for x in v if str(x).strip())
    return ""


# ── 三区文风（style-settings-v2）──────────────────────────────────
# 身份→红线→手法单一来源；possible_mistakes 行与「叙事基调」块退役
# （通用反模式归禁用词句面板，基调经 normalize_style 拆并）。
# quant 段 confidence>0 才注入；容差分档 ≥70→±10% / ≥50→±20% / 其余→±30%。


def style_section(style) -> str:
    """三区文风 → 注入块：身份一句 + 红线逐条 + 手法逐行。全空 → ""。"""
    if not isinstance(style, dict):
        return ""
    lines: list[str] = []
    role = str(style.get("role", "") or "").strip()
    if role:
        lines.append(f"叙事身份：{role}")
    rules = _as_str_list(style.get("rules"))
    if rules:
        lines.append("硬约束（任何一条不得违反）：")
        lines.extend(f"- {r}" for r in rules)
    craft_text = depiction_techniques_str({"depiction_techniques": style.get("craft")})
    if craft_text:
        lines.append("描写手法：")
        lines.append(craft_text)
    return "\n".join(lines)


def quant_section(quant) -> str:
    """量化基线段：六行「约 X（±容差%）」＋章级自调指令。未蒸馏/缺失 → ""。"""
    if not isinstance(quant, dict):
        return ""
    try:
        confidence = int(quant.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    if confidence <= 0:
        return ""
    tolerance = _tolerance_for(confidence)
    baseline = quant.get("baseline") if isinstance(quant.get("baseline"), dict) else {}
    lines = [
        f"【量化文风基线（以下按「约 X（±{tolerance}%）」执行，可按本章剧情在容差内自行调节）】"
    ]
    emitted = False
    from settings.style_quant_model import BASELINE_ROWS

    for key, label in BASELINE_ROWS:
        item = baseline.get(key)
        value = str(item.get("value", "") or "").strip() if isinstance(item, dict) else ""
        if not value:
            continue
        row_tol = item.get("tolerance", tolerance)
        lines.append(f"- {label}：约 {value}（±{row_tol}%）")
        emitted = True
    return "\n".join(lines) if emitted else ""


def build_tone_section(style) -> str:  # noqa: ARG001 — 退役占位（style-settings-v2）
    """退役（style-settings-v2）：tone 块不再注入提示词，信息经 normalize_style
    拆并进三区/题材蓝图。函数仅留一版周期防未知导入，恒返回空串。"""
    return ""


