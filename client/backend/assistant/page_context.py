"""页面字段上下文（c-agent-page-context）。

作家在设定页说「这个/这格/这里」时，模型需要知道当前面板有哪些字段、现在填的是什么。
前端随消息带 `page_state.panel`，本模块按面板读当前值，拼一行紧凑的 L2 注入：

  ［本页字段：01 题材＝都市脑洞 / 战神赘婿；02 主要看什么＝…；…］

只进当轮提示词（不落库、不渲染）；读失败 fail-soft 为空串，不打断对话。
值一律裁短，避免把整段正文/长清单灌进上下文。
"""

from __future__ import annotations

from typing import Any

# 前端 SettingsView 的面板键 → 人话
PANEL_LABELS: dict[str, str] = {
    "genre": "题材",
    "intro": "简介",
    "world": "世界",
    "chars": "角色",
    "arc": "主线",
    "style": "文风",
    "foreshadow": "伏笔",
    "aiModel": "模型设定",
}

# 章内页签键 → 人话（chapterTab 只报页签，字段细节由 read_* 工具按需读）
CHAPTER_TAB_LABELS: dict[str, str] = {
    "og": "章纲",
    "prose": "正文",
    "settings": "设定",
    "relations": "角色关系",
    "hooks": "伏笔",
    "actions": "操作",
    "style": "文风",
}

_BUDGET = 800


def _clip(text: Any, budget: int = 80) -> str:
    s = str(text or "").strip().replace("\n", " ")
    if not s:
        return "未填"
    return s if len(s) <= budget else s[: budget - 1] + "…"


def _list_text(v: Any, budget: int = 80) -> str:
    if isinstance(v, list):
        parts = []
        for x in v:
            if isinstance(x, dict):
                parts.append(str(x.get("text") or x.get("name") or x.get("tagId") or ""))
            else:
                parts.append(str(x or ""))
        return _clip("、".join(p for p in parts if p), budget)
    return _clip(v, budget)


def format_genre_fields(card: dict[str, Any], story: dict[str, Any]) -> str:
    """01 题材目录＋02-05 四格的当前值（纯函数，便于单测）。"""
    theme = str(story.get("genre") or card.get("theme") or "").strip()
    sub = str(story.get("sub_genre") or card.get("sub_genre") or "").strip()
    theme_text = f"{theme} / {sub}" if theme and sub else (theme or "未填")
    promise = str(card.get("core_promise") or "").strip()
    promise_note = str(card.get("promise_note") or "").strip()
    promise_text = "；".join(p for p in (promise, promise_note) if p) or "未填"
    rows = [
        f"01 题材＝{theme_text}",
        f"02 主要看什么＝{_clip(promise_text, 100)}",
        f"03 绝对禁止＝{_list_text(card.get('forbidden_list'), 100)}",
        f"04 吃苦指数＝{_clip(card.get('cost_ratio'), 20)}",
        f"05 本小说斗什么＝{_list_text(card.get('battlefield'), 100)}",
    ]
    return "；".join(rows)


async def _genre_fields(novel: Any) -> str:
    from db import async_session
    from filesystem.storage import get_storage
    from genres.novel_genre_service import get_novel_genre

    async with async_session() as db:
        card = await get_novel_genre(db, novel.id)
    story = await get_storage().read_yaml(novel.root_path, "story.yaml") or {}
    return format_genre_fields(card, story)


async def _intro_fields(novel: Any) -> str:
    from filesystem.storage import get_storage

    story = await get_storage().read_yaml(novel.root_path, "story.yaml") or {}
    return f"简介＝{_clip(story.get('synopsis'), 180)}"


async def _world_fields(novel: Any) -> str:
    from assistant.caps.settings import SETTINGS_FIELD_WRITE
    from filesystem.paths import KEY_TO_PATH
    from filesystem.storage import get_storage

    world = await get_storage().read_yaml(novel.root_path, KEY_TO_PATH["world"]) or {}
    labels = SETTINGS_FIELD_WRITE["world"]
    rows = [
        f"{label}（{key}）＝{_clip(world.get(key), 70)}"
        for key, label in labels.items()
    ]
    return "；".join(rows)


async def _arc_fields(novel: Any) -> str:
    from filesystem.storage import get_storage

    story = await get_storage().read_yaml(novel.root_path, "story.yaml") or {}
    arc = story.get("story_arc") or {}
    ending = arc.get("ending") or {}
    rows = [
        f"这本书从头到尾说什么＝{_clip(arc.get('fullstory'), 180)}",
        f"结局画面＝{_clip(ending.get('scene'), 100)}",
        f"主角终态＝{_clip(ending.get('hero'), 100)}",
        f"结局基调＝{_clip(ending.get('tone'), 80)}",
    ]
    return "；".join(rows)


async def _style_fields(novel: Any) -> str:
    from filesystem.paths import KEY_TO_PATH
    from filesystem.storage import get_storage
    from settings.style_model import read_style

    raw = await get_storage().read_yaml(novel.root_path, KEY_TO_PATH["style"]) or {}
    style = read_style(raw)
    rows = [
        f"叙事身份＝{_clip(style.get('role'), 100)}",
        f"硬约束＝{_list_text(style.get('rules'), 100)}",
        f"描写手法＝{_list_text(style.get('craft'), 100)}",
        f"禁用词＝{_list_text(style.get('banned_words'), 80)}",
        f"句式规则＝{_list_text(style.get('tic_patterns'), 80)}",
    ]
    return "；".join(rows)


async def _chars_fields(novel: Any) -> str:
    from db import async_session
    from settings.character_service import list_characters

    async with async_session() as session:
        data = await list_characters(session, novel.id)
    items = data.get("items") or []
    if not items:
        return "角色＝（暂无）"
    rows = [f"{it.get('name', '')}（{it.get('role', '')}）" for it in items[:12]]
    return "角色＝" + "、".join(r for r in rows if r.strip())


async def _hooks_fields(novel: Any) -> str:
    from prompt.context import load_active_hooks

    hooks = await load_active_hooks(novel.id)
    if not hooks:
        return "伏笔＝（暂无在途）"
    rows = [str(h.get("title") or h.get("name") or "") for h in hooks[:10]]
    return "伏笔＝" + "、".join(r for r in rows if r)


async def build_page_field_note(novel: Any, panel: str) -> str:
    """当前设定面板的字段清单＋当前值；未知面板/读失败返回空串。"""
    panel = str(panel or "").strip()
    label = PANEL_LABELS.get(panel)
    if not label:
        return ""
    builder = {
        "genre": _genre_fields,
        "intro": _intro_fields,
        "world": _world_fields,
        "arc": _arc_fields,
        "style": _style_fields,
        "chars": _chars_fields,
        "foreshadow": _hooks_fields,
    }.get(panel)
    if builder is None:
        return f"［当前设定面板：{label}］"
    try:
        body = await builder(novel)
    except Exception:  # noqa: BLE001
        # 读失败不打断对话（页面上下文是增强，不是闸）
        return f"［当前设定面板：{label}（字段读取失败，按面板名理解）］"
    text = f"［当前设定面板：{label}；本页字段：{body}］"
    if len(text) > _BUDGET:
        text = text[: _BUDGET - 1] + "…］"
    return text
