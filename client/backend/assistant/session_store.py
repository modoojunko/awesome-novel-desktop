"""助手会话存储——coding agent 式文件后端（c-agent-session-files）。

载体迁移史：OpenWorker conversations.py（SQLite 索引＋每会话 JSONL）→ 批A 改宿主
两表 → 本版回归纯文件（boss 拍板 2026-11-18：像 coding agent 一样按 id+日期存
安装目录 sessions 目录）。机制语义承自 OpenWorker/批A 双蓝本：

  - 会话 id 白名单（conversations.py:30-34）：id 会出现在文件名/日志路径里，
    客户端可传的 id 必须挡住路径逃逸；
  - append-only＋seq 单调：正常路径只追加；改写（meta 变更/收尾/compact）走
    「整段重写」＝tmp 文件＋os.replace 原子替换（conversations.py:332-342 同款）；
  - 自愈（conversations.py:157-261）：加载时把超墙钟仍悬挂的 streaming 行收尾为
    error，崩前已产出的卡与轨迹原样保留；文件尾部半行（崩溃残迹）读侧跳过；
  - /new 对齐 coding agent：新开会话＝新文件（新 id＋当日日期），旧文件留档。

布局：DATA_ROOT/sessions/<novel_id>/<YYYYMMDD>__<thread>__<session_id>.jsonl
（thread_key 中 ":" 编码为 "-"；首行 meta，其后每行一条消息/事件）。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config import DATA_ROOT

# 会话 id 白名单（openwriter conversations.py:30 同款正则）：id 出现在文件名里，
# 客户端可传的 id 必须挡住路径逃逸。
_SAFE_SESSION_ID = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")
# 书 id 同口径（目录段）
_SAFE_NOVEL_ID = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")


def is_safe_session_id(sid: str) -> bool:
    return bool(isinstance(sid, str) and _SAFE_SESSION_ID.match(sid))


def new_session_id() -> str:
    return uuid.uuid4().hex


def new_message_id() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return default
    return value


# 会话线程键白名单（前端按页面/页签生成；服务端防御性校验）
_SAFE_THREAD_KEY = re.compile(r"\A[A-Za-z0-9:_-]{0,64}\Z")


def sanitize_thread_key(raw: str | None) -> str:
    return raw if isinstance(raw, str) and _SAFE_THREAD_KEY.match(raw) else ""


# ── 文件布局 ────────────────────────────────────────────────────────────────


def _root() -> Path:
    return Path(DATA_ROOT) / "sessions"


def _novel_dir(novel_id: str) -> Path:
    if not _SAFE_NOVEL_ID.match(novel_id or ""):
        raise ValueError(f"bad novel_id: {novel_id!r}")
    return _root() / novel_id


def _thread_enc(thread_key: str) -> str:
    return (thread_key or "").replace(":", "-") or "root"


def _session_path(meta: SessionMeta) -> Path:
    date = (meta.created_at or _now())[:10].replace("-", "")
    return _novel_dir(meta.novel_id) / f"{date}__{_thread_enc(meta.thread_key)}__{meta.id}.jsonl"


@dataclass
class SessionMeta:
    """会话元数据（文件 meta 行的内存形态；grants/compaction 保持 JSON 串——
    router 既有 json.loads(session.grants_json) 调用面零变化）。"""

    id: str
    user_id: str
    novel_id: str
    thread_key: str
    page_cursor: str
    grants_json: str
    compaction_json: str
    created_at: str
    updated_at: str
    path: str = ""


@dataclass
class MsgRow:
    """消息行（文件 msg 行的内存形态；字段与原 assistant_messages 行同形）。"""

    id: str
    session_id: str
    novel_id: str
    seq: int
    role: str
    page: str
    content: str
    payload_json: str
    card_kind: str
    status: str
    run_id: str
    tokens_in: int
    tokens_out: int
    created_at: str
    path: str = ""


def _meta_dict(meta: SessionMeta) -> dict[str, Any]:
    return {
        "type": "meta",
        "id": meta.id,
        "user_id": meta.user_id,
        "novel_id": meta.novel_id,
        "thread_key": meta.thread_key,
        "page_cursor": meta.page_cursor,
        "grants": _load_json(meta.grants_json, {}),
        "compaction": _load_json(meta.compaction_json, {}),
        "created_at": meta.created_at,
        "updated_at": meta.updated_at,
    }


def _msg_dict(m: MsgRow) -> dict[str, Any]:
    return {
        "type": "msg",
        "id": m.id,
        "session_id": m.session_id,
        "novel_id": m.novel_id,
        "seq": m.seq,
        "role": m.role,
        "page": m.page,
        "content": m.content,
        "payload": _load_json(m.payload_json, {}),
        "card_kind": m.card_kind,
        "status": m.status,
        "run_id": m.run_id,
        "tokens_in": m.tokens_in,
        "tokens_out": m.tokens_out,
        "created_at": m.created_at,
    }


def _meta_from(obj: dict[str, Any], path: str) -> SessionMeta:
    return SessionMeta(
        id=str(obj.get("id") or ""),
        user_id=str(obj.get("user_id") or ""),
        novel_id=str(obj.get("novel_id") or ""),
        thread_key=str(obj.get("thread_key") or ""),
        page_cursor=str(obj.get("page_cursor") or ""),
        grants_json=json.dumps(obj.get("grants") or {}, ensure_ascii=False),
        compaction_json=json.dumps(obj.get("compaction") or {}, ensure_ascii=False),
        created_at=str(obj.get("created_at") or ""),
        updated_at=str(obj.get("updated_at") or ""),
        path=path,
    )


def _msg_from(obj: dict[str, Any], path: str) -> MsgRow:
    return MsgRow(
        id=str(obj.get("id") or ""),
        session_id=str(obj.get("session_id") or ""),
        novel_id=str(obj.get("novel_id") or ""),
        seq=int(obj.get("seq") or 0),
        role=str(obj.get("role") or ""),
        page=str(obj.get("page") or ""),
        content=str(obj.get("content") or ""),
        payload_json=json.dumps(obj.get("payload") or {}, ensure_ascii=False),
        card_kind=str(obj.get("card_kind") or ""),
        status=str(obj.get("status") or "done"),
        run_id=str(obj.get("run_id") or ""),
        tokens_in=int(obj.get("tokens_in") or 0),
        tokens_out=int(obj.get("tokens_out") or 0),
        created_at=str(obj.get("created_at") or ""),
        path=path,
    )


def _parse_file(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """读一个会话文件：meta 行＋消息行。崩溃残迹容忍——坏行/半行跳过。"""
    meta_d: dict[str, Any] | None = None
    msgs: list[dict[str, Any]] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, msgs
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # 崩溃尾半行/坏行——跳过不炸
        if not isinstance(obj, dict):
            continue
        t = obj.get("type")
        if t == "meta" and meta_d is None:
            meta_d = obj
        elif t == "msg":
            msgs.append(obj)
    return meta_d, msgs


def _dump_file(path: Path, meta_d: dict[str, Any], msgs: list[dict[str, Any]]) -> None:
    """整段重写：tmp 文件＋os.replace 原子替换（conversations.py:332 同款）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(meta_d, ensure_ascii=False) + "\n")
        for m in msgs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _append_line(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _iter_novel_files(novel_id: str) -> list[Path]:
    d = _novel_dir(novel_id)
    if not d.is_dir():
        return []
    return sorted(d.glob("*.jsonl"))


def _load_meta_obj(path: Path) -> dict[str, Any] | None:
    """只读文件头部找 meta 行（前 2KB 足够——meta 是首行）。"""
    try:
        with path.open("r", encoding="utf-8") as f:
            head = f.readline(2048)
    except (OSError, UnicodeDecodeError):
        return None
    try:
        obj = json.loads(head.strip())
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) and obj.get("type") == "meta" else None


