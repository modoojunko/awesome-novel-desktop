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
