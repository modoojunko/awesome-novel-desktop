"""朱雀检测路由（c-zhuque-ai-detect）。

- ``/api/v1/zhuque/*``：配置域（GET/PUT/DELETE config、POST test）——只挂登录，
  配置页签全档可见可配（门禁落使用口）。
- ``/api/novels/{project_id}/chapters/{chapter_ref}/zhuque-check``：执行域——
  登录＋会员级防御校验（require_ai_access，同 ai-check）；MAX 精确判定在前端快照。
  章数据只读；结果不落库。

错误语义（响应 detail 为可读中文，前端按状态码映射出口）：
  400 empty_prose | 401 上游 Key 无效 | 403 会员校验（require_ai_access）
  404 章/项目不存在 | 409 zhuque_check_in_progress | 422 prose_too_long
  429 限流或额度耗尽 | 502 上游 5xx/分段错配 | 503 zhuque_not_configured
  504 网络/超时
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import require_ai_access
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from workflow.engine import _validate_ref, load_chapter
from zhuque import service
from zhuque.client import ZhuqueUpstreamError
from zhuque.segmentation import MAX_PROSE_CHARS

config_router = APIRouter(prefix="/api/v1/zhuque", tags=["zhuque"])
check_router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/zhuque-check",
    tags=["zhuque"],
)
# 存档读取与执行分路由：GET 挂章前缀（/zhuque-result），不嵌在 /zhuque-check 下
result_router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}",
    tags=["zhuque"],
)

_UPSTREAM_MAP = {
    # 上游 401/403（朱雀 Key 无效）映射为本端 401，但 reason="zhuque_auth"：
    # C端 request() 对 401 的默认语义是「会话失效→踢登录」，须豁免该 reason
    # （改抛原 message、不清凭据），否则作家配错 Key 会被踢出登录。
    401: (401, "zhuque_auth", "API Key 无效或已失效——去「模型配置 → 朱雀」检查或更换"),
    403: (401, "zhuque_auth", "API Key 无效或已失效——去「模型配置 → 朱雀」检查或更换"),
    429: (429, "zhuque_quota", "触发限流或本月免费额度已用完，以腾讯云控制台为准"),
    0: (504, "zhuque_network", "无法连接朱雀服务或响应超时，请稍后重试"),
}


def _map_upstream(e: ZhuqueUpstreamError) -> HTTPException:
    if e.status in _UPSTREAM_MAP:
        code, reason, message = _UPSTREAM_MAP[e.status]
    elif e.status >= 500:
        code, reason, message = 502, "zhuque_upstream", "朱雀服务暂时不可用，请稍后重试"
    else:
        code, reason, message = 502, "zhuque_upstream", e.message
    return HTTPException(code, detail={"reason": reason, "message": message})


_SERVICE_ERRORS = {
    "zhuque_not_configured": (503, "尚未配置朱雀 Key——去「模型配置 → 朱雀」粘贴"),
    "empty_prose": (400, "本章还没有正文，先写正文再检测"),
    "prose_too_long": (422, f"正文超出单次检测上限（{MAX_PROSE_CHARS} 字），请分段处理"),
    "zhuque_check_in_progress": (409, "本章检测正在进行中，请稍候"),
    "segment_mismatch": (502, "检测结果与段落不一致，请重试"),
}


def _map_service_error(e: ValueError) -> HTTPException:
    code, message = _SERVICE_ERRORS.get(str(e), (400, str(e)))
    return HTTPException(code, detail={"reason": str(e), "message": message})


# ─── 配置域（全档可配；Key 是作者自己的腾讯资产） ───


@config_router.get("/config")
async def get_config(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_config_status(db, user["id"])


@config_router.put("/config")
async def put_config(
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    api_key = str((body or {}).get("api_key", "") or "")
    if not api_key.strip():
        # 空串＝未提供（不覆盖已存密钥，沿用 api_configs 既有守卫口径）
        return await service.get_config_status(db, user["id"])
    try:
        return await service.save_config(db, user["id"], api_key)
    except ValueError as e:
        if "已被其他配置使用" in str(e):
            raise HTTPException(409, detail={"reason": "name_conflict", "message": str(e)}) from e
        raise HTTPException(400, detail={"reason": "invalid", "message": str(e)}) from e


@config_router.delete("/config")
async def delete_config(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await service.delete_config(db, user["id"])
    return {"ok": ok}


@config_router.post("/test")
async def test_config(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.test_config(db, user["id"])
    except ZhuqueUpstreamError as e:  # 理论不抛（service 内部已归档），防御兜底
        raise _map_upstream(e) from e


# ─── 执行域（登录＋会员防御；章数据只读） ───


@check_router.post("")
async def check_chapter(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    chapter = await load_chapter(project.root_path, chapter_ref) or {}
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    prose = chapter.get("prose") or ""
    try:
        return await service.check_chapter(
            db, user_id=user["id"], project_id=project_id, chapter_ref=chapter_ref, prose=prose
        )
    except ValueError as e:
        raise _map_service_error(e) from e
    except ZhuqueUpstreamError as e:
        raise _map_upstream(e) from e


@result_router.get("/zhuque-result")
async def get_stored_zhuque_result(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按章读检测结果存档（c-zhuque-persist）：只读零额度；无档 {stored:false}。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    try:
        return await service.get_stored_result(db, project_id=project_id, chapter_ref=chapter_ref)
    except KeyError:
        raise HTTPException(404, "Chapter not found") from None
