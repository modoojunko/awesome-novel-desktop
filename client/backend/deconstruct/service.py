"""拆书任务服务（c-deconstruct-book 1.x）——任务 CRUD、队列位次、模型解析。

调度契约（design.md D1）：
- 独立于 job_runner 全局单飞槽（备份/成稿下载共用该槽，31 分钟拆解不得锁死它们）；
- FIFO：queue_seq = MAX+1，取任务按 (queue_seq, created_at) 兜底排序；
- cancel 载体 = jobs 表 status 列（worker 每段边界重读），不用内存 Event；
- 源文件落 DATA_ROOT/deconstruct-staging/{task_id}/source.txt（上传即落盘）。
"""

from __future__ import annotations

import json
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import DATA_ROOT
from models.deconstruct import DIMENSION_KEYS, DIMENSIONS, DeconstructJob

STAGING_ROOT = os.path.join(DATA_ROOT, "deconstruct-staging")
MAX_SOURCE_BYTES = 50 * 1024 * 1024


def staging_dir(task_id: str) -> str:
    return os.path.join(STAGING_ROOT, task_id)


def source_path_of(task_id: str) -> str:
    return os.path.join(staging_dir(task_id), "source.txt")


def default_selected_dims() -> list[str]:
    return list(DIMENSION_KEYS)


def normalize_dims(raw: object) -> list[str]:
    """勾选集归一：交集保全序、去重；空/非法 → 全选（下限 1 由前端把守、此处兜底全选）。"""
    if not isinstance(raw, list):
        return default_selected_dims()
    picked = [k for k in DIMENSION_KEYS if k in raw]
    return picked or default_selected_dims()


async def next_queue_seq(db: AsyncSession) -> int:
    seq = await db.scalar(select(func.max(DeconstructJob.queue_seq)))
    return (seq or 0) + 1


async def create_task(
    db: AsyncSession,
    user_id: str,
    *,
    book_name: str,
    source_name: str,
    source_size: int,
    encoding: str,
    parse: dict,
    api_config_id: str,
    ai_model: str,
    selected_dims: list[str],
) -> DeconstructJob:
    task_id = str(uuid.uuid4())
    os.makedirs(staging_dir(task_id), exist_ok=True)
    task = DeconstructJob(
        id=task_id,
        user_id=user_id,
        status="queued",
        queue_seq=await next_queue_seq(db),
        source_name=source_name[:255],
        source_size=source_size,
        source_path=source_path_of(task_id),
        encoding=encoding[:20],
        book_name=(book_name or "未命名")[:255],
        total_chars=parse.get("total_chars", 0),
        chapter_count=len(parse.get("chapters", [])),
        volume_count=len(parse.get("volumes", [])),
        parse_warnings_json=json.dumps(parse.get("warnings", []), ensure_ascii=False),
        api_config_id=api_config_id,
        ai_model=ai_model[:120],
        selected_dims_json=json.dumps(selected_dims, ensure_ascii=False),
        dims_json=json.dumps(
            {
                "prescan": {"state": "queued", "chapters_done": 0},
                "dims": {
                    k: {"state": "queued", "seg_done": 0, "seg_total": 0, "error": ""}
                    for k in selected_dims
                },
            },
            ensure_ascii=False,
        ),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: str, user_id: str) -> DeconstructJob | None:
    task = await db.get(DeconstructJob, task_id)
    if task is None or task.user_id != user_id:
        return None
    return task


async def list_tasks(db: AsyncSession, user_id: str) -> list[dict]:
    rows = (
        await db.scalars(
            select(DeconstructJob)
            .where(DeconstructJob.user_id == user_id)
            .order_by(DeconstructJob.queue_seq.desc(), DeconstructJob.created_at.desc())
        )
    ).all()
    running_seq = next((r.queue_seq for r in rows if r.status == "running"), None)
    out = []
    for r in rows:
        ahead = 0
        if r.status == "queued" and running_seq is not None:
            ahead = max(0, r.queue_seq - running_seq - 1)
        out.append(
            {
                "id": r.id,
                "status": r.status,
                "book_name": r.book_name,
                "total_chars": r.total_chars,
                "chapter_count": r.chapter_count,
                "volume_count": r.volume_count,
                "ai_model": r.ai_model,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "queued_ahead": ahead,
                "product_count": len(json.loads(r.products_json or "{}")),
                "error": _first_error(r),
            }
        )
    return out


