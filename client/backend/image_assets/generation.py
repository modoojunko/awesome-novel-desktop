"""图像生成任务服务（c-image-generation）：创建/取消/恢复/执行 image_jobs。

任务不占用写作 ``job_runner`` 的全局单飞槽；同一目标（书封面/角色头像/批量头像）
靠部分唯一索引保证同时最多一个 active job。生成逐候选调用供应商：每个候选有独立
seed（供应商不支持 seed 时用确定性 prompt 变体）与独立 prompt_hash。
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api_configs.crypto import decrypt_api_key
from image_assets.adapters import (
    ImageGenerationSpec,
    ImageProviderError,
    capabilities_for,
    generate_images,
    variant_prompt,
)
from image_assets.prompt_builder import (
    MAX_SEED,
    PROMPT_TEMPLATE_VERSION,
    build_avatar_prompt,
    build_cover_prompt,
    effective_prompt_hash,
)
from image_assets.service import (
    Conflict,
    Unprocessable,
    create_generated_asset,
    ensure_signing_key,
    now_utc,
    sweep_expired_assets,
)
from models.character import Character
from models.image_asset import (
    BookImageSettings,
    ImageBatchItem,
    ImageConfig,
    ImageJob,
)
from models.project import Novel

JOB_STATUSES = {"queued", "running", "completed", "failed", "cancelled"}
ITEM_STATUSES = {"pending", "running", "completed", "failed", "cancelled", "cancelled_billed"}
MAX_CANDIDATES = 4


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _seed_at(base: int | None, index: int) -> int:
    return ((base or 0) + index) % MAX_SEED


def _safe_json(raw: str | None, fallback):
    try:
        return json.loads(raw) if raw else fallback
    except (TypeError, ValueError):
        return fallback


def job_to_dict(job: ImageJob, items: list[ImageBatchItem] | None = None) -> dict:
    data = {
        "id": job.id,
        "user_id": job.user_id,
        "novel_id": job.novel_id,
        "character_id": job.character_id,
        "target_type": job.target_type,
        "target_id": job.target_id,
        "purpose": job.purpose,
        "kind": job.kind,
        "status": job.status,
        "image_config_id": job.image_config_id,
        "provider": job.provider,
        "model": job.model,
        "style_key": job.style_key,
        "prompt_hash": job.prompt_hash,
        "base_seed": job.base_seed,
        "requested_n": job.requested_n,
        "produced_count": job.produced_count,
        "billed_n": job.billed_n,
        "cancelled_billed_count": job.cancelled_billed_count,
        "duration_ms": job.duration_ms,
        "error_kind": job.error_kind,
        "error_message": job.error_message,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
    if items is not None:
        data["items"] = [{
            "id": item.id,
            "character_id": item.character_id,
            "item_index": item.item_index,
            "status": item.status,
            "seed": item.seed,
            "prompt_hash": item.prompt_hash,
            "produced_count": item.produced_count,
            "billed_n": item.billed_n,
            "duration_ms": item.duration_ms,
            "error_kind": item.error_kind,
            "error_message": item.error_message,
        } for item in items]
    return data


async def _load_items(db: AsyncSession, job_id: str) -> list[ImageBatchItem]:
    return list((await db.scalars(
        select(ImageBatchItem).where(ImageBatchItem.job_id == job_id).order_by(ImageBatchItem.item_index)
    )).all())


async def _preview(
    db: AsyncSession, novel: Novel, kind: str, character: Character | None,
):
    if kind == "cover":
        return await build_cover_prompt(db, novel)
    if character is None:
        raise Unprocessable("头像必须指定角色", "character_required")
    return await build_avatar_prompt(db, novel, character)


async def create_job(
    db: AsyncSession, *, user_id: str, novel_id: str, kind: str,
    character_id: str | None = None, purpose: str = "generate",
    character_ids: list[str] | None = None, n: int = 2,
) -> dict:
    from image_assets.service import _owned_character, _owned_novel

    novel = await _owned_novel(db, user_id, novel_id)
    if kind not in {"cover", "avatar"}:
        raise Unprocessable("kind 必须是 cover 或 avatar", "invalid_kind")
    if purpose not in {"generate", "test", "batch"}:
        raise Unprocessable("purpose 非法", "invalid_purpose")
    if not 1 <= int(n) <= MAX_CANDIDATES:
        raise Unprocessable(f"候选数必须在 1..{MAX_CANDIDATES}", "invalid_n")
    character = None
    if kind == "avatar" and purpose != "batch":
        if not character_id:
            raise Unprocessable("头像必须指定角色", "character_required")
        character = await _owned_character(db, user_id, novel_id, character_id)
    if purpose == "batch" and character_ids:
        # 批量任务的配置/画风快照以第一个角色为代表；逐项 prompt 在执行时按角色重建。
        character = await _owned_character(db, user_id, novel_id, character_ids[0])

    preview = await _preview(db, novel, kind, character)
    if preview.get("model_unbound"):
        raise Conflict("本书图像模型未绑定，请先在封面工坊选择模型", "model_unbound")
    config_id = None
    declared = {}
    settings_row = (await db.execute(
        select(BookImageSettings).where(BookImageSettings.novel_id == novel_id)
    )).scalar_one_or_none()
    if settings_row and settings_row.image_config_id:
        config_id = settings_row.image_config_id
        cfg = await db.get(ImageConfig, config_id)
        if cfg:
            declared = _safe_json(cfg.declared_capabilities, {})
    caps = capabilities_for(str(preview.get("provider") or ""), declared)

    if purpose == "batch":
        if kind != "avatar":
            raise Unprocessable("批量任务只支持头像", "invalid_kind")
        ids = list(dict.fromkeys(character_ids or []))
        if not ids:
            raise Unprocessable("批量头像至少选择一个角色", "characters_required")
        # 归属校验 + 顺序稳定（按角色 seq）
        rows = (await db.scalars(
            select(Character).where(
                Character.novel_id == novel_id, Character.id.in_(ids)
            ).order_by(Character.seq)
        )).all()
        found = {row.id for row in rows}
        if len(found) != len(ids):
            raise Unprocessable("批量头像包含无效角色", "character_not_found")
        target_type, target_id = "batch", novel_id
        requested_n = len(rows)
    else:
        target_type = "character" if kind == "avatar" else "book"
        target_id = character_id if kind == "avatar" else novel_id
        rows = []
        requested_n = int(n)

    idempotency = hashlib.sha256(":".join([
        user_id, purpose, kind, target_id,
        str(preview.get("prompt_hash") or ""), str(requested_n),
    ]).encode()).hexdigest()
    existing = (await db.execute(select(ImageJob).where(
        ImageJob.user_id == user_id, ImageJob.idempotency_key == idempotency,
    ))).scalar_one_or_none()
    if existing:
        await db.commit()
        return job_to_dict(existing, await _load_items(db, existing.id))

    job = ImageJob(
        user_id=user_id,
        novel_id=novel_id,
        character_id=character_id if purpose != "batch" else None,
        target_type=target_type,
        target_id=target_id,
        purpose=purpose,
        kind=kind,
        status="queued",
        image_config_id=config_id,
        provider=str(preview.get("provider") or ""),
        model=str(preview.get("model") or ""),
        style_key=preview.get("style_key"),
        prompt_text=preview.get("prompt"),
        negative_prompt=preview.get("negative_prompt"),
        prompt_template_version=int(preview.get("prompt_template_version") or PROMPT_TEMPLATE_VERSION),
        prompt_hash=preview.get("prompt_hash"),
        request_json=json.dumps({
            "capabilities": caps,
            "size": preview.get("size"),
            "candidate_seeds": preview.get("candidate_seeds") or [],
        }, ensure_ascii=False),
        base_seed=preview.get("seed"),
        requested_n=requested_n,
        idempotency_key=idempotency,
    )
    db.add(job)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise Conflict("该目标已有生成任务在排队或执行", "job_active_exists") from e
    if rows:
        for idx, char_row in enumerate(rows):
            db.add(ImageBatchItem(job_id=job.id, character_id=char_row.id, item_index=idx))
    await db.commit()
    return job_to_dict(job, await _load_items(db, job.id))


async def list_jobs(
    db: AsyncSession, *, user_id: str, novel_id: str,
    kind: str | None = None, status: str | None = None, limit: int = 20,
) -> list[dict]:
    from image_assets.service import _owned_novel

    await _owned_novel(db, user_id, novel_id)
    if status and status not in JOB_STATUSES:
        raise Unprocessable("status 非法", "invalid_status")
    q = select(ImageJob).where(ImageJob.user_id == user_id, ImageJob.novel_id == novel_id)
    if kind:
        q = q.where(ImageJob.kind == kind)
    if status:
        q = q.where(ImageJob.status == status)
    jobs = (await db.scalars(
        q.order_by(ImageJob.created_at.desc()).limit(max(1, min(int(limit), 100)))
    )).all()
    out = []
    for job in jobs:
        out.append(job_to_dict(job, await _load_items(db, job.id)))
    return out


async def get_job(db: AsyncSession, *, user_id: str, job_id: str) -> dict:
    job = (await db.execute(select(ImageJob).where(
        ImageJob.id == job_id, ImageJob.user_id == user_id
    ))).scalar_one_or_none()
    if not job:
        raise Unprocessable("任务不存在", "job_not_found")
    return job_to_dict(job, await _load_items(db, job.id))


async def cancel_job(db: AsyncSession, *, user_id: str, job_id: str) -> dict:
    job = (await db.execute(select(ImageJob).where(
        ImageJob.id == job_id, ImageJob.user_id == user_id
    ))).scalar_one_or_none()
    if not job:
        raise Unprocessable("任务不存在", "job_not_found")
    if job.status in {"completed", "failed", "cancelled"}:
        return job_to_dict(job, await _load_items(db, job.id))
    if job.status == "queued":
        result = await db.execute(
            update(ImageJob)
            .where(ImageJob.id == job.id, ImageJob.status == "queued")
            .values(status="cancelled", cancel_requested=True, finished_at=now_utc())
        )
        if result.rowcount:
            await db.execute(
                update(ImageBatchItem)
                .where(ImageBatchItem.job_id == job.id, ImageBatchItem.status == "pending")
                .values(status="cancelled", finished_at=now_utc())
            )
        await db.commit()
    else:
        job.cancel_requested = True
        await db.commit()
    job = await db.get(ImageJob, job_id)
    assert job is not None
    return job_to_dict(job, await _load_items(db, job.id))


async def retry_job(db: AsyncSession, *, user_id: str, job_id: str) -> dict:
    job = (await db.execute(select(ImageJob).where(
        ImageJob.id == job_id, ImageJob.user_id == user_id
    ))).scalar_one_or_none()
    if not job:
        raise Unprocessable("任务不存在", "job_not_found")
    if job.status not in {"failed", "cancelled"}:
        raise Conflict("只有失败/取消的任务可以重试", "job_not_retryable")
    job.status = "queued"
    job.cancel_requested = False
    job.error_kind = None
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    await db.execute(
        update(ImageBatchItem)
        .where(ImageBatchItem.job_id == job.id, ImageBatchItem.status.in_(("failed", "cancelled")))
        .values(status="pending", error_kind=None, error_message=None, started_at=None, finished_at=None)
    )
    await db.commit()
    return job_to_dict(job, await _load_items(db, job.id))


async def startup_sweep() -> int:
    from db import async_session

    async with async_session() as db:
        running = (await db.scalars(select(ImageJob).where(ImageJob.status == "running"))).all()
        for job in running:
            job.status = "failed"
            job.error_kind = "interrupted"
            job.error_message = "应用重启导致任务中断，可重试"
            job.finished_at = now_utc()
        await db.commit()
        return len(running)


async def list_queued_ids() -> list[str]:
    from db import async_session

    async with async_session() as db:
        rows = (await db.scalars(
            select(ImageJob.id).where(ImageJob.status == "queued").order_by(ImageJob.created_at)
        )).all()
        return list(rows)


async def claim_job(job_id: str) -> bool:
    from db import async_session

    async with async_session() as db:
        result = await db.execute(
            update(ImageJob)
            .where(ImageJob.id == job_id, ImageJob.status == "queued")
            .values(status="running", started_at=now_utc())
        )
        await db.commit()
        return result.rowcount > 0


def _request_caps(job: ImageJob) -> dict[str, bool]:
    payload = _safe_json(job.request_json, {})
    caps = payload.get("capabilities") if isinstance(payload, dict) else None
    return caps if isinstance(caps, dict) else {}


def _preview_like(job: ImageJob, prompt: str, seed: int | None, candidate_seeds: list[int]) -> dict:
    payload = _safe_json(job.request_json, {})
    size = payload.get("size") if isinstance(payload, dict) else {}
    return {
        "kind": job.kind,
        "prompt": prompt,
        "negative_prompt": job.negative_prompt or "",
        "prompt_template_version": job.prompt_template_version or PROMPT_TEMPLATE_VERSION,
        "style_key": job.style_key or "ink",
        "size": size if isinstance(size, dict) else {},
        "seed": seed,
        "model": job.model,
        "provider": job.provider,
        "capabilities": _request_caps(job),
        "candidate_seeds": candidate_seeds,
    }


async def _generate_one(
    db: AsyncSession, job: ImageJob, *, prompt: str, seed: int | None,
    prompt_hash: str, character_id: str | None, source: str,
) -> int:
    cfg = await db.get(ImageConfig, job.image_config_id)
    if not cfg or cfg.status != "active" or cfg.user_id != job.user_id:
        raise ImageProviderError("invalid", "图像配置已删除或不可用")
    caps = _request_caps(job)
    spec = ImageGenerationSpec(
        provider=job.provider,
        model=job.model,
        prompt=prompt,
        negative_prompt=job.negative_prompt or "",
        kind="avatar" if job.kind == "avatar" else "cover",
        n=1,
        seed=seed if caps.get("seed_supported", True) else None,
        watermark=False,
        capabilities=caps,
    )
    images = await generate_images(
        base_url=cfg.base_url, api_key=decrypt_api_key(cfg.api_key), spec=spec,
    )
    for image in images:
        await create_generated_asset(
            db,
            user_id=job.user_id,
            novel_id=job.novel_id,
            kind=job.kind,
            data=image.data,
            character_id=character_id,
            source=source,
            provider=job.provider,
            model=job.model,
            style_key=job.style_key,
            prompt_hash=prompt_hash,
            prompt_text=prompt,
            negative_prompt=job.negative_prompt,
            prompt_template_version=job.prompt_template_version,
            seed=seed,
            job_id=job.id,
        )
    return len(images)


async def _cancel_remaining_items(db: AsyncSession, job: ImageJob) -> None:
    await db.execute(
        update(ImageBatchItem)
        .where(ImageBatchItem.job_id == job.id, ImageBatchItem.status.in_(("pending", "running")))
        .values(status="cancelled", finished_at=now_utc())
    )


async def run_job(job_id: str) -> dict:
    from db import async_session

    started = time.monotonic()
    async with async_session() as db:
        job = await db.get(ImageJob, job_id)
        if not job or job.status != "running":
            return job_to_dict(job) if job else {}
        await ensure_signing_key(db)
        await sweep_expired_assets(db, user_id=job.user_id)
        produced = 0
        billed = 0
        error: ImageProviderError | None = None
        try:
            if job.purpose == "batch":
                items = await _load_items(db, job.id)
                for item in items:
                    if item.status in {"completed", "failed", "cancelled", "cancelled_billed"}:
                        continue
                    await db.refresh(job)
                    if job.cancel_requested:
                        await _cancel_remaining_items(db, job)
                        break
                    item.started_at = now_utc()
                    item.status = "running"
                    await db.commit()
                    character = await db.get(Character, item.character_id)
                    novel = await db.get(Novel, job.novel_id)
                    if not character or not novel:
                        item.status = "failed"
                        item.error_kind = "invalid"
                        item.error_message = "角色或书不存在"
                        item.finished_at = now_utc()
                        await db.commit()
                        continue
                    preview = await build_avatar_prompt(db, novel, character)
                    caps = _request_caps(job)
                    seed = preview.get("seed")
                    item.seed = seed if caps.get("seed_supported", True) else None
                    item.prompt_hash = effective_prompt_hash(preview, 0, capabilities=caps)
                    item_started = time.monotonic()
                    try:
                        count = await _generate_one(
                            db, job,
                            prompt=preview["prompt"], seed=preview.get("seed"),
                            prompt_hash=item.prompt_hash or "",
                            character_id=character.id, source="batch",
                        )
                        item.status = "completed"
                        item.produced_count = count
                        item.billed_n = count
                        item.duration_ms = int((time.monotonic() - item_started) * 1000)
                        produced += count
                        billed += count
                    except ImageProviderError as e:
                        item.status = "failed"
                        item.error_kind = e.kind
                        item.error_message = e.message[:500]
                    item.finished_at = now_utc()
                    await db.commit()
            else:
                candidate_seeds = [_seed_at(job.base_seed, i) for i in range(max(1, job.requested_n))]
                caps = _request_caps(job)
                source = "test" if job.purpose == "test" else "generation"
                for index in range(max(1, job.requested_n)):
                    await db.refresh(job)
                    if job.cancel_requested:
                        break
                    prompt = variant_prompt(
                        job.prompt_text or "", index,
                        candidate_seeds[index], caps.get("seed_supported", True),
                    )
                    seed = candidate_seeds[index] if caps.get("seed_supported", True) else None
                    prompt_hash = effective_prompt_hash(
                        _preview_like(job, job.prompt_text or "", job.base_seed, candidate_seeds),
                        index,
                        capabilities=caps,
                        prompt_override=prompt,
                    )
                    count = await _generate_one(
                        db, job, prompt=prompt, seed=seed, prompt_hash=prompt_hash,
                        character_id=job.character_id, source=source,
                    )
                    produced += count
                    billed += count
                    job.produced_count = produced
                    job.billed_n = billed
                    await db.commit()
        except ImageProviderError as e:
            error = e
        except Exception as e:  # noqa: BLE001 — 任务层兜底：保留已产生候选，落失败终态
            error = ImageProviderError("invalid", f"生成任务异常中断：{e}")

        await db.refresh(job)
        job.produced_count = produced
        job.billed_n = billed
        job.duration_ms = int((time.monotonic() - started) * 1000)
        if job.cancel_requested:
            await _cancel_remaining_items(db, job)
            job.status = "cancelled"
        elif error is not None:
            job.status = "failed"
            job.error_kind = error.kind
            job.error_message = error.message[:500]
        elif produced == 0:
            job.status = "failed"
            job.error_kind = "empty"
            job.error_message = "供应商未返回任何图片"
        else:
            job.status = "completed"
        job.finished_at = now_utc()
        await db.commit()
        return job_to_dict(job, await _load_items(db, job.id))
