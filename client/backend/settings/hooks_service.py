"""伏笔服务层 — 全部跨表事务收在这里，router 只做参数与响应整形。

并发/事务纪律（沿 character_service 先例）：
- seq 取号 = novels.hook_seq_high 计数器同事务读改写（单调不复用）。
- 删除写 hook_ops 前像；撤销按前像同事务重放（原 id 原样恢复）。
- 单槽撤销：新删除诞生时本书更早 op 一并过期（token 有效期到「下次操作」）。
- 章节引用只认同书章 id：跨书/不存在的章引用一律拒绝（400）。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.hook import HookOp, NovelHook
from models.project import Novel
from settings.hooks_model import (
    DESCRIPTION_MAX,
    HOOK_STATUSES,
    HOOK_TYPE_KEYS,
    PAYOFF_NOTE_MAX,
    normalize_priority,
)

UNDO_TTL_SECONDS = 600

# PATCH/POST 白名单：mentioned_chapter_id 故意不在内——它是归档联动专属列
# （write-archive-meta-sync），前端不得写；状态语义 status 只由状态切换写。
_PATCHABLE = {
    "description",
    "type",
    "priority",
    "status",
    "introduced_chapter_id",
    "planned_chapter_id",
    "resolved_chapter_id",
    "payoff_note",
}
_CHAPTER_REFS = (
    "introduced_chapter_id",
    "planned_chapter_id",
    "resolved_chapter_id",
)


class Conflict(Exception):
    """语义冲突（409）。detail 直接给前端。"""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.detail = {"code": code, "message": message, **extra}


class Unprocessable(Exception):
    """语义拒绝（400）。"""

    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.detail = {"code": code, "message": message, **extra}


def hook_to_dict(h: NovelHook) -> dict:
    """显式白名单整形——禁止 model_dump() 直出。"""
    return {
        "id": h.id,
        "novel_id": h.novel_id,
        "seq": h.seq,
        "code": f"#H-{h.seq:04d}",
        "description": h.description,
        "type": h.type,
        "priority": h.priority,
        "status": h.status,
        "introduced_chapter_id": h.introduced_chapter_id,
        "planned_chapter_id": h.planned_chapter_id,
        "resolved_chapter_id": h.resolved_chapter_id,
        "mentioned_chapter_id": h.mentioned_chapter_id,
        "payoff_note": h.payoff_note,
        "created_at": h.created_at.isoformat() if h.created_at else None,
        "updated_at": h.updated_at.isoformat() if h.updated_at else None,
    }


async def list_hooks(session: AsyncSession, novel_id: str) -> dict:
    """全量列表（台账三分组由前端按 status 归堆；这里按 seq 序给全）。"""
    rows = (
        await session.scalars(
            select(NovelHook).where(NovelHook.novel_id == novel_id).order_by(NovelHook.seq)
        )
    ).all()
    return {"count": len(rows), "items": [hook_to_dict(h) for h in rows]}


async def _load_novel(session: AsyncSession, novel_id: str) -> Novel:
    novel = await session.get(Novel, novel_id)
    if novel is None:
        raise Unprocessable("not_found", "书不存在")
    return novel


async def _load_hook(session: AsyncSession, novel_id: str, hook_id: str) -> NovelHook:
    h = await session.get(NovelHook, hook_id)
    if h is None or h.novel_id != novel_id:
        raise Unprocessable("not_found", "伏笔不存在或已删除")
    return h


async def _validate_chapter_ref(
    session: AsyncSession, novel_id: str, column: str, value
) -> str | None:
    """章引用只认同书章 id；跨书/不存在/非法类型一律拒绝。None/"" 显式清空。"""
    from models.chapter import Chapter

    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise Unprocessable("invalid_chapter_ref", f"「{column}」需要是章节 id")
    row = await session.get(Chapter, value)
    if row is None or row.project_id != novel_id:
        raise Unprocessable(
            "invalid_chapter_ref", "章节不存在或不属于本书", chapter_id=value
        )
    return value


def _validate_text(column: str, value, max_len: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise Unprocessable("invalid_text", f"「{column}」需要是字符串")
    text = value.strip()
    if len(text) > max_len:
        raise Unprocessable("too_long", f"「{column}」最多 {max_len} 字")
    return text


async def create_hook(session: AsyncSession, novel_id: str, body: dict) -> NovelHook:
    """新增：seq 同事务取号。description 允许空串（台账先落行后编辑；
    门禁/readiness 只认 trim 非空行，空行不进判定）。"""
    novel = await _load_novel(session, novel_id)
    fields = await _apply_fields(session, novel_id, {}, body, creating=True)
    novel.hook_seq_high += 1
    h = NovelHook(novel_id=novel_id, seq=novel.hook_seq_high, **fields)
    session.add(h)
    await session.commit()
    await session.refresh(h)
    return h


async def _apply_fields(
    session: AsyncSession, novel_id: str, current: dict, body: dict, *, creating: bool
) -> dict:
    """白名单逐字段校验，产出可直接进 ORM 的字段 dict（只含 body 提供的键）。"""
    if not isinstance(body, dict):
        raise Unprocessable("invalid_body", "请求体需要是对象")
    fields: dict[str, Any] = {}
    if "description" in body or creating:
        fields["description"] = _validate_text(
            "description", body.get("description"), DESCRIPTION_MAX
        )
    if "payoff_note" in body or creating:
        fields["payoff_note"] = _validate_text(
            "payoff_note", body.get("payoff_note"), PAYOFF_NOTE_MAX
        )
    if "type" in body:
        value = body.get("type")
        if value not in HOOK_TYPE_KEYS:
            raise Unprocessable(
                "invalid_type", f"伏笔类型只能是 {'/'.join(HOOK_TYPE_KEYS)}"
            )
        fields["type"] = value
    if "priority" in body:
        try:
            fields["priority"] = normalize_priority(body.get("priority"))
        except ValueError as e:
            raise Unprocessable("invalid_priority", "优先级只能是 高/中/低") from e
    if "status" in body:
        value = body.get("status")
        if value not in HOOK_STATUSES:
            raise Unprocessable(
                "invalid_status", f"状态只能是 {'/'.join(HOOK_STATUSES)}"
            )
        fields["status"] = value
    for column in _CHAPTER_REFS:
        if column in body:
            fields[column] = await _validate_chapter_ref(
                session, novel_id, column, body.get(column)
            )
    # mentioned_chapter_id 不在白名单：归档联动专属列，任何手写请求都拒绝
    unknown = set(body) - _PATCHABLE
    if unknown:
        raise Unprocessable(
            "unknown_field", f"没有「{min(unknown)}」这一格"
        )
    _ = current  # 预留：后续按旧值做条件更新的挂点
    return fields


async def patch_hook(
    session: AsyncSession, novel_id: str, hook_id: str, body: dict
) -> NovelHook:
    """部分字段更新（白名单见 _PATCHABLE）。

    resolved→active 回切保留收束记录：PATCH 只动提供的键，
    resolved_chapter_id / payoff_note 不随 status 变化被清。
    """
    h = await _load_hook(session, novel_id, hook_id)
    fields = await _apply_fields(session, novel_id, hook_to_dict(h), body, creating=False)
    for key, value in fields.items():
        setattr(h, key, value)
    await session.commit()
    await session.refresh(h)
    return h


async def delete_hook(session: AsyncSession, novel_id: str, hook_id: str) -> dict:
    """删除即时落库并返回撤销凭证（ops token）。新 op 诞生 → 本书旧 op 全部过期。"""
    h = await _load_hook(session, novel_id, hook_id)
    before = hook_to_dict(h)
    token = uuid.uuid4().hex
    now = datetime.now(UTC).replace(tzinfo=None)
    await session.delete(h)
    # 单槽撤销：更早的 op 一并过期（token 有效期到「下次操作」）
    await session.execute(
        update(HookOp)
        .where(HookOp.novel_id == novel_id, HookOp.undone_at.is_(None))
        .values(expires_at=now)
    )
    session.add(HookOp(
        novel_id=novel_id, kind="delete", before=json.dumps(before, ensure_ascii=False),
        hook_id=hook_id, undo_token=token, expires_at=now + timedelta(seconds=UNDO_TTL_SECONDS),
    ))
    await session.commit()
    return {
        "receipt": f"已删除「{before['description'] or before['code']}」",
        "undo": {"token": token, "hook_id": hook_id},
    }


async def restore_hook(
    session: AsyncSession, novel_id: str, hook_id: str, token: str | None = None
) -> NovelHook:
    """按原 id 原样恢复（id 与 seq 不变）。幂等：行已在则按前像覆盖回写。"""
    op = (
        await session.scalars(
            select(HookOp)
            .where(
                HookOp.novel_id == novel_id,
                HookOp.hook_id == hook_id,
                HookOp.kind == "delete",
            )
            .order_by(HookOp.created_at.desc())
        )
    ).first()
    if op is None:
        raise Unprocessable("not_found", "没有这次删除的撤销记录")
    if token is not None and token != op.undo_token:
        raise Conflict("token_mismatch", "撤销凭证不匹配，请刷新后重试")
    now = datetime.now(UTC).replace(tzinfo=None)
    if op.expires_at is not None and op.expires_at < now:
        raise Conflict("undo_expired", "撤销窗口已过，无法恢复")
    before = json.loads(op.before or "{}")
    snap_seq = int(before.get("seq") or 0)
    values = {
        "seq": snap_seq,
        "description": before.get("description", ""),
        "type": before.get("type", "mystery"),
        "priority": before.get("priority", 2),
        "status": before.get("status", "active"),
        "introduced_chapter_id": before.get("introduced_chapter_id"),
        "planned_chapter_id": before.get("planned_chapter_id"),
        "resolved_chapter_id": before.get("resolved_chapter_id"),
        "mentioned_chapter_id": before.get("mentioned_chapter_id"),
        "payoff_note": before.get("payoff_note", ""),
    }
    existing = await session.get(NovelHook, hook_id)
    if existing is None:
        session.add(NovelHook(id=hook_id, novel_id=novel_id, **values))
        await session.flush()
        # 计数器不能倒退（防复用；恢复行的 seq 必 ≤ high，这里只兜底）
        novel = await session.get(Novel, novel_id)
        if novel is not None and snap_seq > novel.hook_seq_high:
            novel.hook_seq_high = snap_seq
    else:
        # 幂等重放：行已存在（重复 restore）→ 按前像覆盖回写
        for key, value in values.items():
            setattr(existing, key, value)
    op.undone_at = op.undone_at or now
    await session.commit()
    return await session.get(NovelHook, hook_id)


async def mark_hooks_mentioned(session: AsyncSession, novel_id: str, chapter_id: str) -> None:
    """归档联动（write-archive-meta-sync）：本章引入的活跃伏笔 → 单条 UPDATE
    mentioned_in_chapter_id。status 不动；同值重复写天然幂等。"""
    await session.execute(
        update(NovelHook)
        .where(
            NovelHook.novel_id == novel_id,
            NovelHook.status == "active",
            NovelHook.introduced_chapter_id == chapter_id,
        )
        .values(mentioned_chapter_id=chapter_id)
    )
