"""拆书端点族（c-deconstruct-book 1.3）——上传/清单/详情/取消/续拆/重传/建书/导出/删除。

鉴权与既有 routers 同源（get_current_user，按 user 过滤）；上传走 multipart 流式落盘。
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import ai_feature, require_ai_access
from auth_local.middleware import get_current_user
from db import get_db
from deconstruct import apply, imports, service
from deconstruct.mdrender import evidence_report
from deconstruct.textparse import (
    MAX_SOURCE_BYTES,
    decode_text,
    parse_novel,
    structure_verdict,
)
from models.deconstruct import DeconstructJob

router = APIRouter(prefix="/api/deconstruct", tags=["deconstruct"])


def _user_id(user: dict) -> str:
    return user["id"]


def _require(task, user: dict):
    if task is None:
        raise HTTPException(404, "任务不存在")
    if task.user_id != _user_id(user):
        raise HTTPException(404, "任务不存在")  # 不泄露他人任务存在性


@router.post("/tasks")
@ai_feature("deconstruct")
async def create_task(
    file: UploadFile = File(...),
    book_name: str = Form(""),
    api_config_id: str = Form(...),
    ai_model: str = Form(...),
    selected_dims: str = Form("[]"),
    thinking: str = Form("off"),
    user: dict = Depends(get_current_user),
    _gate: bool = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """创建拆书任务：流式落盘（Content-Length 不可信，块累计双检）→ 探测/解析 → 入队。"""
    import asyncio
    import uuid as _uuid

    os.makedirs(service.STAGING_ROOT, exist_ok=True)
    part_path = os.path.join(service.STAGING_ROOT, f"upload-{_uuid.uuid4().hex}.part")
    size = 0
    too_big = False
    try:
        with open(part_path, "wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_SOURCE_BYTES:
                    too_big = True
                    break
                f.write(chunk)
        if too_big:
            raise HTTPException(400, "文件超过 50MB 上限，请拆分后重试")
        with open(part_path, "rb") as f:
            raw = f.read()
        try:
            text, encoding = decode_text(raw)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        finally:
            del raw

        parse = await asyncio.to_thread(parse_novel, text)
        verdict = structure_verdict(parse)  # 入口结构判定：问题清单前置进 parse_warnings（不拦截，risk 由前端确认闸放行）
        parse["warnings"] = [*verdict["issues"], *(w for w in parse.get("warnings", []) if w not in verdict["issues"])]
        caps = service.graph_caps()  # 能力戳：创建时判卡模板是否含 presence
        try:
            picked = json.loads(selected_dims) if selected_dims else []
        except ValueError as e:
            raise HTTPException(400, "拆解范围参数不合法，请重选维度后重试") from e
        dims = service.normalize_dims(picked)
        task = await service.create_task(
            db,
            _user_id(user),
            book_name=book_name or os.path.splitext(file.filename or "未命名")[0],
            source_name=file.filename or "source.txt",
            source_size=size,
            encoding=encoding,
            parse=parse,
            api_config_id=api_config_id,
            ai_model=ai_model,
            selected_dims=dims,
            graph_caps_flag=caps,
            thinking_mode=service.normalize_thinking_mode(thinking),
        )
        os.replace(part_path, task.source_path)  # 上传即落盘契约：排队不依赖浏览器 File
    finally:
        if os.path.exists(part_path):
            os.remove(part_path)
    return {
        "id": task.id,
        "status": task.status,
        "book_name": task.book_name,
        "encoding": task.encoding,
        "total_chars": task.total_chars,
        "chapter_count": task.chapter_count,
        "volume_count": task.volume_count,
        "parse_warnings": json.loads(task.parse_warnings_json),
        "structure": verdict,
        "selected_dims": dims,
        "graph_caps": caps,
        "thinking": task.thinking_mode,
    }


@router.get("/tasks")
async def list_tasks(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await service.list_tasks(db, _user_id(user))
    running = next((t for t in tasks if t["status"] == "running"), None)
    queued = sum(1 for t in tasks if t["status"] == "queued")
    # 建书中也算活动态（c-deconstruct-import-async）：顶栏心跳要让用户知道后台还在跑；
    # 已建书＝已消费（book_id 非空），建书失败＝需要处理，继续计入「已完成未取结果」。
    importing = sum(1 for t in tasks if t["status"] == "importing")
    done_unpicked = len(
        (
            await db.scalars(
                select(DeconstructJob.id).where(
                    DeconstructJob.user_id == _user_id(user),
                    DeconstructJob.status.in_(("completed", "import_failed")),
                    DeconstructJob.book_id.is_(None),
                    DeconstructJob.exported_at.is_(None),  # 文件夹出口也算「已取」
                )
            )
        ).all()
    )
    return {
        "tasks": tasks,
        "heartbeat": {"running": 1 if running else 0, "queued": queued, "importing": importing},
        "badge": (1 if running else 0) + queued + importing + done_unpicked,
    }


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    stats = await service.task_stats(task_id)  # 调用账（c-deconstruct-resilience）
    monitor = await service.monitor_view(task)  # 运行监控账（c-deconstruct-monitor，终态 None）
    # 幂等键读时校正（c-import-stale-book）：书被删后详情不再显示「已建书」死链
    live = await service.live_book_ids(db, [task.book_id])
    return {**service.task_view(task, live_books=live), "stats": stats, "monitor": monitor}


@router.get("/tasks/{task_id}/products/{filename}")
async def get_product(
    task_id: str,
    filename: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """产物 md 全文（结果目录「点文件名预览」与导出共用，c-deconstruct-product-preview）。

    内容由 data 现渲染（c-deconstruct-evidence-report）：作家 md 不含证据类字段。
    """
    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    products = service.products_of(task)
    if filename not in products:
        raise HTTPException(404, "产物不存在")
    return {"filename": filename, "content": products[filename]}


@router.get("/tasks/{task_id}/evidence")
async def get_evidence(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """证据报告（c-deconstruct-evidence-report）：任务资料 JSON 现渲染的证据账。

    作家 md 已去证据；证据章节/可信度/说明/原文佐证搬家到这里按维度呈现。
    鉴权与归属同预览端点（产物查看不设档位门）；非完成态/无产物给空 dims。
    """
    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    return {"task_id": task_id, "dims": evidence_report(service.products_raw(task))}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    if task.status not in ("queued", "running"):
        raise HTTPException(409, "任务已结束，无法取消")
    task.status = "cancelled"
    task.finished_at = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()
    return {"id": task.id, "status": task.status}


@router.post("/tasks/{task_id}/resume")
@ai_feature("deconstruct")
async def resume_task(
    task_id: str,
    body: dict | None = None,
    user: dict = Depends(get_current_user),
    _gate: bool = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """断点续拆：failed/cancelled → 重新入队（run_task 按维度 state 跳过已完成）。

    body.api_config_id/ai_model 可选＝换模型续拆（c-deconstruct-resilience D8）：
    沿 resolve_client 同源谓词校验新配置可用，成功后更新任务并追加 model_history；
    已完成单元（卡片/批次）在新模型下照常复用。
    """
    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    if task.status not in ("failed", "cancelled"):
        raise HTTPException(409, "仅失败/已取消任务可续拆")
    if not task.source_path or not os.path.exists(task.source_path):
        task.status = "need_reupload"
        await db.commit()
        raise HTTPException(409, "源文件缺失，请先重传文件")
    if isinstance(body, dict) and (body.get("api_config_id") or body.get("ai_model")):
        new_config = str(body.get("api_config_id") or task.api_config_id)
        new_model = str(body.get("ai_model") or task.ai_model)
        from deconstruct.service import resolve_client

        try:
            await resolve_client(_user_id(user), new_config, new_model)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if new_config != task.api_config_id or new_model != task.ai_model:
            history = []
            try:
                history = json.loads(task.model_history_json or "[]")
            except ValueError:
                history = []
            history.append({
                "api_config_id": new_config,
                "ai_model": new_model,
                "at": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
            })
            task.model_history_json = json.dumps(history, ensure_ascii=False)
            task.api_config_id = new_config
            task.ai_model = new_model[:120]
    from deconstruct.dispatcher import start_dispatcher

    start_dispatcher()  # 兜底（常驻线程一般已在）：置 queued 后由 dispatcher 接手
    task.status = "queued"
    await db.commit()
    return {"id": task.id, "status": task.status}


@router.post("/tasks/{task_id}/retry-upload")
@ai_feature("deconstruct")
async def retry_upload(
    task_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    _gate: bool = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """需重传恢复：源文件重新落盘，回原排队位次。"""
    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    if task.status != "need_reupload":
        raise HTTPException(409, "任务不在需重传状态")
    size = 0
    chunks: list[bytes] = []
    while chunk := await file.read(1 << 20):
        size += len(chunk)
        if size > MAX_SOURCE_BYTES:
            raise HTTPException(400, "文件超过 50MB 上限，请拆分后重试")
        chunks.append(chunk)
    raw = b"".join(chunks)
    try:
        decode_text(raw)  # 重传与首传同守卫：UTF-16/空字节等坏编码同口径拒收（存任务行编码必在探测链内）
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    os.makedirs(os.path.dirname(task.source_path), exist_ok=True)
    with open(task.source_path, "wb") as f:
        f.write(raw)
    task.status = "queued"
    await db.commit()
    return {"id": task.id, "status": task.status}


@router.post("/tasks/{task_id}/import-book", status_code=202)
@ai_feature("deconstruct-import")
async def import_book(
    task_id: str,
    body: dict | None = None,
    user: dict = Depends(get_current_user),
    _gate: bool = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """建书受理（c-deconstruct-import-async）：立即返回，整段后台执行。

    四臂（design D9）：
    - `book_id` 指向现存书（含本次变更前的 `completed + book_id` 存量任务）→ 200 幂等回同一本，
      顺带把状态读时升级为 `imported`；
    - 书已被删/不存在 → 解绑后按本次勾选重建（不复活旧书）；
    - `importing` → 409 返回当前状态，不排第二次；
    - `completed | import_failed` → 满额检查后条件抢占，202 + 起执行体。
    """
    from auth_local.deps import project_quota_reject

    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    if not task.api_config_id:
        raise HTTPException(409, "任务缺模型信息")

    invalid_key = False
    # ① 幂等第一判定：book_id（不看 status）——存量任务也是 completed+book_id
    if task.book_id:
        from novels.service import get_novel

        existing = await get_novel(db, task.book_id, _user_id(user))
        if existing is not None:
            if task.status == "completed":
                task.status = "imported"  # 读时升级：旧任务未带 import 载荷也认
                await db.commit()
            # 幂等返回是 200（已建成），与「202 受理」靠状态码区分（design D9）
            return JSONResponse(
                status_code=200,
                content={
                    "status": task.status,
                    "book_id": task.book_id,
                    "name": task.book_name,
                    "skipped": [],
                    "warnings": [
                        "任务已建过书（幂等返回），本次未重复写入；需要补灌请新建任务或删书重导"
                    ],
                },
            )
        # 键已失效（软删/不存在/他人）：解绑并回到「可重建」态，再按本次勾选重建
        task.book_id = None
        if task.status == "imported":
            task.status = "completed"
        await db.commit()
        invalid_key = True
    else:
        invalid_key = False

    if task.status == "importing":
        st = await imports.state_of(task_id)
        raise HTTPException(
            409,
            {
                "reason": "import_in_progress",
                "message": "建书已在进行中，请等它跑完或先取消",
                "import": imports.view(st),
            },
        )
    if task.status not in ("completed", "import_failed"):
        raise HTTPException(409, "任务未完成，无法建书")

    # ② 满额在受理时就拦（不烧一次精炼）；写入前执行体还会再查一次防并发越限
    reject = await project_quota_reject(db, _user_id(user))
    if reject:
        raise HTTPException(403, reject)

    raw_items = body.get("items") if isinstance(body, dict) else None
    items = imports.normalize_items(raw_items)
    seed: list[str] = []
    if invalid_key:
        seed.append("原建书已被删除或不存在，已按本次勾选重新建书")
    run_id = await imports.claim(task_id, items, seed_warnings=seed)
    if run_id is None:
        raise HTTPException(409, "任务状态已变化，请刷新后重试")
    imports.start(task_id)
    # claim 在独立 session 里提交，请求 session 里的 task 仍是旧实例——状态必须重读
    state = await imports.state_of(task_id)
    return {
        "status": "importing",
        "book_id": None,
        "name": task.book_name,
        "skipped": [],
        "warnings": [],
        "import": imports.view(state),
    }


@router.post("/tasks/{task_id}/import-book/cancel")
async def cancel_import(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取消建书：回到已完成、清理半成品。

    刻意**不挂 AI 门**（`require_ai_access`/档位门）：这是止损动作——Key 失效、会员到期、
    降档的用户必须仍然能停下正在烧 token 的建书（评审 P1）。
    """
    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    if not await imports.cancel(task_id):
        raise HTTPException(409, "当前没有正在进行的建书")
    fresh = await service.get_task(db, task_id, _user_id(user))
    # 请求 session 里还是取消前的实例（identity map）：不 refresh 会把 importing 回给前端
    if fresh is not None:
        await db.refresh(fresh)
    return {"status": fresh.status if fresh else "completed"}


