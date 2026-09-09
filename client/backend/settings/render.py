"""settings/render.py — writing-style / anti-ai → prompt 字符串渲染（ADR-006）。

设定数据存在 dict/list 双态：模板盘文件 core_principles 为按类别分组的 dict、
前端/AI 保存为 list；depiction_techniques 模板为 {name/description/example}
列表、旧数据/AI 生成为 {category: desc} dict。所有提示词组装统一经此模块
收敛，容忍双态、缺省安全（不抛错、返回空串）。
"""


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


def build_tone_section(style) -> str:
    """writing-style → 「## 叙事基调」markdown 块（ADR-007）。

    从 style.narrator_role + style.tone{default_tone, atmosphere, pov, techniques}
    + style.chapter_types/pacing_rules（6.0c 从题材行迁来）渲染。
    全部缺失/为空 → ""（不注入空块）。
    题材库不再注入基调（见 genres/service.resolve_genre_context 停用）。
    """
    if not isinstance(style, dict):
        return ""
    narrator_role = style.get("narrator_role", "")
    tone = style.get("tone")
    has_extras = bool(style.get("chapter_types") or style.get("pacing_rules"))
    if not narrator_role and not isinstance(tone, dict) and not has_extras:
        return ""
    lines = ["## 叙事基调"]
    if narrator_role:
        lines.append(f"叙事者角色：{narrator_role}")
    if isinstance(tone, dict):
        if tone.get("default_tone"):
            lines.append(f"默认基调：{tone['default_tone']}")
        if tone.get("atmosphere"):
            lines.append(f"氛围：{_fmt_list(tone['atmosphere'])}")
        if tone.get("pov"):
            lines.append(f"叙事视角：{_fmt_list(tone['pov'])}")
        if tone.get("techniques"):
            lines.append(f"描写技法：{_fmt_list(tone['techniques'])}")
    # 6.0c 迁移：原题材行 config_overrides.chapter_types / pacing_rules
    if style.get("chapter_types"):
        lines.append("章节类型：" + _fmt_list(style["chapter_types"]))
    if style.get("pacing_rules"):
        lines.append("节奏规则：" + _fmt_list(style["pacing_rules"]))
    if len(lines) == 1:
        return ""  # 全空（仅标题无内容）不注入空块
    return "\n".join(lines)