# ── 对外 API（router 调用面；函数名保持，db 参数退役）──────────────────────


async def get_or_create_session(
    *, user_id: str, novel_id: str, thread_key: str = ""
) -> SessionMeta:
    """thread→会话解析：扫书目目录读 meta 行，匹配 user+thread 取最新；无则建新文件。
    「最新」按文件 mtime 决胜（updated_at 字符串同秒会平手——reset 快速连发场景）。"""
    thread_key = sanitize_thread_key(thread_key)
    best: SessionMeta | None = None
    best_mtime = -1.0
    for path in _iter_novel_files(novel_id):
        obj = _load_meta_obj(path)
        if obj is None:
            continue
        meta = _meta_from(obj, str(path))
        if meta.user_id == user_id and meta.thread_key == thread_key:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            if best is None or mtime > best_mtime:
                best = meta
                best_mtime = mtime
    if best is not None:
        return best
    now = _now()
    meta = SessionMeta(
        id=new_session_id(),
        user_id=user_id,
        novel_id=novel_id,
        thread_key=thread_key,
        page_cursor="",
        # 新线程继承本书最近线程的授权档位（grants 书级语义——boss 拍板：切页签不重置）
        grants_json=_latest_grants_in_novel(user_id, novel_id),
        compaction_json="{}",
        created_at=now,
        updated_at=now,
    )
    meta.path = str(_session_path(meta))
    _append_line(Path(meta.path), _meta_dict(meta))
    return meta


