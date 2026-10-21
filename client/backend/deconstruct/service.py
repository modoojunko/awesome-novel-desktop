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
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import DATA_ROOT
from deconstruct.pipeline import (  # _now＝UTC naive（时间口径单源）
    CONCURRENCY,
    NON_CALL_STAGES,
    _now,
)
from models.deconstruct import (
    DIMENSION_KEYS,
    DIMENSIONS,
    DeconstructJob,
    DeconstructUnit,
)

STAGING_ROOT = os.path.join(DATA_ROOT, "deconstruct-staging")
MAX_SOURCE_BYTES = 50 * 1024 * 1024
# 思考档位（c-deconstruct-resilience D10）：任务级，不随 ApiConfig 走
THINKING_MODES = ("off", "low", "inherit")


def normalize_thinking_mode(raw: object) -> str:
    """创建表单的思考档位归一：白名单外（含空/非法）一律默认关。"""
    return raw if raw in THINKING_MODES else "off"


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


def graph_caps() -> bool:
    """能力戳（评审 P1：判点前移到创建时）：card 模板契约是否含 presence。

    老包（无 presence）出不了图谱——创建照常（md 仍值钱），导出端只认行内戳回落文档版。
    """
    try:
        from prompts import load_layers

        system, _user = load_layers("deconstruct_card")
        return "presence" in (system or "")
    except Exception:  # noqa: BLE001 — 缺包/读失败一律按无能力（创建不拦）
        return False


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
    graph_caps_flag: bool = True,
    thinking_mode: str = "off",
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
        thinking_mode=normalize_thinking_mode(thinking_mode),
        dims_json=json.dumps(
            {
                "caps_graph": graph_caps_flag,  # 能力戳：判点在创建时（导出只认行内戳）
                "cards": {"state": "queued", "done": 0, "entries": {}},
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
    # 排队位次按仍处 queued 的行计数（取消/删除留下的序号空洞不计入，评审 P3）
    queued_seqs = [r.queue_seq for r in rows if r.status == "queued"]
    out = []
    for r in rows:
        ahead = 0
        if r.status == "queued":
            ahead = sum(1 for q in queued_seqs if q < r.queue_seq)
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


def _error_kind(task: DeconstructJob) -> str:
    """失败归因（c-deconstruct-resilience）：provider_unavailable/stalled/auth/config/
    content_filter/timeout/…——失败面板按它给可执行出口。"""
    try:
        err = json.loads(task.error_json or "{}")
    except ValueError:
        return ""
    return str(err.get("kind", ""))


def _dims_state(task: DeconstructJob) -> dict:
    try:
        raw = json.loads(task.dims_json or "{}").get("dims", {})
    except ValueError:
        return {}
    out: dict = {}
    for k, st in raw.items():
        if isinstance(st, dict) and st.get("state") == "running":
            eta = _eta_seconds(st.get("started_at"), int(st.get("seg_done") or 0), int(st.get("seg_total") or 0))
            st = {**st, "eta_seconds": eta}
        out[k] = st
    return out


def _graph_view(task: DeconstructJob) -> dict:
    """图谱视图（可选字段）：ready/absent/error＋警告计数＋完成度。"""
    try:
        raw = json.loads(task.dims_json or "{}")
    except ValueError:
        raw = {}
    graph = raw.get("graph")
    if isinstance(graph, dict):
        meta = graph.get("meta") if isinstance(graph.get("meta"), dict) else {}
        warnings = meta.get("warnings") if isinstance(meta.get("warnings"), list) else []
        n_warn = sum(int(w.get("count") or 1) for w in warnings if isinstance(w, dict))
        state = "ready"
    elif raw.get("graph_error"):
        n_warn = 0
        state = "error"
    else:
        n_warn = 0
        state = "absent"
    return {
        "state": state,
        "available": state == "ready",
        "warnings": n_warn,
        "caps": bool(raw.get("caps_graph", True)),
    }


def _cards_state(task: DeconstructJob) -> dict:
    try:
        return json.loads(task.dims_json or "{}").get("cards", {})
    except ValueError:
        return {}


def _activity(task: DeconstructJob) -> dict | None:
    """当前动作账（pipeline 每次模型调用前写）：label＋距今秒数。

    at 是 pipeline._now() 的 UTC naive 串——这里必须同口径取 UTC，否则 UTC+8
    下「已进行 2 分钟」显示成 8 小时（c-deconstruct-resilience 时间口径修复）。
    """
    try:
        raw = json.loads(task.dims_json or "{}")
    except ValueError:
        return None
    a = raw.get("activity")
    if not isinstance(a, dict) or not a.get("label"):
        return None
    age: int | None = None
    try:
        age = int((_now() - datetime.fromisoformat(str(a["at"]))).total_seconds())
    except (ValueError, TypeError):
        pass
    return {"label": str(a["label"]), "age_seconds": max(0, age) if age is not None else None}


def _eta_seconds(started_at, done, total) -> int | None:
    """阶段 ETA：按已完成的实际速率外推剩余，并发度摊薄；无基准/已完成则 None。

    时间口径与 _activity 同源（UTC naive 比较，pipeline._now()）。
    """
    if not started_at or done <= 0 or total <= done:
        return None
    try:
        elapsed = max(1.0, (_now() - datetime.fromisoformat(str(started_at))).total_seconds())
    except ValueError:
        return None
    conc = max(1, CONCURRENCY)
    return int(elapsed / done * (total - done) / conc)


def _graph_phase(task: DeconstructJob) -> dict | None:
    """阶段三进度账（pipeline 写、终态 pop）：presence n/m ／ place_merge ／ assemble。"""
    try:
        raw = json.loads(task.dims_json or "{}")
    except ValueError:
        return None
    p = raw.get("graph_phase")
    if not isinstance(p, dict) or not p.get("step"):
        return None
    out: dict = {"step": str(p["step"])}
    if "done" in p or "total" in p:
        out["done"] = int(p.get("done") or 0)
        out["total"] = int(p.get("total") or 0)
    return out


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
        "cards": {
            "state": str(_cards_state(task).get("state", "queued")),
            "done": int(_cards_state(task).get("done", 0) or 0),
            "total": task.chapter_count,
            "eta_seconds": _eta_seconds(_cards_state(task).get("started_at"),
                                        int(_cards_state(task).get("done", 0) or 0),
                                        task.chapter_count),
        },
        "activity": _activity(task),
        "graph": _graph_view(task),
        "graph_phase": _graph_phase(task),
        "dims": _dims_state(task),
        "products": product_meta,
        "error": _first_error(task),
        "error_kind": _error_kind(task),
        "warnings": _warnings_view(task),
        "model_history": _model_history(task),
        "book_id": task.book_id,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


def _warnings_view(task: DeconstructJob) -> list[str]:
    """任务级告警账（单元隔离的章级/批级失败）：详情页可见，不再「全绿但缺章」。"""
    try:
        raw = json.loads(task.dims_json or "{}")
    except ValueError:
        return []
    w = raw.get("warnings")
    return [str(x) for x in w][:50] if isinstance(w, list) else []


def _model_history(task: DeconstructJob) -> list[dict]:
    """换模型续拆历史：[{api_config_id, ai_model, at}]，append-only。"""
    try:
        raw = json.loads(task.model_history_json or "[]")
    except ValueError:
        return []
    return raw if isinstance(raw, list) else []


async def task_stats(task_id: str) -> dict:
    """调用账（c-deconstruct-resilience）：按阶段聚合 deconstruct_units。

    calls=单元行数（done+failed+skipped）、failures=failed 行数、
    attempts=尝试总和（重试可见）、tokens/duration 累计。不含原文与密钥。
    非模型调用行（NON_CALL_STAGES：轮间检查点/合批逐章产物）不进账——
    否则一批 N 章会虚增 N 次调用且拉低平均耗时。
    """
    from db import async_session

    async with async_session() as session:
        rows = (
            await session.execute(
                select(DeconstructUnit).where(DeconstructUnit.task_id == task_id)
            )
        ).scalars().all()
    out: dict[str, dict] = {}
    for r in rows:
        if r.stage in NON_CALL_STAGES:
            continue  # 非调用行：不进调用账，防幽灵 calls
        bucket = out.setdefault(r.stage, {
            "calls": 0, "failures": 0, "attempts": 0,
            "duration_ms": 0, "tokens_in": 0, "tokens_out": 0,
            "by_kind": {},
        })
        bucket["calls"] += 1
        bucket["attempts"] += int(r.attempts or 0)
        bucket["duration_ms"] += int(r.duration_ms or 0)
        if r.status == "done":
            bucket["tokens_in"] += int(r.tokens_in or 0)
            bucket["tokens_out"] += int(r.tokens_out or 0)
        elif r.status == "failed":
            bucket["failures"] += 1
            k = r.error_kind or "unknown"
            bucket["by_kind"][k] = bucket["by_kind"].get(k, 0) + 1
    return out


_MONITOR_WINDOW_S = 300
_MONITOR_RECENT = 8


def _unit_label(stage: str, dim: str, unit_key: str) -> str:
    """最近流水的调度对象（c-deconstruct-monitor）：具体到章号/维度，不再只报阶段。"""
    if stage == "card":
        return f"第{unit_key}章"
    if stage == "presence":
        return f"第{unit_key}章·在场"
    if stage == "card_batch":
        # 合批行的单元键＝输入指纹:章号区间（旧账行无区间后缀，按原样只报阶段）
        span = unit_key.split(":", 1)[1] if ":" in unit_key else ""
        first, _, last = span.partition("-")
        if not span:
            return "拆卡合批"
        return f"拆卡合批·第{first}章" if first == last or not last else f"拆卡合批·第{first}-{last}章"
    if stage == "place":
        return "地点归并"
    name = dim_names().get(dim, dim)
    if stage == "l1":
        return f"{name}·归并" if name else "归并"
    if stage == "reduce":
        return f"{name}·收敛" if name else "收敛"
    return stage or "调用"


async def monitor_view(task: DeconstructJob) -> dict | None:
    """运行监控账（c-deconstruct-monitor）：在途＋批次进度＋近 5 分钟速度＋最近调用流水。

    单元账派发即写 running 行（调度即现），完成时覆盖为终态；只读计数列（MUST NOT 读
    output_json——reduce partials 大载荷不得进 1.5s 轮询）；非模型调用行（NON_CALL_STAGES：
    reduce_state 检查点、card_product 合批逐章产物）与 task_stats 同口径排除——合批的
    耗时/token 在 card_batch 行上，产物行若入流水会成片 0s/0.0k 并挤掉真实调用。
    queued/running 返回账块，终态返回 None。
    """
    if task.status not in ("running", "queued"):
        return None
    from db import async_session

    async with async_session() as session:
        rows = (
            await session.execute(
                select(
                    DeconstructUnit.stage, DeconstructUnit.dim, DeconstructUnit.unit_key,
                    DeconstructUnit.status,
                    DeconstructUnit.error_kind, DeconstructUnit.duration_ms,
                    DeconstructUnit.tokens_in, DeconstructUnit.tokens_out,
                    DeconstructUnit.updated_at,
                ).where(DeconstructUnit.task_id == task.id)
            )
        ).all()
    calls = [r for r in rows if r.stage not in NON_CALL_STAGES]
    now = _now()
    win = [
        r for r in calls
        if r.updated_at is not None
        and 0 <= (now - r.updated_at).total_seconds() <= _MONITOR_WINDOW_S
    ]
    done_win = [r for r in win if r.status == "done"]
    fail_win = [r for r in win if r.status == "failed"]
    l1 = [r for r in rows if r.stage == "l1"]
    recent = sorted(
        (r for r in calls if r.updated_at is not None),
        key=lambda r: r.updated_at, reverse=True,
    )[:_MONITOR_RECENT]
    avg_ms: int | None = (
        sum(int(r.duration_ms or 0) for r in done_win) // len(done_win)
    ) if done_win else None
    done_rows = [r for r in calls if r.status == "done"]  # token 记账口径：完成时入账
    tok_in = sum(int(r.tokens_in or 0) for r in done_rows)
    tok_out = sum(int(r.tokens_out or 0) for r in done_rows)
    return {
        "concurrency": CONCURRENCY,
        "in_flight": sum(1 for r in calls if r.status == "running"),
        "batches": {
            "done": sum(1 for r in l1 if r.status in ("done", "skipped")),
            "total": len(l1),
        },
        "tokens": {
            "in": tok_in,
            "out": tok_out,
            "total": tok_in + tok_out,
        },
        "speed": {
            "window_s": _MONITOR_WINDOW_S,
            "done": len(done_win),
            "fail": len(fail_win),
            "avg_ms": avg_ms,
            "out_tokens": sum(int(r.tokens_out or 0) for r in done_win),
            "total": len(calls),
        },
        "recent": [
            {
                "at": r.updated_at.isoformat(),
                "label": _unit_label(r.stage, r.dim, r.unit_key),
                "running": r.status == "running",
                "duration_ms": int(r.duration_ms or 0),
                "tokens_out": int(r.tokens_out or 0),
                "ok": r.status == "done",
                "reason": "" if r.status != "failed" else str(r.error_kind or ""),
            }
            for r in recent
        ],
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


async def resolve_client(user_id: str, api_config_id: str, model: str, thinking: str = "inherit"):
    """按 (api_config_id, model) 构造 AIClient；谓词与按次覆盖对同源（可读 ValueError）。

    thinking：任务级思考档位（c-deconstruct-resilience D10）——off/low 折算成构造
    参数覆盖 ApiConfig（off＝关思考；GLM-5.3 强制端点在请求层自动折算 enabled＋low），
    inherit＝跟随 ApiConfig 配置（旧行为）。"""
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
        # SDK 重试关到 0：拆书重试策略单源 deconstruct/policy（「管线 3 次 × SDK 2 次」
        # 的乘法放大是长时间假死的成因之一，c-deconstruct-resilience D1）
        if thinking == "off":
            thinking_enabled, thinking_effort = False, "low"
        elif thinking == "low":
            thinking_enabled, thinking_effort = True, "low"
        else:
            thinking_enabled = thinking_effort = None  # inherit：跟随 ApiConfig
        return _client_from_config(cfg, model, plain_key, max_retries=0,
                                   thinking_enabled=thinking_enabled,
                                   thinking_effort=thinking_effort), model


async def probe_model(user_id: str, api_config_id: str, model: str) -> dict:
    """创建前轻量探针：复用既有连接测试（支持 model 覆盖），不新增端点。"""
    from api_configs.router import _test_api_config  # noqa: PLC2701 — 既有探针单源
    from db import async_session

    async with async_session() as session:
        return await _test_api_config(
            session, user_id, api_config_id, preferred_model=model or None
        )