def _first_error(task: DeconstructJob) -> str:
    try:
        err = json.loads(task.error_json or "{}")
    except ValueError:
        return ""
    return str(err.get("message", ""))[:200]


def _dims_state(task: DeconstructJob) -> dict:
    try:
        return json.loads(task.dims_json or "{}").get("dims", {})
    except ValueError:
        return {}


def task_view(task: DeconstructJob) -> dict:
    """详情视图：全量（含 dims/products 元信息，不含产物正文）。"""
    product_meta = [
        {"filename": p["file"], "size": len(p.get("md", "")), "dim": dim}
        for dim, p in products_raw(task).items()
        if isinstance(p, dict)
    ]
    selected = []
    try:
        selected = json.loads(task.selected_dims_json or "[]")
    except ValueError:
        pass
    return {
        "id": task.id,
        "status": task.status,
        "book_name": task.book_name,
        "encoding": task.encoding,
        "source_name": task.source_name,
        "total_chars": task.total_chars,
        "chapter_count": task.chapter_count,
        "volume_count": task.volume_count,
        "parse_warnings": json.loads(task.parse_warnings_json or "[]"),
        "ai_model": task.ai_model,
        "api_config_id": task.api_config_id,
        "selected_dims": selected,
        "dims": _dims_state(task),
        "products": product_meta,
        "error": _first_error(task),
        "book_id": task.book_id,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


def products_raw(task: DeconstructJob) -> dict:
    """{dim: {file, data, md}} 原始结构（apply 建书消费 data）。"""
    try:
        return json.loads(task.products_json or "{}")
    except ValueError:
        return {}


def products_of(task: DeconstructJob) -> dict[str, str]:
    """{filename: md} 扁平视图（导出/下载用）。"""
    out: dict[str, str] = {}
    for dim, obj in products_raw(task).items():
        if isinstance(obj, dict) and obj.get("file"):
            out[obj["file"]] = obj.get("md", "")
        elif isinstance(obj, str):  # 兼容旧形状
            out[dim] = obj
    return out


def dim_names() -> dict[str, str]:
    return {k: name for k, name, _ in DIMENSIONS}


# ── 模型客户端解析（自备 key；口径与 get_ai_client_for_novel 按次覆盖对同源）────


async def resolve_client(user_id: str, api_config_id: str, model: str):
    """按 (api_config_id, model) 构造 AIClient；谓词与按次覆盖对同源（可读 ValueError）。"""
    from ai_client import _client_from_config  # noqa: PLC2701 — 域内复用同一构造器
    from ai_state import config_key_usable, parse_models
    from api_configs.crypto import decrypt_api_key
    from db import async_session
    from models.api_config import ApiConfig

    if not api_config_id or not model:
        raise ValueError("请先选择拆解模型")
    async with async_session() as session:
        cfg = await session.get(ApiConfig, api_config_id)
        if cfg is None or getattr(cfg, "status", "active") == "deleted":
            raise ValueError("所选模型配置不存在，请重新选择模型")
        if getattr(cfg, "user_id", None) != user_id:
            raise ValueError("所选模型配置不存在，请重新选择模型")
        if getattr(cfg, "vendor", None) == "zhuque":
            raise ValueError("所选配置不能用于拆解，请重新选择模型")
        if not config_key_usable(cfg):
            raise ValueError("所选配置没有可用 Key（或最近连接失败），去「模型配置」检查或重测后重试")
        if model not in parse_models(cfg.models):
            raise ValueError("所选模型不在该配置的模型清单里，请重新选择模型")
        plain_key = decrypt_api_key(cfg.api_key)
        if not plain_key:
            raise ValueError("所选配置 Key 无法解密，去「模型配置」重存后重试")
        return _client_from_config(cfg, model, plain_key), model


async def probe_model(user_id: str, api_config_id: str, model: str) -> dict:
    """创建前轻量探针：复用既有连接测试（支持 model 覆盖），不新增端点。"""
    from api_configs.router import _test_api_config  # noqa: PLC2701 — 既有探针单源
    from db import async_session

    async with async_session() as session:
        return await _test_api_config(
            session, user_id, api_config_id, preferred_model=model or None
        )
