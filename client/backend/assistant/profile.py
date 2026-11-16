"""作家画像（c-writing-agent 批C 3.2-3.4）。

openwriter memory 模式（拍板⑤）：画像更新不弹授权卡（改的是助手自己的认知，
不是作家数据），配四个保命条件——
  ①画像页可查看/可编辑/可一键清空（端点见 router /profile 系）
  ②写画像时对话里透明告知一句（loop 经 profile 工具的 result 摘要天然呈现）
  ③敏感类目先问再存（SENSITIVE_HINTS：写入敏感分区时 result 要求助手先问）
  ④「暂停画像学习」开关（paused=True 时后台总结与工具写入都停，已有内容保留）

结构：作家级（跨书）sections_json 分区 naming/pet_peeves/pacing/style/freeform；
书级沿用既有书设置不另起炉灶。定期总结＝后台任务（autotitle 模式：非阻塞/防重入/
失败静默），数据源＝writer_profile_events（采纳/拒绝/修改/对话收集）。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.assistant import WriterProfile, WriterProfileEvent

logger = logging.getLogger(__name__)

# 定期总结触发：事件数达到该值即总结一轮（env 可调）
SUMMARY_EVERY_EVENTS = 20
# 敏感类目：先问再存（openwriter 保守保存纪律 agent.py L84-86 同款）
SENSITIVE_KEYS = ("income", "contract", "identity", "red_line")
SENSITIVE_NOTICE = "（这条涉及敏感信息——先跟你确认：要记进画像吗？）"

_PROFILE_SECTIONS = ("naming", "pet_peeves", "pacing", "style", "freeform")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def get_or_create_profile(db: AsyncSession, user_id: str) -> WriterProfile:
    row = (
        await db.scalars(select(WriterProfile).where(WriterProfile.user_id == user_id))
    ).first()
    if row is None:
        row = WriterProfile(
            user_id=user_id, sections_json="{}", paused=False, updated_at=_now()
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def load_sections(db: AsyncSession, user_id: str) -> dict[str, Any]:
    row = await get_or_create_profile(db, user_id)
    try:
        data = json.loads(row.sections_json or "{}")
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


async def record_event(
    db: AsyncSession,
    *,
    user_id: str,
    novel_id: str = "",
    kind: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """画像行为事件（采纳/拒绝/修改/对话收集/总结）——定期总结的数据源。"""
    db.add(
        WriterProfileEvent(
            id=uuid.uuid4().hex,
            user_id=user_id,
            novel_id=novel_id or "",
            kind=kind,
            payload_json=json.dumps(payload or {}, ensure_ascii=False),
            created_at=_now(),
        )
    )
    await db.commit()


async def update_sections(
    db: AsyncSession,
    *,
    user_id: str,
    novel_id: str = "",
    updates: dict[str, Any],
    kind: str = "chat_collect",
) -> dict[str, Any]:
    """合并写入画像分区（dict 深合并一层；list 追加去重）。写事件入账。

    返回给助手的结果含透明告知与敏感提示——调用方（工具）直接把它给作家看。
    """
    if not updates:
        return {"ok": False, "notice": "没有要记的内容。"}
    row = await get_or_create_profile(db, user_id)
    sections = await load_sections(db, user_id)
    sensitive_hit = [k for k in updates if k in SENSITIVE_KEYS]
    for key, value in updates.items():
        section = key if key in _PROFILE_SECTIONS else "freeform"
        existing = sections.get(section)
        if isinstance(existing, dict) and isinstance(value, dict):
            existing.update({k: v for k, v in value.items()})
            sections[section] = existing
        elif isinstance(existing, list) and isinstance(value, list):
            merged = list(existing)
            for item in value:
                if item not in merged:
                    merged.append(item)
            sections[section] = merged
        else:
            sections[section] = value
    row.sections_json = json.dumps(sections, ensure_ascii=False)
    row.updated_at = _now()
    await record_event(
        db, user_id=user_id, novel_id=novel_id, kind=kind, payload=updates
    )
    notice = "已记进画像：" + "、".join(f"{k}" for k in updates)
    if sensitive_hit:
        notice += SENSITIVE_NOTICE
    return {"ok": True, "notice": notice, "sensitive": bool(sensitive_hit)}


async def clear_profile(db: AsyncSession, user_id: str) -> None:
    """一键清空（可清空是画像四条件之一）。"""
    row = await get_or_create_profile(db, user_id)
    row.sections_json = "{}"
    row.updated_at = _now()
    await db.commit()


async def set_paused(db: AsyncSession, user_id: str, paused: bool) -> None:
    """「暂停画像学习」开关（即时生效；已有内容保留）。"""
    row = await get_or_create_profile(db, user_id)
    row.paused = paused
    row.updated_at = _now()
    await db.commit()


async def maybe_summarize(
    db: AsyncSession,
    *,
    user_id: str,
    novel_id: str,
    complete_fn: Any,
) -> dict[str, Any]:
    """定期总结（autotitle 模式：非阻塞调用方自己包 create_task；失败静默；去重按
    未总结事件数阈值）。把未总结事件交给 complete_fn 出增量摘要，合并进 freeform。

    complete_fn(system, user_text) -> str 由调用方注入（AIClient.chat 适配）。
    返回给调用方的 dict 只做日志/埋点用，不冒泡成会话错误。
    """
    row = await get_or_create_profile(db, user_id)
    if row.paused:
        return {"skipped": "paused"}
    pending = (
        await db.scalars(
            select(func.count())
            .select_from(WriterProfileEvent)
            .where(
                WriterProfileEvent.user_id == user_id,
                WriterProfileEvent.kind.not_in(("summary",)),
            )
        )
    ).first()
    pending = int(pending or 0)
    if pending < SUMMARY_EVERY_EVENTS:
        return {"skipped": "below_threshold", "pending": pending}
    events = (
        await db.scalars(
            select(WriterProfileEvent)
            .where(
                WriterProfileEvent.user_id == user_id,
                WriterProfileEvent.kind.not_in(("summary",)),
            )
            .order_by(WriterProfileEvent.created_at)
            .limit(60)
        )
    ).all()
    digest = "\n".join(
        f"- [{e.kind}] {e.payload_json[:180]}" for e in events
    )
    sections = await load_sections(db, user_id)
    system = (
        "你在维护一位网文作家的画像（让 AI 搭档越用越懂作家）。"
        "根据下面的行为记录，输出要合并进画像的增量要点 JSON："
        '{"naming": str|dict, "pet_peeves": [str], "pacing": str, "style": str, '
        '"freeform": str}。只输出 JSON。没有把握的分区输出空串/空表。'
    )
    user_text = (
        f"当前画像：{json.dumps(sections, ensure_ascii=False)}\n\n"
        f"近期行为记录：\n{digest}"
    )
    try:
        raw = await complete_fn(system, user_text)
        parsed = json.loads(raw) if raw else None
        if not isinstance(parsed, dict):
            raise TypeError("summary not a dict")
    except Exception as e:  # noqa: BLE001——总结失败静默（不阻塞对话、不冒泡）
        logger.info("profile summarize failed (silent): %s", e)
        return {"error": str(e)}
    result = await update_sections(
        db, user_id=user_id, novel_id=novel_id, updates=parsed, kind="summary"
    )
    # 已总结事件打标（kind→summary 不再回灌；事件行保留审计）
    for e in events:
        try:
            payload = json.loads(e.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        payload["summarized"] = True
        e.kind = "summary"
        e.payload_json = json.dumps(payload, ensure_ascii=False)
    await db.commit()
    await record_event(
        db,
        user_id=user_id,
        novel_id=novel_id,
        kind="summary",
        payload={"covered": pending, "result": result.get("ok", False)},
    )
    return {"ok": True, "covered": pending}