def _latest_grants_in_novel(user_id: str, novel_id: str) -> str:
    best = ""
    best_ts = ""
    for path in _iter_novel_files(novel_id):
        obj = _load_meta_obj(path)
        if obj is None or obj.get("user_id") != user_id:
            continue
        ts = str(obj.get("updated_at") or "")
        if ts > best_ts:
            best_ts = ts
            best = json.dumps(obj.get("grants") or {}, ensure_ascii=False)
    return best or "{}"


async def iter_novel_sessions(novel_id: str) -> list[SessionMeta]:
    """本书全部会话（/mode、档位全量改写用）。"""
    out: list[SessionMeta] = []
    for path in _iter_novel_files(novel_id):
        obj = _load_meta_obj(path)
        if obj is not None:
            out.append(_meta_from(obj, str(path)))
    return out


async def load_session(session_id: str, *, user_id: str) -> SessionMeta | None:
    """按 id 取会话（跨书扫描）；归属校验＋id 白名单。"""
    if not is_safe_session_id(session_id):
        return None
    root = _root()
    if not root.is_dir():
        return None
    for path in root.glob("*/*.jsonl"):
        obj = _load_meta_obj(path)
        if obj is None:
            continue
        if obj.get("id") == session_id and obj.get("user_id") == user_id:
            return _meta_from(obj, str(path))
    return None


