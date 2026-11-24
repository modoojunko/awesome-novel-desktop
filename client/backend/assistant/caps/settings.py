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

# 字段 → 作家看得懂的标签（授权卡/回执共用；键名是内部契约，绝不上卡面）
# genre 不含 theme/sub_genre（c-agent-page-field-truth）：题材目录写走
# settings_genre_pick 采纳卡单一通道（前端成对写整包 PUT），不在此开第二写路。
SETTINGS_FIELD_WRITE: dict[str, dict[str, str]] = {
    "genre": {
        # 设定页字段目录（单一源）：标签逐字等于页面 02-05 的可见小标题，顺序即
        # 页面顺序（02 主句 → 02 标签 → 03-05）。read_page_fields 也读这份目录
        # ——agent 先看页面有哪些字段，再按对应键请求作家授权（2026-11-24 实锤：
        # 旧名 核心承诺/禁忌/代价设定/战场 在设定页上根本找不到）。
        "promise_note": "主要看什么",
        "core_promise": "主要看什么 · 标签",
        "forbidden_list": "绝对禁止",
        "cost_ratio": "吃苦指数",
        "battlefield": "本小说斗什么",
    },
    "story": {"synopsis": "简介"},
    "world": {
        "no_power": "现实向开关",
        "stage": "世界舞台",
        "power": "力量体系",
        "cost": "力量的代价",
        "history": "历史与旧账",
        "factions": "势力",
        "constraints": "世界铁律",
        "extra": "更多世界细节",
    },
}

# 面板名（同设定页左栏：题材 / 简介 / 世界）
SETTINGS_PANEL_ZH: dict[str, str] = {
    "genre": "题材",
    "story": "简介",
    "world": "世界",
}

# agent 字段写白名单（SETTINGS_FIELD_WRITE 的子集）：02 标签 core_promise 只做
# 页面展示/减少输入，不通过本工具写——标签走 settings_genre_core_promise 采纳卡。
SETTINGS_FIELD_AGENT_WRITE: dict[str, dict[str, str]] = {
    "genre": {
        k: v for k, v in SETTINGS_FIELD_WRITE["genre"].items() if k != "core_promise"
    },
    "story": dict(SETTINGS_FIELD_WRITE["story"]),
    "world": dict(SETTINGS_FIELD_WRITE["world"]),
}


def agent_write_error(stype: str, field: str) -> CapabilityError | None:
    """字段不可由 agent 字段写时的（人话）原因；可写返回 None。"""
    if field in SETTINGS_FIELD_AGENT_WRITE.get(stype, {}):
        return None
    label = SETTINGS_FIELD_WRITE.get(stype, {}).get(field)
    if label is None:
        return CapabilityError(f"不支持的字段：{stype}.{field}")
    if stype == "genre" and field == "core_promise":
        return CapabilityError(
            "「主要看什么 · 标签」不通过字段写改——主句写 promise_note；"
            "标签是给作家省字的短标签，用「出爽点」采纳卡。"
        )
    return CapabilityError(f"「{label}」不通过字段写改。")


def settings_field_maxlen(stype: str, field: str) -> int | None:
    """文本字段的落库上限（与 NovelGenreIn 单一源）。

    超长值在授权卡之前就说不清楚＝作家批了也写不进去（2026-11-24 实锤：
    core_promise 60 字上限，模型却把 200 字主句塞进来，连弹两张卡）。
    只认**文本字段**：列表字段的 MaxLen 是「条数」不是「字数」，误用会把
    「战场传成字符串」拒成「最多 10 字」（review 2026-11-24）。
    """
    if stype != "genre":
        return None
    from typing import get_args, get_origin

    from annotated_types import MaxLen

    from genres.novel_genre_service import NovelGenreIn

    info = NovelGenreIn.model_fields.get(field)
    if info is None:
        return None
    # list[...] 的 get_args 也含 str——先排除容器类型，再看联合/裸 str。
    if get_origin(info.annotation) in (list, tuple, set, dict):
        return None
    if info.annotation is not str and str not in get_args(info.annotation):
        return None
    return next(
        (meta.max_length for meta in info.metadata if isinstance(meta, MaxLen)), None
    )


def settings_field_overlong(
    stype: str, field: str, value: object
) -> tuple[int, int] | None:
    """值超落库上限时返回 (上限, 原始长度)；否则 None。

    与 NovelGenreIn.max_length 同口径按**原始字符串**计数——Pydantic 不忽略
    首尾空白，strip 后再比会漏放行「批了也写不进」的值（review P2，2026-11-24）。
    授权卡 preview 与写核共用本函数，避免两处判断再漂移。
    """
    if not isinstance(value, str):
        return None
    limit = settings_field_maxlen(stype, field)
    if limit is not None and len(value) > limit:
        return limit, len(value)
    return None


