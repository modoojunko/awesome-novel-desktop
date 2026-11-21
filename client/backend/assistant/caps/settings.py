"""设定域能力核（c-tool-flow 批4：对话与面板同调一层）。

包装 settings/ai_router 的端点核（generate_field/run_hooks_ai/intro_ai——
Depends 占位按位传），失败归一 CapabilityError（人话消息，工具层直接回作家）。
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


async def generate_settings_field(
    novel_id: str, stype: str, field: str, user_id: str, context: dict | None = None
) -> dict:
    """单字段生成核（题材四问等同源）。失败抛 CapabilityError。"""
    from db import async_session
    from settings.ai_router import generate_field

    try:
        async with async_session() as db:
            return await generate_field(
                novel_id, stype, field, {"context": context or {}},
                {"id": user_id}, True, True, db,
            )
    except Exception as e:  # noqa: BLE001——HTTPException 归一
        raise _cap_error_from_http(e) from e


async def hooks_ai_action(
    novel_id: str, action: str, user_id: str, body: dict | None = None
) -> dict:
    """伏笔 AI 四能力核（draft/payoff/audit/check）。失败抛 CapabilityError。"""
    from db import async_session
    from settings.ai_router import run_hooks_ai

    try:
        async with async_session() as db:
            return await run_hooks_ai(
                novel_id, action, body or {},
                {"id": user_id}, True, True, db,
            )
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


async def intro_ai_action(
    novel_id: str, action: str, user_id: str, body: dict | None = None
) -> dict:
    """简介 AI 核（draft/check）。失败抛 CapabilityError。"""
    from db import async_session
    from settings.ai_router import intro_ai

    try:
        async with async_session() as db:
            return await intro_ai(
                novel_id, action, body or {},
                {"id": user_id}, True, True, db,
            )
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


async def arc_ai_action(
    novel_id: str,
    action: str,
    user_id: str,
    input_text: str = "",
    constraints: str = "",
) -> dict:
    """主线四能力核（draft/calibrate/check/tone）。失败抛 CapabilityError。

    input_text＝故事素材；constraints＝写法约束（只影响怎么写，不是故事内容），
    由 ai_router 在格式化 {input} 前拼成带标题的分隔块。"""
    from db import async_session
    from settings.ai_router import run_arc_ai

    try:
        async with async_session() as db:
            return await run_arc_ai(
                project_id=novel_id,
                action=action,
                body={
                    "input": str(input_text or ""),
                    "constraints": str(constraints or ""),
                },
                user={"id": user_id},
                _=True,
                __=True,
                db=db,
            )
    except Exception as e:  # noqa: BLE001
        raise _cap_error_from_http(e) from e


# ── 字段级写（c-agent-page-ops）：agent 字段写＝读现值→合并→走既有服务链 ──
# 粒度：单字段。白名单外的 stype/field 一律 CapabilityError（不静默扩权）。

SETTINGS_FIELD_WRITE: dict[str, dict[str, str]] = {
    "genre": {
        "core_promise": "核心承诺",
        "forbidden_list": "禁忌",
        "cost_ratio": "代价设定",
        "battlefield": "战场",
    },
    "story": {"synopsis": "简介"},
    "world": {k: k for k in (
        "no_power", "stage", "power", "cost", "history", "factions", "constraints", "extra",
    )},
}


async def read_settings_field(
    novel_id: str, stype: str, field: str, user_id: str
) -> str:
    """读字段现值（GET 语义；preview 构造用）。不存在/不支持抛 CapabilityError。"""
    from sqlalchemy import select

    from db import async_session
    from filesystem.paths import KEY_TO_PATH
    from filesystem.storage import get_storage
    from genres.novel_genre_service import get_novel_genre
    from models.project import Novel

    if stype not in SETTINGS_FIELD_WRITE or field not in SETTINGS_FIELD_WRITE[stype]:
        raise CapabilityError(f"不支持的字段：{stype}.{field}")
    async with async_session() as db:
        project = (
            await db.scalars(select(Novel).where(Novel.id == novel_id))
        ).first()
        if project is None:
            raise CapabilityError("书不存在或不属于当前作家。")
        if stype == "genre":
            card = await get_novel_genre(db, novel_id)
            return str(card.get(field, "") or "")
        story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
        if stype == "story":
            return str(story.get("synopsis", "") or "")
        world = await get_storage().read_yaml(project.root_path, KEY_TO_PATH["world"]) or {}
        return str(world.get(field, "") or "")


async def write_settings_field_cap(
    novel_id: str, stype: str, field: str, value, user_id: str
) -> dict:
    """设定字段写核：读现值→合并→走既有服务链；返回前后对比供 preview/write_log。

    - genre：现卡整体合并后整卡校验落库（NovelGenreIn），不覆盖未提及字段；
    - story.synopsis：story.yaml 单键写（同面板端点语义）；
    - world：v2 键合并写（put_world_merged）。
    失败抛 CapabilityError（人话）。
    """
    from sqlalchemy import select

    from db import async_session
    from filesystem.paths import KEY_TO_PATH
    from filesystem.storage import get_storage
    from models.project import Novel

    if stype not in SETTINGS_FIELD_WRITE or field not in SETTINGS_FIELD_WRITE[stype]:
        raise CapabilityError(f"不支持的字段：{stype}.{field}")
    async with async_session() as db:
        project = (
            await db.scalars(select(Novel).where(Novel.id == novel_id))
        ).first()
        if project is None:
            raise CapabilityError("书不存在或不属于当前作家。")

        if stype == "genre":
            from genres.novel_genre_service import (
                NovelGenreIn,
                get_novel_genre,
                put_novel_genre,
            )

            card = await get_novel_genre(db, novel_id)
            before = str(card.get(field, "") or "")
            merged = {**card, field: value}
            try:
                payload = NovelGenreIn.model_validate(merged).model_dump()
            except Exception as e:  # noqa: BLE001——校验失败归一人话
                raise CapabilityError(f"写入后校验不过（字段值不合法）：{e}") from e
            await put_novel_genre(db, novel_id, payload)
            await db.commit()
            return {"entity": f"settings:{stype}:{field}", "before": before, "after": str(value)}

        if stype == "story":
            story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
            before = str(story.get("synopsis", "") or "")
            story["synopsis"] = str(value).strip()
            await get_storage().write_yaml(project.root_path, "story.yaml", story)
            return {"entity": "settings:story:synopsis", "before": before, "after": story["synopsis"]}

        # world：put_world_merged 是「新 payload 整包替换」语义——单字段写必须
        # 先带齐 v2 现键再覆盖目标字段（否则清空其他键），旧原文由其落 _legacy。
        from settings.world_model import V2_KEYS, put_world_merged

        raw = await get_storage().read_yaml(project.root_path, KEY_TO_PATH["world"]) or {}
        before = str(raw.get(field, "") or "")
        payload = {k: raw.get(k) for k in V2_KEYS}
        payload[field] = str(value)
        merged = put_world_merged(raw, payload)
        await get_storage().write_yaml(project.root_path, KEY_TO_PATH["world"], merged)
        return {"entity": f"settings:world:{field}", "before": before, "after": str(value)}
