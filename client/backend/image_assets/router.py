"""图像配置/资产 HTTP 端点（c-cover-avatar 阶段 1）。

路由顺序：静态段（links/adopt/undo）必须在 `/{asset_id}` 之前。
图片读取端点不挂 Bearer（签名 URL 自证）；其余全部走本地会话。
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import ai_feature, get_current_user, require_tier_access
from db import get_db
from image_assets import generation as jobs
from image_assets import service as svc
from image_assets.schemas import (
    AdoptBody,
    AvatarBatchCreate,
    BookImageSettingsBody,
    CharacterImageSettingsBody,
    ImageConfigCreate,
    ImageConfigUpdate,
    ImageJobCreate,
)

router = APIRouter(prefix="/api", tags=["image-assets"])
SVC_ERRORS = (svc.Unprocessable, svc.Conflict, svc.SigningUnavailable)


def _svc_error(e):
    if isinstance(e, svc.SigningUnavailable):
        return HTTPException(
            status_code=503,
            detail={"code": "image_unavailable", "message": "图像服务暂不可用"},
        )
    status = 409 if isinstance(e, svc.Conflict) else 400
    return HTTPException(
        status_code=status,
        detail={"code": getattr(e, "code", "conflict"), "message": e.detail},
    )


# ── 图像配置 ───────────────────────────────────────────────────────────────


@router.get("/image-configs")
async def list_image_configs(
    include_deleted: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    return {
        "ok": True,
        "data": await svc.list_configs(db, user["id"], include_deleted=include_deleted),
    }


@router.post("/image-configs", status_code=201)
async def create_image_config(
    body: ImageConfigCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.create_config(db, user["id"], body.model_dump())
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.put("/image-configs/{config_id}")
async def update_image_config(
    config_id: str,
    body: ImageConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.update_config(db, user["id"], config_id, body.model_dump(exclude_unset=True))
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.delete("/image-configs/{config_id}")
async def delete_image_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.delete_config(db, user["id"], config_id)
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.post("/image-configs/{config_id}/restore")
async def restore_image_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.restore_config(db, user["id"], config_id)
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


# ── 每书绑定 / 角色设置 ────────────────────────────────────────────────────


@router.get("/novels/{novel_id}/image-settings")
async def get_book_image_settings(
    novel_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.get_book_settings(db, user["id"], novel_id)
    except svc.Unprocessable as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.put("/novels/{novel_id}/image-settings")
async def put_book_image_settings(
    novel_id: str,
    body: BookImageSettingsBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    payload = body.model_dump()
    # 未显式提交 cover_seed 时保留库里的值，不能被 Pydantic 默认 None 清掉。
    if "cover_seed" not in body.model_fields_set:
        payload.pop("cover_seed", None)
    try:
        data = await svc.put_book_settings(db, user["id"], novel_id, payload)
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.patch("/novels/{novel_id}/image-settings")
async def patch_book_image_settings(
    novel_id: str,
    body: BookImageSettingsBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.patch_book_settings(
            db, user["id"], novel_id, body.model_dump(exclude_unset=True),
        )
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.get("/novels/{novel_id}/characters/{character_id}/image-settings")
async def get_character_image_settings(
    novel_id: str,
    character_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.get_character_settings(db, user["id"], novel_id, character_id)
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.put("/novels/{novel_id}/characters/{character_id}/image-settings")
async def put_character_image_settings(
    novel_id: str,
    character_id: str,
    body: CharacterImageSettingsBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.put_character_settings(
            db, user["id"], novel_id, character_id,
            str(body.avatar_prompt or ""), body.seed,
        )
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.patch("/novels/{novel_id}/characters/{character_id}/image-settings")
async def patch_character_image_settings(
    novel_id: str,
    character_id: str,
    body: CharacterImageSettingsBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.patch_character_settings(
            db, user["id"], novel_id, character_id,
            body.model_dump(exclude_unset=True),
        )
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


# ── Prompt 预览（只读；生成阶段复用同一 builder） ───────────────────────────


@router.get("/novels/{novel_id}/image-prompt")
async def cover_prompt_preview(
    novel_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.get_cover_prompt(db, user["id"], novel_id)
    except svc.Unprocessable as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.get("/novels/{novel_id}/characters/{character_id}/image-prompt")
async def avatar_prompt_preview(
    novel_id: str,
    character_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.get_avatar_prompt(db, user["id"], novel_id, character_id)
    except svc.Unprocessable as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


# ── 生成任务（PRO 起；图像 Key 作者自持，不查写作大模型）───────────────────


@router.post("/novels/{novel_id}/image-jobs", status_code=201)
@ai_feature("image-generate")
async def create_image_job(
    novel_id: str,
    body: ImageJobCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
    _access: bool = Depends(require_tier_access),
):
    try:
        data = await jobs.create_job(
            db, user_id=user["id"], novel_id=novel_id, kind=body.kind,
            character_id=body.character_id, purpose=body.purpose, n=body.n,
        )
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.post("/novels/{novel_id}/avatar-batches", status_code=201)
@ai_feature("image-generate")
async def create_avatar_batch(
    novel_id: str,
    body: AvatarBatchCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
    _access: bool = Depends(require_tier_access),
):
    try:
        data = await jobs.create_job(
            db, user_id=user["id"], novel_id=novel_id, kind="avatar",
            purpose="batch", character_ids=body.character_ids,
        )
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.get("/novels/{novel_id}/image-jobs")
async def list_image_jobs(
    novel_id: str,
    kind: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await jobs.list_jobs(
            db, user_id=user["id"], novel_id=novel_id,
            kind=kind, status=status, limit=limit,
        )
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.get("/image-jobs/{job_id}")
async def get_image_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        return {"ok": True, "data": await jobs.get_job(db, user_id=user["id"], job_id=job_id)}
    except SVC_ERRORS as e:
        raise _svc_error(e) from e


@router.post("/image-jobs/{job_id}/cancel")
async def cancel_image_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        return {"ok": True, "data": await jobs.cancel_job(db, user_id=user["id"], job_id=job_id)}
    except SVC_ERRORS as e:
        raise _svc_error(e) from e


@router.post("/image-jobs/{job_id}/retry")
@ai_feature("image-generate")
async def retry_image_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
    _access: bool = Depends(require_tier_access),
):
    try:
        return {"ok": True, "data": await jobs.retry_job(db, user_id=user["id"], job_id=job_id)}
    except SVC_ERRORS as e:
        raise _svc_error(e) from e


# ── 资产上传 / 列出 / 采用 / 撤销 / 签名读取 ───────────────────────────────


@router.get("/novels/{novel_id}/image-assets")
async def list_image_assets(
    novel_id: str,
    kind: str | None = Query(None),
    character_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.list_assets(
            db, user["id"], novel_id,
            kind=kind, character_id=character_id, status=status, limit=limit,
        )
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": data}


@router.post("/novels/{novel_id}/image-assets", status_code=201)
async def upload_image_asset(
    novel_id: str,
    kind: str = Form(...),
    character_id: str | None = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    data = await file.read(svc.MAX_BYTES + 1)
    if len(data) > svc.MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "file_too_large", "message": "图片超过 10MB"},
        )
    try:
        asset = await svc.create_asset(
            db, user["id"], novel_id, kind, data, character_id,
        )
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    return {"ok": True, "data": await svc.asset_to_dict(db, asset)}


@router.post("/image-assets/{asset_id}/adopt")
async def adopt_image_asset(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        asset = await svc.adopt_asset(db, user["id"], asset_id)
    except SVC_ERRORS as e:
        raise _svc_error(e) from e
    data = await svc.asset_to_dict(db, asset)
    data["undo_token"] = asset.undo_token
    return {"ok": True, "data": data}


@router.post("/image-assets/{asset_id}/undo")
async def undo_image_asset(
    asset_id: str,
    body: AdoptBody | None = None,
    token_q: str | None = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    token = token_q or (getattr(body, "undo_token", None) if body else None) \
        or (getattr(body, "token", None) if body else None)
    if not token:
        raise HTTPException(
            status_code=422,
            detail={"code": "undo_token_required", "message": "缺少撤销凭证"},
        )
    try:
        return {"ok": True, "data": await svc.undo_asset(db, user["id"], asset_id, token)}
    except SVC_ERRORS as e:
        raise _svc_error(e) from e


@router.get("/image-assets/{asset_id}/links")
async def refresh_image_asset_links(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        return {"ok": True, "data": await svc.get_asset_links(db, user["id"], asset_id)}
    except SVC_ERRORS as e:
        raise _svc_error(e) from e


@router.delete("/image-assets/{asset_id}")
async def delete_image_asset(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        return {"ok": True, "data": await svc.delete_candidate_asset(db, user["id"], asset_id)}
    except SVC_ERRORS as e:
        raise _svc_error(e) from e


@router.get("/image-assets/{asset_id}")
async def read_image_asset(
    asset_id: str,
    variant: str = Query("full"),
    exp: int = Query(...),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await svc.read_blob(db, asset_id, variant, exp, sig)
    except svc.SigningUnavailable as e:
        raise _svc_error(e) from e
    except svc.Unprocessable as e:
        raise HTTPException(
            status_code=400 if e.code == "invalid_variant" else 403,
            detail={"code": e.code, "message": e.detail},
        ) from e
    return Response(
        content=data,
        media_type="image/webp",
        headers={
            "X-Content-Type-Options": "nosniff",
            # 签名只有 1h；缓存必须更短，不能写 immutable。
            "Cache-Control": f"private, max-age={svc.SIGN_CACHE_SECONDS}",
        },
    )
