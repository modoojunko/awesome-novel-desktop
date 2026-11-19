"""章纲域能力核（c-tool-flow 批1 样板：对话与面板同调一层）。

能力核＝业务语义入参（章 ref/排除卡名…）→ 结构化结果；大模型管线细节
（Depends 占位、面板表单 body 装配、错误归一）私有在本层。失败统一抛
CapabilityError（人话消息，工具层直接回作家）。

现状：核体暂时包装既有端点 handler（plot_simulate/cast_ai_draw/cast_ai_review
——Depends 占位按位传）；后续批3 把 handler 内的模型管线拆进本层，handler
改调本层（端点与工具单源）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CapabilityError(Exception):
    """能力核失败（message 为人话，可直接给作家）。"""

    message: str


def _cap_error_from_http(e: Exception) -> CapabilityError:
    detail = getattr(e, "detail", None)
    return CapabilityError(str(detail) if detail else str(e))


async def simulate_chapter(
    novel_id: str, chapter_ref: str, user_id: str
) -> dict:
    """剧情推演：照本章章纲与已写内容推演后续走向（不落库）。

    返回 plot_sim 核结果（ok/entry/exit/rounds…）；失败抛 CapabilityError。"""
    from db import async_session
    from write.plot_sim import plot_simulate

    try:
        async with async_session() as db:
            return await plot_simulate(
                novel_id, chapter_ref, {"id": user_id}, True, True, db,
            )
    except CapabilityError:
        raise
    except Exception as e:  # noqa: BLE001——HTTPException 归一为人话
        raise _cap_error_from_http(e) from e


async def draw_plot_proposals(
    novel_id: str,
    chapter_ref: str,
    user_id: str,
    exclude_names: list[str] | None = None,
    extra: str = "",
) -> dict:
    """剧情抽卡：照章纲门槛出互斥提案卡（不落库）。

    exclude_names＝重抽排除的上次卡名（同章纲再抽不出同一批）。
    返回 cast_ai_draw 核结果（cards/note）；失败抛 CapabilityError。"""
    from chapters.ai_cast import CastDrawBody, CastExcludeItem, cast_ai_draw
    from db import async_session

    body = CastDrawBody(
        extra=str(extra or "")[:200],
        exclude=[CastExcludeItem(name=n) for n in (exclude_names or [])][:9],
    )
    try:
        async with async_session() as db:
            return await cast_ai_draw(
                novel_id, chapter_ref, body,
                {"id": user_id}, True, True, db,
            )
    except CapabilityError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


async def review_chapter_cast(
    novel_id: str, chapter_ref: str, user_id: str
) -> dict:
    """人物盘点：逐段对照章纲与正文（只读不落库；零新增是常态输出）。

    返回 cast_ai_review 核结果（rows/quota/hints/warnings）；失败抛 CapabilityError。"""
    from chapters.ai_cast import CastReviewBody, cast_ai_review
    from db import async_session

    try:
        async with async_session() as db:
            return await cast_ai_review(
                novel_id, chapter_ref, CastReviewBody(),
                {"id": user_id}, True, True, db,
            )
    except CapabilityError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


# ── 结构管理动作（c-agent-tools-expand：route 函数直调——状态机守卫在路由内）──


async def confirm_chapter_cap(novel_id: str, chapter_ref: str, user_id: str) -> dict:
    from chapters.router import confirm_chapter as _route
    from db import async_session

    try:
        async with async_session() as db:
            return await _route(novel_id, chapter_ref, {"id": user_id}, db)
    except CapabilityError:
        raise
    except Exception as e:  # noqa: BLE001——HTTPException 归一
        raise _cap_error_from_http(e) from e


async def unconfirm_chapter_cap(novel_id: str, chapter_ref: str, user_id: str) -> dict:
    from chapters.router import unconfirm_chapter as _route
    from db import async_session

    try:
        async with async_session() as db:
            return await _route(novel_id, chapter_ref, {"id": user_id}, db)
    except CapabilityError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


async def archive_chapter_cap(novel_id: str, chapter_ref: str, user_id: str) -> dict:
    from archive.router import archive as _route
    from db import async_session

    try:
        async with async_session() as db:
            return await _route(novel_id, chapter_ref, {}, {"id": user_id}, db)
    except CapabilityError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


async def unarchive_chapter_cap(novel_id: str, chapter_ref: str, user_id: str) -> dict:
    from chapters.router import unarchive_chapter as _route
    from db import async_session

    try:
        async with async_session() as db:
            return await _route(novel_id, chapter_ref, {"id": user_id}, db)
    except CapabilityError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


async def add_volume_cap(novel_id: str, user_id: str, title: str = "") -> dict:
    from db import async_session
    from novels.service import get_novel
    from volumes.service import create_volume

    try:
        async with async_session() as db:
            project = await get_novel(db, novel_id, user_id)
            if project is None:
                raise CapabilityError("书不存在。")
            return await create_volume(db, project, title=title)
    except CapabilityError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


async def add_chapter_cap(novel_id: str, user_id: str, volume_ref: str, title: str = "") -> dict:
    from chapters.service import create_chapter
    from db import async_session
    from novels.service import get_novel

    try:
        async with async_session() as db:
            project = await get_novel(db, novel_id, user_id)
            if project is None:
                raise CapabilityError("书不存在。")
            return await create_chapter(db, project, volume_ref, title)
    except CapabilityError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


# ── 章纲字段级写（c-agent-page-ops）：读现值→patch 落库→前后对比 ──
# 键＝agent 面向作家的字段名；save_chapter patch-gates（缺键保现值）——
# 只传 provided 键映射出的 data，未提及字段零触碰。

CHAPTER_FIELD_WRITE_KEYS: dict[str, str] = {
    "summary": "概要",
    "characters": "出场角色",
    "challenge": "碰到的挑战",
    "plot_stage": "阶段",
    "ladder_exit": "章末落点",
    "plot_items": "剧情条目",
    "required_changes": "必须完成的变化",
    "prohibitions": "禁则",
    "primary_mood": "主情绪",
    "word_target": "本章目标字数",
}


def _chapter_prev_value(assembled: dict, key: str):
    outline = assembled.get("outline") if isinstance(assembled.get("outline"), dict) else {}
    memo = assembled.get("memo") if isinstance(assembled.get("memo"), dict) else {}
    emo = (
        assembled.get("emotional_design")
        if isinstance(assembled.get("emotional_design"), dict)
        else {}
    )
    ch = assembled.get("chapter") if isinstance(assembled.get("chapter"), dict) else {}
    return {
        "summary": outline.get("summary", ""),
        "characters": outline.get("characters", []),
        "challenge": assembled.get("challenge", ""),
        "plot_stage": assembled.get("plot_stage", ""),
        "ladder_exit": assembled.get("ladder_exit", ""),
        "plot_items": assembled.get("plot_items", []),
        "required_changes": memo.get("required_changes", []),
        "prohibitions": memo.get("prohibitions", []),
        "primary_mood": emo.get("primary_mood", ""),
        "word_target": ch.get("word_target"),
        "title": ch.get("title", ""),
    }.get(key)


def _chapter_data_for(key: str, value) -> dict:
    if key == "summary":
        return {"outline": {"summary": str(value)}}
    if key == "characters":
        if not isinstance(value, list):
            raise CapabilityError("出场角色必须是字符串数组（角色名列表）")
        return {"outline": {"characters": [str(x) for x in value]}}
    if key in ("challenge", "plot_stage", "ladder_exit"):
        return {key: str(value)}
    if key == "plot_items":
        if not isinstance(value, list):
            raise CapabilityError("剧情条目必须是字符串数组（一条一段场景描述）")
        return {"plot_items": [str(x) for x in value]}
    if key == "required_changes":
        if not isinstance(value, list):
            raise CapabilityError("「必须完成的变化」必须是字符串数组")
        return {"memo": {"required_changes": [str(x) for x in value]}}
    if key == "prohibitions":
        if not isinstance(value, list):
            raise CapabilityError("「禁则」必须是字符串数组")
        return {"memo": {"prohibitions": [str(x) for x in value]}}
    if key == "primary_mood":
        return {"emotional_design": {"primary_mood": str(value)}}
    if key == "word_target":
        return {"word_target": int(value)}
    if key == "title":
        return {"title": str(value)}
    raise CapabilityError(f"不支持的章纲字段：{key}")


def _chapter_after_value(data: dict, key: str):
    if key == "summary":
        return (data.get("outline") or {}).get("summary", "")
    if key == "characters":
        return (data.get("outline") or {}).get("characters", [])
    if key in ("challenge", "plot_stage", "ladder_exit"):
        return data.get(key, "")
    if key == "plot_items":
        return data.get("plot_items", [])
    if key == "required_changes":
        return (data.get("memo") or {}).get("required_changes", [])
    if key == "prohibitions":
        return (data.get("memo") or {}).get("prohibitions", [])
    if key == "primary_mood":
        return (data.get("emotional_design") or {}).get("primary_mood", "")
    if key == "word_target":
        return data.get("word_target")
    if key == "title":
        return data.get("title", "")
    return ""


async def write_chapter_fields_cap(
    novel_id: str, chapter_ref: str, user_id: str, fields: dict
) -> dict:
    """章纲字段写核：读现值→构造 patch data→save_chapter（patch-gates）。

    返回 {entity, changes:[{field,label,before,after}]}；失败抛 CapabilityError
    （人话）。plot_stage 闭集/plot_items 形状校验复用 validate_chapter_fields
    （HTTP 422 归一 CapabilityError）。
    """
    from fastapi import HTTPException
    from sqlalchemy import select

    from chapters.schemas import validate_chapter_fields
    from chapters.store import load_chapter, save_chapter
    from db import async_session
    from models.project import Novel

    if not isinstance(fields, dict) or not fields:
        raise CapabilityError("没有要写的字段。")
    unknown = [k for k in fields if k not in CHAPTER_FIELD_WRITE_KEYS]
    if unknown:
        raise CapabilityError(f"不支持的章纲字段：{'、'.join(unknown)}")

    async with async_session() as db:
        project = (
            await db.scalars(select(Novel).where(Novel.id == novel_id))
        ).first()
    if project is None:
        raise CapabilityError("书不存在或不属于当前作家。")
    root = project.root_path

    current = await load_chapter(root, chapter_ref)
    if not current:
        raise CapabilityError(f"章节 {chapter_ref} 不存在。")

    data: dict = {}
    changes: list[dict] = []
    for key, value in fields.items():
        body_probe = _chapter_data_for(key, value)
        try:
            validate_chapter_fields(body_probe)
        except HTTPException as e:  # 422 归一为人话（CapabilityError）
            raise _cap_error_from_http(e) from e
        data.update(body_probe)
        changes.append(
            {
                "field": key,
                "label": CHAPTER_FIELD_WRITE_KEYS[key],
                "before": _chapter_prev_value(current, key),
                "after": _chapter_after_value(data, key),
            }
        )
    await save_chapter(root, chapter_ref, data)
    return {
        "entity": f"chapter:{chapter_ref}",
        "changes": changes,
        "labels": [c["label"] for c in changes],
    }