# ── 世界字段写：保留页面契约的原生类型（c-agent-field-write-parity）────────
# 页面：no_power=开关（bool）、history/factions/constraints/extra=条目数组、
# stage/power/cost=一段文字。旧实现一律 str(value) 落库 → 开关写反、列表读回空。
_WORLD_TEXT_FIELDS = ("stage", "power", "cost")
_WORLD_LIST_FIELDS = ("history", "factions", "constraints", "extra")
_WORLD_TRUE = ("开", "true", "1", "yes", "是")
_WORLD_FALSE = ("关", "false", "0", "no", "否")


def _world_label(field: str) -> str:
    return SETTINGS_FIELD_WRITE["world"].get(field, field)


def _normalize_world_entry(field: str, item: dict) -> dict:
    """条目键归一：factions=name/note，其余=key/value（模型给另一套键时映射）。"""
    if field == "factions":
        if "name" in item or "note" in item:
            return item
        return {
            "name": item.get("key") or item.get("name") or "",
            "note": item.get("value") or item.get("note") or "",
        }
    if "key" in item or "value" in item:
        return item
    return {
        "key": item.get("name") or item.get("key") or "",
        "value": item.get("note") or item.get("value") or "",
    }


def _coerce_world_field_value(field: str, value):
    """单字段值 → 页面契约类型；非法值抛 CapabilityError（人话）。"""
    label = _world_label(field)
    if field == "no_power":
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            s = value.strip().lower()
            if s in _WORLD_TRUE:
                return True
            if s in _WORLD_FALSE:
                return False
        raise CapabilityError(f"「{label}」只接受开/关（布尔值）。")
    if field in _WORLD_LIST_FIELDS:
        if not isinstance(value, list):
            raise CapabilityError(
                f"「{label}」要写成条目数组（每条是名目 + 内容，或一行文字）。"
            )
        entries: list = []
        for item in value:
            if isinstance(item, dict):
                entries.append(_normalize_world_entry(field, item))
            elif isinstance(item, str):
                key = item.strip()
                if not key:
                    continue
                entries.append(
                    {"name": key, "note": ""}
                    if field == "factions"
                    else {"key": key, "value": ""}
                )
            else:
                raise CapabilityError(f"「{label}」的条目只能是对象或一行文字。")
        return entries
    if field in _WORLD_TEXT_FIELDS:
        if not isinstance(value, str):
            raise CapabilityError(f"「{label}」要写成一段文字。")
        return value.strip()
    raise CapabilityError(f"不支持的字段：world.{field}")


def format_world_field_value(field: str, value) -> str:
    """世界字段值 → 页面口径（开关 开/关；条目「名目：内容」；文本原样）。"""
    if field == "no_power":
        return "开" if bool(value) else "关"
    if field in _WORLD_LIST_FIELDS:
        items = value if isinstance(value, list) else []
        parts: list[str] = []
        for item in items:
            if isinstance(item, dict):
                key = str(item.get("key") or item.get("name") or "").strip()
                val = str(item.get("value") or item.get("note") or "").strip()
                parts.append(f"{key}：{val}" if key and val else (key or val))
            else:
                parts.append(str(item).strip())
        return "；".join(p for p in parts if p)
    return str(value or "").strip()


def _human_pydantic_msg(msg: str) -> str:
    """Pydantic 常见长度/条数英文消息 → 人话（其余原样）。"""
    import re

    m = re.search(r"String should have at most (\d+) characters", msg)
    if m:
        return f"内容太长（最多 {m.group(1)} 字）"
    m = re.search(r"List should have at most (\d+) items", msg)
    if m:
        return f"条目太多（最多 {m.group(1)} 条）"
    if "Field required" in msg:
        return "缺少必填内容"
    return msg


def _world_validation_error(e: Exception) -> CapabilityError:
    from pydantic import ValidationError

    if isinstance(e, ValidationError) and e.errors():
        msg = str(e.errors()[0].get("msg", "字段值不合法"))
        return CapabilityError(f"世界设定校验失败：{_human_pydantic_msg(msg)}")
    return CapabilityError(f"世界设定校验失败：{e}")


def validate_world_field_value(field: str, value):
    """单字段形状/长度校验（不读现书）——preview 无书上下文时用。"""
    from pydantic import ValidationError

    from settings.world_model import WorldIn

    coerced = _coerce_world_field_value(field, value)
    try:
        WorldIn.model_validate({field: coerced}).model_dump()
    except ValidationError as e:
        raise _world_validation_error(e) from e
    return coerced


def build_world_field_patch(raw: dict, field: str, value) -> tuple[dict, object, object]:
    """世界单字段 patch：保留原生类型 + WorldIn 同源校验。

    返回 (待落库 merged, 写前原值, 写后新值)；失败抛 CapabilityError（人话）。
    preview 与写核共用——preview 能弹的卡必须能落库。
    """
    from pydantic import ValidationError

    from settings.world_model import WorldIn, normalize_world, put_world_merged

    coerced = _coerce_world_field_value(field, value)
    payload = normalize_world(raw)
    before = payload.get(field)
    payload[field] = coerced
    try:
        WorldIn.model_validate(payload).model_dump()
    except ValidationError as e:
        raise _world_validation_error(e) from e
    return put_world_merged(raw, payload), before, coerced


