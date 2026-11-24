"""页面字段说明书（c-agent-field-write-parity）。

`read_page_schema` 的实现层：给 agent 一份「当前页面有哪些字段、各叫什么、什么
类型、能不能直接写」的元数据，供它把作家的说法（精确/近义）对到字段键。

边界：
- 只描述**有字段级写入口**的页面（设定题材/简介/世界、章纲、卷纲）；其余页面
  如实说「本页没有字段级写入口」，不编字段。
- 只给元数据，不给现值；现值用 `read_page_fields`（设定）/`read_chapter`（章纲）。
- 标签复用写作核的字段表（SETTINGS_FIELD_WRITE / CHAPTER_FIELD_WRITE_KEYS），
  不在本模块另抄一份，避免再漂移。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldMeta:
    key: str
    label: str
    kind: str
    limit: str = ""
    write: str = ""  # 写入口（工具名或采纳卡名）
    aliases: tuple[str, ...] = field(default_factory=tuple)


def _genre_fields() -> list[FieldMeta]:
    from assistant.caps.settings import SETTINGS_FIELD_WRITE

    labels = SETTINGS_FIELD_WRITE["genre"]
    return [
        FieldMeta(
            "theme/sub_genre", "01 题材", "题材目录（大类 + 子类）",
            write="settings_genre_pick 采纳卡",
            aliases=("题材", "什么题材", "大类", "子类"),
        ),
        FieldMeta(
            "promise_note", labels["promise_note"], "一句话（作家写的那句）", "≤200 字",
            write="write_settings_field",
            aliases=("主句", "读者预期", "那句话"),
        ),
        FieldMeta(
            "core_promise", labels["core_promise"], "短标签", "≤60 字",
            write="settings_genre_core_promise 采纳卡（页面标签，不直接写）",
            aliases=("标签", "核心承诺", "短标签"),
        ),
        FieldMeta(
            "forbidden_list", labels["forbidden_list"], "条目数组（[{tagId} 或 {text}]）",
            "≤50 条", write="write_settings_field",
            aliases=("禁区", "红线", "禁写"),
        ),
        FieldMeta(
            "cost_ratio", labels["cost_ratio"], "整数", "1-10",
            write="write_settings_field",
            aliases=("代价", "吃苦"),
        ),
        FieldMeta(
            "battlefield", labels["battlefield"], "字符串数组", "≤10 项，自定义项≤20 字",
            write="write_settings_field",
            aliases=("战场", "斗什么", "对抗物"),
        ),
    ]


def _world_fields() -> list[FieldMeta]:
    from assistant.caps.settings import SETTINGS_FIELD_WRITE

    labels = SETTINGS_FIELD_WRITE["world"]
    return [
        FieldMeta(
            "no_power", labels["no_power"], "布尔（开/关）",
            write="write_settings_field", aliases=("现实向", "超自然力量"),
        ),
        FieldMeta("stage", labels["stage"], "一段文字", "≤300 字", "write_settings_field"),
        FieldMeta("power", labels["power"], "一段文字", "≤300 字", "write_settings_field"),
        FieldMeta("cost", labels["cost"], "一段文字", "≤300 字", "write_settings_field"),
        FieldMeta(
            "history", labels["history"], "条目数组（每条 {key,value}）",
            "≤100 条", "write_settings_field", aliases=("历史", "旧事"),
        ),
        FieldMeta(
            "factions", labels["factions"], "条目数组（每条 {name,note}）",
            "≤6 条", "write_settings_field", aliases=("势力", "势力名单"),
        ),
        FieldMeta(
            "constraints", labels["constraints"], "条目数组（每条 {key,value}）",
            "≤10 条", "write_settings_field", aliases=("铁律", "硬边界"),
        ),
        FieldMeta(
            "extra", labels["extra"], "条目数组（每条 {key,value}）",
            "≤50 条", "write_settings_field", aliases=("细节", "杂项"),
        ),
    ]


def _chapter_fields() -> list[FieldMeta]:
    from assistant.caps.chapter import CHAPTER_FIELD_WRITE_KEYS

    labels = CHAPTER_FIELD_WRITE_KEYS
    return [
        FieldMeta("summary", labels["summary"], "一段文字", write="write_chapter_fields",
                  aliases=("概要", "这一章写什么")),
        FieldMeta("characters", labels["characters"], "字符串数组（角色名）",
                  write="write_chapter_fields"),
        FieldMeta("challenge", labels["challenge"], "一段文字", write="write_chapter_fields"),
        FieldMeta("plot_stage", labels["plot_stage"], "六档之一",
                  write="write_chapter_fields",
                  aliases=("开局铺垫", "冲突初现", "矛盾升级", "重要转折", "高潮爆发", "卷末收束")),
        FieldMeta("ladder_exit", labels["ladder_exit"], "一段文字",
                  write="write_chapter_fields", aliases=("落点", "结尾停在哪")),
        FieldMeta("plot_items", labels["plot_items"], "字符串数组（一条一段场景）",
                  write="write_chapter_fields", aliases=("剧情条目", "场景")),
        FieldMeta("required_changes", labels["required_changes"], "字符串数组",
                  write="write_chapter_fields", aliases=("变化", "必须发生")),
        FieldMeta("prohibitions", labels["prohibitions"], "字符串数组",
                  write="write_chapter_fields", aliases=("禁则", "禁止发生")),
        FieldMeta("primary_mood", labels["primary_mood"], "一段文字", "≤50 字",
                  write="write_chapter_fields", aliases=("情绪", "读者感受")),
        FieldMeta("word_target", labels["word_target"], "数字", "整数",
                  write="write_chapter_fields", aliases=("目标字数", "字数")),
    ]


def _volume_fields() -> list[FieldMeta]:
    return [
        FieldMeta("title", "卷名", "一段文字", write="write_volume_fields"),
        FieldMeta("summary", "本卷主旨", "一段文字", write="write_volume_fields",
                  aliases=("这一卷讲什么", "主旨")),
        FieldMeta("core_conflict", "主要冲突", "一段文字", write="write_volume_fields",
                  aliases=("核心矛盾", "冲突")),
        FieldMeta("ending", "卷末收在哪里", "一段文字", write="write_volume_fields",
                  aliases=("卷末", "结局")),
        FieldMeta("chapter_target", "章数目标", "数字", "1-9999",
                  write="write_volume_fields", aliases=("章数", "几章")),
        FieldMeta("antagonist_type", "坎的类型", "一段文字", write="write_volume_fields",
                  aliases=("反派类型", "坎")),
        FieldMeta("antagonist_line", "坎的一句话", "一段文字", write="write_volume_fields",
                  aliases=("反派线", "反派的一句话")),
    ]


_PAGES: dict[str, tuple[str, Callable[[], list[FieldMeta]]]] = {
    "set:genre": ("设定 · 题材", _genre_fields),
    "set:intro": ("设定 · 简介", lambda: [
        FieldMeta("synopsis", "简介", "一段文字", write="write_settings_field"),
    ]),
    "set:world": ("设定 · 世界", _world_fields),
    "ch:og": ("章纲", _chapter_fields),
    "vol": ("卷纲", _volume_fields),
}

_UNSUPPORTED = {
    "set:chars": "设定 · 角色",
    "set:arc": "设定 · 主线",
    "set:style": "设定 · 文风",
    "set:foreshadow": "设定 · 伏笔",
    "set:aiModel": "设定 · 模型设定",
    "ch:prose": "正文",
    "ch:settings": "章节设定",
    "ch:relations": "角色关系",
    "ch:hooks": "伏笔",
    "ch:actions": "章节操作",
    "ch:style": "文风",
    "preview": "预览",
}


def _page_of_thread(thread: str) -> str:
    thread = (thread or "").strip()
    if thread.startswith("set:"):
        return thread if thread in _PAGES or thread in _UNSUPPORTED else "set:"
    for prefix in _PAGES:
        if thread == prefix or thread.startswith(f"{prefix}"):
            return prefix
    return thread


def render_page_schema(thread: str) -> str:
    """当前页面的字段说明书（页面说法 → 字段键｜类型/上限｜写入口）。"""
    page = _page_of_thread(thread)
    if page == "set:":
        return "当前页面没有指定具体的设定面板；先确认作家在哪个面板。"
    if page in _UNSUPPORTED:
        return (
            f"当前页面：{_UNSUPPORTED[page]}（本页没有字段级写入口；"
            "写/改请走对应面板或 AI 卡）。现值用 read_page_fields 查。"
        )
    entry = _PAGES.get(page)
    if entry is None:
        return "当前页面无法识别；先确认作家在哪个页面，别猜字段。"
    title, builder = entry
    lines = [
        f"当前页面：{title}",
        "字段说明书（作家说法 → 字段键｜类型/上限｜写入口）：",
    ]
    for f in builder():
        alias = f"（别名：{'/'.join(f.aliases)}）" if f.aliases else ""
        limit = f"，{f.limit}" if f.limit else ""
        write = f"｜{f.write}" if f.write else ""
        lines.append(f"- {f.label}{alias} → {f.key}｜{f.kind}{limit}{write}")
    lines.append(
        "匹配：先按页面说法精确匹配；别名/近义走语义匹配；仍不唯一就用字段名问一句，不猜。"
        "只写本表列出的字段；现值用 read_page_fields（设定）/read_chapter（章纲）/"
        "read_outline（卷纲）查。"
    )
    return "\n".join(lines)