async def load_messages(session: SessionMeta, *, heal: bool = True) -> list[MsgRow]:
    """按 seq 有序取全量消息；自愈：超墙钟仍悬挂的 streaming 行收尾为 error。"""
    path = Path(session.path or _session_path(session))
    meta_d, msg_objs = _parse_file(path)
    rows = [_msg_from(o, str(path)) for o in msg_objs]
    rows.sort(key=lambda m: m.seq)
    if heal:
        grace = _heal_grace_seconds()
        now = datetime.now()
        changed = False
        for m in rows:
            if m.status != "streaming":
                continue
            try:
                age = now - datetime.strptime(m.created_at, "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                age = None
            if age is not None and age.total_seconds() <= grace:
                continue  # 活跃 run（线程切换后 GET 命中），不误标
            m.status = "error"
            if not m.content:
                m.content = "（这一轮没有完成——上次中途被打断了。）"
            changed = True
        if changed and meta_d is not None:
            _dump_file(path, meta_d, [_msg_dict(m) for m in rows])
    return rows


def _heal_grace_seconds() -> float:
    import os

    try:
        return float(os.environ.get("ASSISTANT_TURN_DEADLINE", "600")) + 30
    except (TypeError, ValueError):
        return 630


def _next_seq(rows: list[MsgRow]) -> int:
    return max((m.seq for m in rows), default=0) + 1


async def append_message(
    session: SessionMeta,
    *,
    role: str,
    content: str = "",
    page: str = "",
    payload: dict | None = None,
    card_kind: str = "",
    status: str = "done",
    run_id: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> MsgRow:
    """追加一条消息（append-only 一行；seq 单调——崩了留下完整轨迹非悬空流）。"""
    path = Path(session.path or _session_path(session))
    _, msg_objs = _parse_file(path)
    seq = _next_seq([_msg_from(o, str(path)) for o in msg_objs])
    m = MsgRow(
        id=new_message_id(),
        session_id=session.id,
        novel_id=session.novel_id,
        seq=seq,
        role=role,
        page=page or "",
        content=content or "",
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        card_kind=card_kind or "",
        status=status or "done",
        run_id=run_id or "",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        created_at=_now(),
        path=str(path),
    )
    _append_line(path, _msg_dict(m))
    return m


async def update_message_status(
    message: MsgRow, *, status: str, content: str | None = None
) -> None:
    """改一行状态（收尾 streaming／采纳回执）：整段重写——append-only 例外。"""
    path = Path(message.path)
    meta_d, msg_objs = _parse_file(path)
    if meta_d is None:
        return
    rows = [_msg_from(o, str(path)) for o in msg_objs]
    for m in rows:
        if m.id != message.id:
            continue
        m.status = status
        if content is not None:
            m.content = content
    _dump_file(path, meta_d, [_msg_dict(m) for m in rows])


async def touch_session(
    session: SessionMeta,
    *,
    page_cursor: str | None = None,
    grants: dict | None = None,
    compaction: dict | None = None,
) -> None:
    """会话级元数据更新（字段独立语义，None＝不动——per-turn save 不碰专属列）。
    meta 行变更＝整段重写（消息行原样保留）。"""
    path = Path(session.path or _session_path(session))
    meta_d, msg_objs = _parse_file(path)
    if meta_d is None:
        return
    meta = _meta_from(meta_d, str(path))
    meta.updated_at = _now()
    if page_cursor is not None:
        meta.page_cursor = page_cursor
    if grants is not None:
        meta.grants_json = json.dumps(grants, ensure_ascii=False)
    if compaction is not None:
        meta.compaction_json = json.dumps(compaction, ensure_ascii=False)
    _dump_file(path, _meta_dict(meta), msg_objs)
    # 同步调用方持有的 meta（page_cursor/grants 后续读取依赖）
    session.updated_at = meta.updated_at
    if page_cursor is not None:
        session.page_cursor = meta.page_cursor
    if grants is not None:
        session.grants_json = meta.grants_json
    if compaction is not None:
        session.compaction_json = meta.compaction_json


async def load_compaction_state(session: SessionMeta):
    """防御性解析 compact 状态（坏 JSON 返回 None）。"""
    from assistant.compact import CompactionState

    raw = _load_json(session.compaction_json, {})
    return CompactionState.from_dict(raw) if raw else None


async def save_compaction_state(session: SessionMeta, state: Any | None) -> None:
    payload = state.as_dict() if state is not None else {}
    await touch_session(session, compaction=payload)


async def reset_session(session: SessionMeta) -> SessionMeta:
    """/new 对齐 coding agent：新开会话＝新文件（新 id＋当日），旧文件留档。
    grants 继承（授权档位跨会话）、page_cursor 继承（还在原页面）、compact 清零。"""
    now = _now()
    fresh = SessionMeta(
        id=new_session_id(),
        user_id=session.user_id,
        novel_id=session.novel_id,
        thread_key=session.thread_key,
        page_cursor=session.page_cursor,
        grants_json=session.grants_json,
        compaction_json="{}",
        created_at=now,
        updated_at=now,
    )
    fresh.path = str(_session_path(fresh))
    _append_line(Path(fresh.path), _meta_dict(fresh))
    return fresh


async def meta_from_path(path: str) -> SessionMeta | None:
    obj = _load_meta_obj(Path(path))
    return _meta_from(obj, path) if obj else None


async def find_message(novel_id: str, message_id: str) -> MsgRow | None:
    """跨线程按消息 id 找行（undo 用：写入可能发生在任意页签线程）。"""
    for path in _iter_novel_files(novel_id):
        _, msg_objs = _parse_file(path)
        for o in msg_objs:
            if str(o.get("id") or "") == message_id:
                return _msg_from(o, str(path))
    return None


async def find_card_message(novel_id: str, card_id: str) -> MsgRow | None:
    """跨线程找产物卡行（卡可能在任意页签线程产生；payload.cardId 全局唯一）。"""
    for path in _iter_novel_files(novel_id):
        _, msg_objs = _parse_file(path)
        target: MsgRow | None = None
        for o in msg_objs:
            m = _msg_from(o, str(path))
            if m.card_kind in ("", "gate"):
                continue
            if str(_load_json(m.payload_json, {}).get("cardId") or "") == card_id:
                target = m  # 同 cardId 取最后一条（与 DB 版语义一致）
        if target is not None:
            return target
    return None


# ── 存量迁移（c-agent-session-files D4）────────────────────────────────────


def _is_lock_error(e: Exception) -> bool:
    """SQLite 锁竞争（CI 多引擎偶发实锤）——迁移重试判定。"""
    msg = str(e).lower()
    return "database is locked" in msg or "database table is locked" in msg


async def _lock_retry(coro_fn, attempts: int = 4):
    """锁竞争退避重试：读幂等＋文件写按存在性幂等——重试安全。"""
    for i in range(attempts):
        try:
            return await coro_fn()
        except Exception as e:  # noqa: BLE001——重试判定在 _is_lock_error
            if i == attempts - 1 or not _is_lock_error(e):
                raise
            await asyncio.sleep(1.5 * (i + 1))


async def migrate_db_sessions() -> dict[str, int]:
    """DB 两表存量 → JSONL 导出（一次性＋幂等＋fail-soft）。

    目标文件已存在即跳过（幂等）；DB 行保留归档（代码不再读写）。调用方
    （main lifespan）兜异常——本函数只管搬。"""
    from sqlalchemy import select

    from db import async_session
    from models.assistant import AssistantMessage, AssistantSession

    out = {"sessions": 0, "messages": 0, "skipped": 0}

    async def _read_all():
        async with async_session() as db:
            sessions = (
                await db.scalars(select(AssistantSession).order_by(AssistantSession.created_at))
            ).all()
            per_msgs = {}
            for row in sessions:
                msgs = (
                    await db.scalars(
                        select(AssistantMessage)
                        .where(AssistantMessage.session_id == row.id)
                        .order_by(AssistantMessage.seq)
                    )
                ).all()
                per_msgs[row.id] = msgs
            return sessions, per_msgs

    sessions, per_msgs = await _lock_retry(_read_all)
    for row in sessions:
        meta = SessionMeta(
            id=row.id,
            user_id=row.user_id,
            novel_id=row.novel_id,
            thread_key=row.thread_key,
            page_cursor=row.page_cursor,
            grants_json=row.grants_json or "{}",
            compaction_json=row.compaction_json or "{}",
            created_at=row.created_at or _now(),
            updated_at=row.updated_at or row.created_at or _now(),
        )
        path = _session_path(meta)
        if path.exists():
            out["skipped"] += 1
            continue
        msgs = per_msgs.get(row.id, [])
        meta_d = _meta_dict(meta)
        lines = [json.dumps(meta_d, ensure_ascii=False)]
        for m in msgs:
            row = MsgRow(
                id=m.id,
                session_id=m.session_id,
                novel_id=m.novel_id,
                seq=m.seq,
                role=m.role,
                page=m.page,
                content=m.content,
                payload_json=m.payload_json or "{}",
                card_kind=m.card_kind,
                status=m.status,
                run_id=m.run_id,
                tokens_in=m.tokens_in,
                tokens_out=m.tokens_out,
                created_at=m.created_at,
            )
            lines.append(json.dumps(_msg_dict(row), ensure_ascii=False))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out["sessions"] += 1
        out["messages"] += len(msgs)
    return out
