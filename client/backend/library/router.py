"""角色库端点（c-character-library）——账号级跨书角色库。

九操作：列表/新建/详情/整卡保存/删卡/头像读取/书内收录/书内同步/用到新书/AI 随机起名。
全部 get_current_user；random-name 不挂档位门（本地兜底恒可用，见 design D5）。
静态段（/import/book、/random-name）必须声明在 /{card_id} 族之前防路由遮蔽。
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import ai_feature, get_current_user, require_tier_access
from db import get_db
from library import service as svc
from models.project import Novel

router = APIRouter(prefix="/api/character-library", tags=["character-library"])

_STATUS = {
    "not_found": 404,
    "novel_not_found": 404,
    "character_not_found": 404,
    "avatar_not_found": 404,
    "source_gone": 410,
    # 头像生成（c-library-avatar-gen）：缺配置 400 可读；供应商失败 502
    "no_image_config": 400,
    "image_timeout": 502,
    "image_failed": 502,
}


def _http_error(e: svc.LibraryError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS.get(e.code, 400),
        detail={"code": e.code, "message": e.message},
    )


async def _owned_novel(db: AsyncSession, user_id: str, novel_id: str) -> Novel:
    novel = (
        await db.execute(
            select(Novel).where(
                Novel.id == novel_id,
                Novel.user_id == user_id,
                Novel.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if novel is None:
        raise HTTPException(
            status_code=404, detail={"code": "novel_not_found", "message": "书不存在"}
        )
    return novel


# ── 静态段（必须先于 /{card_id}） ─────────────────────────────────────────


@router.post("/import/book")
async def import_from_book(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """书内卡整卡收进库（幂等：重复收录返回已有卡）。"""
    novel_id = str(body.get("novel_id") or "")
    character_id = str(body.get("character_id") or "")
    if not novel_id or not character_id:
        raise HTTPException(
            status_code=400, detail={"code": "invalid_body", "message": "缺 novel_id 或 character_id"}
        )
    novel = await _owned_novel(db, user["id"], novel_id)
    try:
        data = await svc.collect_from_book(
            db, user["id"], novel, character_id, rename=bool(body.get("rename"))
        )
    except svc.LibraryError as e:
        raise _http_error(e)
    return {"ok": True, "data": data}


@router.post("/random-name")
async def random_name(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """AI 起名＋随机年龄（16–55）；无 Key/失败/模板缺失本地兜底，恒 200。"""
    data = await svc.random_name(db, user["id"], str(body.get("gender") or ""))
    return {"ok": True, "data": data}


# ── 卡族 ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_cards(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """一次给全（文本字段＋头像引用）；筛选/搜索/排序在前端内存完成。"""
    return {"ok": True, "data": await svc.list_cards(db, user["id"])}


@router.post("")
async def create_card(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.create_card(db, user["id"], body)
    except svc.LibraryError as e:
        raise _http_error(e)
    return {"ok": True, "data": data}


@router.get("/{card_id}")
async def get_card(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.get_card_view(db, user["id"], card_id)
    except svc.LibraryError as e:
        raise _http_error(e)
    return {"ok": True, "data": data}


@router.put("/{card_id}")
async def update_card(
    card_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        data = await svc.update_card(db, user["id"], card_id, body)
    except svc.LibraryError as e:
        raise _http_error(e)
    return {"ok": True, "data": data}


@router.delete("/{card_id}")
async def delete_card(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """复制语义：只删库里的卡，书内已导入的副本不受影响。"""
    try:
        data = await svc.delete_card(db, user["id"], card_id)
    except svc.LibraryError as e:
        raise _http_error(e)
    return {"ok": True, "data": data}


@router.get("/{card_id}/avatar")
async def get_avatar(
    card_id: str,
    variant: str = "thumb",
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """头像字节（鉴权＋归属）；ETag 命中回 304，省重复传输。"""
    try:
        data, etag = await svc.avatar_bytes(db, user["id"], card_id, variant)
    except svc.LibraryError as e:
        raise _http_error(e)
    inm = request.headers.get("if-none-match") if request else None
    if inm and inm.strip('"') == etag:
        return Response(status_code=304, headers={"ETag": f'"{etag}"'})
    return Response(
        content=data,
        media_type="image/webp",
        headers={
            "ETag": f'"{etag}"',
            "Cache-Control": "private, no-cache",
        },
    )


@router.post("/{card_id}/avatar/generate")
@ai_feature("image-generate")
async def generate_avatar(
    card_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
    _access: bool = Depends(require_tier_access),
):
    """按卡上档案生成头像（复用书内头像生成能力；PRO 同权，账号级同步生成）。"""
    try:
        data = await svc.generate_avatar(db, user["id"], card_id, body)
    except svc.LibraryError as e:
        raise _http_error(e)
    return {"ok": True, "data": data}


@router.post("/{card_id}/sync-from-book")
async def sync_from_book(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """书→库手动同步：覆盖书域格与头像，库分类（题材/定位/小类）不动。"""
    try:
        data = await svc.sync_from_book(db, user["id"], card_id)
    except svc.LibraryError as e:
        raise _http_error(e)
    return {"ok": True, "data": data}


@router.post("/{card_id}/apply-to-book")
async def apply_to_book(
    card_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """复制落卡：撞名自动后缀、主角冲突落配角留痕、整卡含认知与头像。"""
    novel_id = str(body.get("novel_id") or "")
    if not novel_id:
        raise HTTPException(
            status_code=400, detail={"code": "invalid_body", "message": "缺 novel_id"}
        )
    try:
        data = await svc.apply_to_book(
            db, user["id"], card_id, novel_id, rename=bool(body.get("rename"))
        )
    except svc.LibraryError as e:
        raise _http_error(e)
    return {"ok": True, "data": data}