@router.post("/tasks/{task_id}/export")
@ai_feature("deconstruct")
async def export_task(
    task_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _gate: bool = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """存本地文件夹出口：勾中产物＋README 物化到所选目录。"""
    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    if task.status not in service.RESULT_READY:
        raise HTTPException(409, "任务未完成，无法导出")
    dest = str(body.get("dest_dir") or "").strip()
    if not dest:
        raise HTTPException(400, "请先选择导出文件夹")
    files = [f for f in (body.get("files") or []) if f.endswith(".md")]
    if not files:
        raise HTTPException(400, "至少勾选 1 份产物")
    try:
        state = json.loads(task.dims_json or "{}")
    except ValueError:
        state = {}
    from deconstruct.pipeline import _graph_export_on

    graph_err = ""
    graph = None
    if _graph_export_on():  # 开关关＝一律文档版（缓存图谱也不发——评审 P2-1 关径全实现）
        if state.get("graph_error"):
            # 装配结构性异常：回落文档版（md 永不互拖），响应携错因供前端提示
            graph_err = str(state["graph_error"])
        elif isinstance(state.get("graph"), dict):
            graph = state["graph"]
    try:
        result = apply.export_products(task, dest, files, graph=graph)
    except OSError as e:
        raise HTTPException(400, f"导出失败：{e.strerror or e}") from e
    result["graph_error"] = graph_err
    task.exported_at = datetime.now(UTC).replace(tzinfo=None)  # 已取标记：badge 不再计数
    await db.commit()
    return result


@router.get("/tasks/{task_id}/library-candidates")
async def library_candidates(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """角色库收录候选（c-charlib-deconstruct-exit）：投影角色＋已收录集合＋可用性。"""
    from deconstruct.cards import cards_from_products
    from library import service as library_service

    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    if task.status not in service.RESULT_READY:
        # 建书三态仍可收录（RESULT_READY）；这里只剩拆解中/排队/取消/待重传的真拒因
        reason = "任务还没拆完" if task.status in ("queued", "running") else "任务在这个状态下没有可收录的产物"
        return {"can_import": False, "reason": reason, "items": []}
    try:
        products = json.loads(task.products_json or "{}")
    except ValueError:
        products = {}
    product = products.get("characters") if isinstance(products, dict) else None
    data = product.get("data") if isinstance(product, dict) else None
    cards = cards_from_products(data or {})
    if not cards:
        return {"can_import": False, "reason": "这批产物里没有角色设定", "items": []}
    collected = await library_service.collected_source_keys(db, _user_id(user), task.id)
    items = []
    for idx, card in enumerate(cards, start=1):
        key = library_service.deconstruct_source_key(card, idx)
        items.append(
            {
                "key": key,
                "name": key,
                "role": card.get("role", "配角"),
                "persona": card.get("persona", ""),
                "gender": card.get("gender", ""),
                "age": card.get("age", ""),
                "collected": key in collected,
            }
        )
    return {"can_import": True, "reason": "", "items": items}


@router.post("/tasks/{task_id}/to-library")
async def to_library(
    task_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """收进角色库（第三出口）：只写库、不动书；幂等由库侧 provenance 兜底。"""
    from library import service as library_service

    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    if task.status not in service.RESULT_READY:
        raise HTTPException(409, "任务未完成，无法收录")
    try:
        products = json.loads(task.products_json or "{}")
    except ValueError:
        products = {}
    product = products.get("characters") if isinstance(products, dict) else None
    data = product.get("data") if isinstance(product, dict) else None
    if not data:
        raise HTTPException(422, "这批产物里没有角色设定，无法收录")
    picks = [str(p).strip() for p in (body.get("picks") or []) if str(p or "").strip()]
    if not picks:
        raise HTTPException(400, "至少勾选 1 个角色")

    result = await library_service.import_from_deconstruct(
        db,
        _user_id(user),
        task,
        picks=picks,
        rename=bool(body.get("rename")),
    )
    task.exported_at = datetime.now(UTC).replace(tzinfo=None)  # 已取标记：badge 不再计数
    await db.commit()
    return result


@router.post("/tasks/{task_id}/collect-to-kb")
async def collect_to_kb(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """收进知识库：拆书产物 → 知识条目（手法/文风/文笔/世界/角色，幂等）。"""
    from kb.deconstruct_import import map_deconstruct_products
    from kb.service import ensure_default_library
    from models.kb import KbEntry

    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    if task.status != "completed":
        raise HTTPException(409, "任务未完成，无法收录")
    try:
        products = json.loads(task.products_json or "{}")
    except ValueError:
        products = {}
    if not products:
        raise HTTPException(422, "这批产物为空，无法收录")

    genre = str(task.genre or "").strip()
    uid = _user_id(user)

    entries, warnings = map_deconstruct_products(uid, task_id, genre, products)

    # 幂等：查已有的 src_key，跳过重复
    existing_keys = set()
    if entries:
        src_keys = [e.src_key for e in entries]
        stmt = select(KbEntry.src_key).where(
            KbEntry.user_id == uid,
            KbEntry.src_ref == task_id,
            KbEntry.src_key.in_(src_keys),
        )
        rows = (await db.execute(stmt)).scalars().all()
        existing_keys = set(rows)

    new_entries = [e for e in entries if e.src_key not in existing_keys]
    skipped = len(entries) - len(new_entries)

    for e in new_entries:
        db.add(e)
        await db.flush()
        await ensure_default_library(db, uid, e.genre, e.concept)

    await db.commit()

    return {
        "ok": True,
        "data": {
            "collected": len(new_entries),
            "skipped": skipped,
            "total_mapped": len(entries),
            "warnings": warnings,
        },
    }


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await service.get_task(db, task_id, _user_id(user))
    _require(task, user)
    if task.status == "running":
        raise HTTPException(409, "任务拆解中，请先取消再删除")
    if task.status == "importing":
        # 建书在后台跑：删掉任务行会让执行体无处写终态，还会留下一本无主书（评审 P0）
        raise HTTPException(409, "建书中，请先取消建书再删除")
    if task.source_path and os.path.isdir(os.path.dirname(task.source_path)):
        shutil.rmtree(os.path.dirname(task.source_path), ignore_errors=True)
    await db.delete(task)
    await db.commit()
    return {"deleted": task_id}