async def validate_world_field_write(root_path: str, field: str, value) -> object:
    """preview 用：读当前世界→完整合并校验，返回规范化后的新值。"""
    from filesystem.paths import KEY_TO_PATH
    from filesystem.storage import get_storage

    raw = await get_storage().read_yaml(root_path, KEY_TO_PATH["world"]) or {}
    _, _, after = build_world_field_patch(raw, field, value)
    return after


def _genre_field_error_hint(field: str, e: Exception) -> str:
    from pydantic import ValidationError

    if not isinstance(e, ValidationError) or not e.errors():
        return str(e)
    first = e.errors()[0]
    loc = ".".join(str(x) for x in first.get("loc", ()))
    msg = str(first.get("msg", "") or "字段值不合法")
    if not loc.startswith(field):
        return f"{loc} {_human_pydantic_msg(msg)}".strip()
    if field == "forbidden_list":
        return "要写成条目数组，每条是 {tagId} 或 {text}（引用词或自定义文字）。"
    if field == "battlefield":
        return "要写成字符串数组；自定义战场项不超过 20 字。"
    if field == "cost_ratio":
        return "要填 1-10 的数字。"
    if field == "core_promise":
        return (
            "最多 60 字；这段更像「主要看什么」的主句就改写到 promise_note（最多 200 字）。"
        )
    if field == "promise_note":
        return "最多 200 字。"
    return _human_pydantic_msg(msg)


def validate_genre_field_value(field: str, value):
    """题材单字段形状/上限校验（不读现卡）——02-05 无跨字段规则。"""
    from pydantic import ValidationError

    from genres.novel_genre_service import NovelGenreIn

    try:
        data = NovelGenreIn.model_validate({field: value})
    except ValidationError as e:
        label = SETTINGS_FIELD_WRITE["genre"].get(field, field)
        raise CapabilityError(
            f"「{label}」的值写不进去：{_genre_field_error_hint(field, e)}"
        ) from e
    return data.model_dump(exclude_none=True).get(field)


def validate_genre_card_patch(card: dict, field: str, value) -> dict:
    """题材单字段写：现卡合并后整卡校验；返回可落库 payload；失败人话。"""
    from pydantic import ValidationError

    from genres.novel_genre_service import NovelGenreIn

    try:
        return NovelGenreIn.model_validate({**card, field: value}).model_dump()
    except ValidationError as e:
        label = SETTINGS_FIELD_WRITE["genre"].get(field, field)
        raise CapabilityError(
            f"「{label}」的值写不进去：{_genre_field_error_hint(field, e)}"
        ) from e


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
        from settings.world_model import normalize_world

        world = await get_storage().read_yaml(project.root_path, KEY_TO_PATH["world"]) or {}
        # 与 GET 同口径：先归一化再展示（历史脏字符串不会以 repr 上卡）。
        return format_world_field_value(field, normalize_world(world).get(field))


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

    err = agent_write_error(stype, field)
    if err is not None:
        raise err
    async with async_session() as db:
        project = (
            await db.scalars(select(Novel).where(Novel.id == novel_id))
        ).first()
        if project is None:
            raise CapabilityError("书不存在或不属于当前作家。")

        if stype == "genre":
            over = settings_field_overlong(stype, field, value)
            if over is not None:
                limit, length = over
                label = SETTINGS_FIELD_WRITE[stype][field]
                raise CapabilityError(
                    f"「{label}」最多 {limit} 字，这次给了 {length} 字，写不进去。"
                )
            from genres.novel_genre_service import get_novel_genre, put_novel_genre

            card = await get_novel_genre(db, novel_id)
            before = str(card.get(field, "") or "")
            payload = validate_genre_card_patch(card, field, value)
            await put_novel_genre(db, novel_id, payload)
            await db.commit()
            return {"entity": f"settings:{stype}:{field}", "before": before, "after": str(value)}

        if stype == "story":
            story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
            before = str(story.get("synopsis", "") or "")
            story["synopsis"] = str(value).strip()
            await get_storage().write_yaml(project.root_path, "story.yaml", story)
            return {"entity": "settings:story:synopsis", "before": before, "after": story["synopsis"]}

        # world：原生类型（布尔/条目数组）+ WorldIn 同源校验；put_world_merged
        # 仍是「新 payload 整包替换」语义，单字段写前带齐 v2 现键，旧原文落 _legacy。
        raw = await get_storage().read_yaml(project.root_path, KEY_TO_PATH["world"]) or {}
        merged, before, after = build_world_field_patch(raw, field, value)
        await get_storage().write_yaml(project.root_path, KEY_TO_PATH["world"], merged)
        return {"entity": f"settings:world:{field}", "before": before, "after": after}
