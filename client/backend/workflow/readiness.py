"""Settings readiness — content-based completion checks (PRD 3.4).

Product decision (2026-08-02):
- Creation does NOT judge settings completion (empty settings are normal).
- Judgement happens when the author clicks "完成设定" (ConfirmToggle):
  the item's content is checked; empty -> 400 + hint, non-empty -> confirmed.
- Template default values count as content (non-empty passes).

7 items are judged (ai-model is NOT part of readiness).
"""

from filesystem.storage import get_storage

# world details 子字段非空阈值（推荐值：8 个子字段中 ≥4）
WORLD_DETAILS_THRESHOLD = 4


def _has_nonempty(v) -> bool:
    """Recursively check whether a yaml value contains any non-empty scalar."""
    if isinstance(v, dict):
        return any(_has_nonempty(x) for x in v.values())
    if isinstance(v, list):
        return any(_has_nonempty(x) for x in v)
    return bool(v is not None and str(v).strip())


async def _check_synopsis(root_path: str, novel_id: str | None = None) -> bool:
    story = await get_storage().read_yaml(root_path, "story.yaml") or {}
    return bool(str(story.get("synopsis", "")).strip())


async def _check_genre(root_path: str, novel_id: str | None = None) -> bool:
    """题材就绪＝**已选题材目录（01 格大类）** 或 新契约核心键任一非空（D19 关系表）。

    题材目录落 story.yaml（`genre`/`sub_genre`，与简介同族）；01 格问的就是「什么题材」，
    本身即题材已定的最强信号（用户 2026-09-10 口径）。
    `project_settings('genre')` KV 行已废弃（不再读写）；无 novel_id 时仅看 story.yaml。
    """
    story = await get_storage().read_yaml(root_path, "story.yaml") or {}
    if str(story.get("genre", "")).strip():
        return True
    if not novel_id:
        return False
    from db import async_session
    from genres.novel_genre_service import genre_is_filled

    async with async_session() as session:
        return await genre_is_filled(session, novel_id)


async def _check_world(root_path: str, novel_id: str | None = None) -> bool:
    world = await get_storage().read_yaml(root_path, "settings/world-setting.yaml") or {}
    # 前端保存顶层 geography/politics/rules 三组对象（与写正文引擎一致），
    # 统计子字段非空数达到阈值即可确认。旧 details 结构是过时模板。
    filled = 0
    for section in ("geography", "politics", "rules"):
        sub = world.get(section)
        if not isinstance(sub, dict):
            continue
        filled += sum(1 for v in sub.values() if str(v).strip())
    return filled >= WORLD_DETAILS_THRESHOLD


async def _check_style(root_path: str, novel_id: str | None = None) -> bool:
    style = await get_storage().read_yaml(root_path, "settings/writing-style.yaml") or {}
    return bool(str(style.get("role", "")).strip())


async def _check_anti_ai(root_path: str, novel_id: str | None = None) -> bool:
    anti_ai = await get_storage().read_yaml(root_path, "settings/anti-ai.yaml") or {}
    return _has_nonempty(anti_ai)


async def _check_hooks(root_path: str, novel_id: str | None = None) -> bool:
    hooks = await get_storage().read_yaml(root_path, "settings/hooks.yaml") or {}
    # 前端保存 active/resolved/abandoned 三表（写作引擎只消费 active 悬而未决伏笔）。
    hook_list = hooks.get("active")
    if not isinstance(hook_list, list):
        return False
    return any(
        bool(str(h.get("description", "") or h.get("seed_text", "") or h.get("id", "")).strip())
        for h in hook_list
        if isinstance(h, dict)
    )


async def _check_characters(root_path: str, novel_id: str | None = None) -> bool:
    files = await get_storage().list_dir(root_path, "settings/character-setting")
    return any(f.endswith(".yaml") for f in files)


async def _check_story_arc(root_path: str, novel_id: str | None = None) -> bool:
    """主线卡：一句话主线非空，或任一分卷行有非待定内容（novels/router 同源逻辑）。"""
    from novels.router import _arc_has_content

    story = await get_storage().read_yaml(root_path, "story.yaml") or {}
    arc = story.get("story_arc")
    if not isinstance(arc, dict):
        return False
    return _arc_has_content(arc)


# 判定表（单一来源）：key -> (label, jump, checker)
READINESS_CHECKERS: list[tuple[str, str, str, object]] = [
    ("synopsis", "故事简介", "synopsis", _check_synopsis),
    ("story-arc", "主线规划", "story-arc", _check_story_arc),
    ("genre", "题材类型", "genre", _check_genre),
    ("world", "世界设定", "world", _check_world),
    ("style", "写作风格", "style", _check_style),
    ("anti-ai", "AI痕迹控制", "anti-ai", _check_anti_ai),
    ("hooks", "伏笔管理", "hooks", _check_hooks),
    ("characters", "角色管理", "characters", _check_characters),
]

READINESS_KEYS = {key for key, _label, _jump, _check in READINESS_CHECKERS}


async def compute_readiness(root_path: str, novel_id: str | None = None) -> dict:
    """Compute the 7-item content readiness.

    Returns {"complete": bool, "missing": [{key, label, jump}], "warning": str}.
    """
    missing = []
    for key, label, jump, check in READINESS_CHECKERS:
        if not await check(root_path, novel_id):  # type: ignore[operator]
            missing.append({"key": key, "label": label, "jump": jump})
    complete = not missing
    warning = (
        ""
        if complete
        else f"还差 {len(missing)} 项设定，可以先补完再开始，也可以直接开始"
    )
    return {"complete": complete, "missing": missing, "warning": warning}
