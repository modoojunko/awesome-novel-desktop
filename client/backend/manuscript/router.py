"""成稿下载路由（c-manuscript-download PR3）。

POST /api/manuscript/download/start —— 发起（单飞 409 带 running_kind）
GET  /api/manuscript/download/status —— 进度查询（任务级 state + 逐格式行）

与备份导出共用全局单飞（job_runner 单源）；书归属校验在发起时做（404）。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_local.middleware import get_current_user
from db import get_db

router = APIRouter(prefix="/api/manuscript", tags=["manuscript"])


class DownloadStartBody(BaseModel):
    book_id: str
    target_dir: str
    filename: str = ""
    formats: list[str]


def _reject_conflict() -> HTTPException:
    from job_runner import running_kind

    kind = running_kind()
    label = {"backup": "备份", "single": "导出", "download": "下载"}.get(kind or "", "任务")
    return HTTPException(
        409, detail={"message": f"已有{label}任务在进行中", "running_kind": kind}
    )


@router.post("/download/start")
async def download_start(
    body: DownloadStartBody,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    from manuscript import service

    # 格式白名单 + 大小写归一 + 去重保序；全不合法 → 422（前端主按钮已禁用，此处兜底）
    fmts = [f for f in dict.fromkeys(x.lower() for x in body.formats) if f in service.FORMATS]
    if not fmts:
        raise HTTPException(422, "请至少选择一种下载格式")

    # 书归属校验：非法访问 404（不泄露他人书的存在性）
    from models.project import Novel

    project = await db.get(Novel, body.book_id)
    if project is None or project.status == "deleted" or project.user_id != user["id"]:
        raise HTTPException(404, "作品不存在")
    if not body.target_dir.strip():
        raise HTTPException(422, "缺少保存目录")

    started = service.start_download_job(
        target_dir=body.target_dir,
        filename=body.filename,
        formats=fmts,
        book_id=body.book_id,
        user_id=user["id"],
    )
    if started is None:
        raise _reject_conflict()
    return {"code": 0, "data": started}


@router.get("/download/status")
async def download_status(user: dict = Depends(get_current_user)):
    from job_runner import status

    data = status()
    # 非下载任务在跑时按「无任务」口径返回（该端点只关心下载）；
    # 完成态（kind=download 且 state∈done/error）保留供弹层读回。
    if data.get("kind") not in (None, "download"):
        return {"code": 0, "data": {"state": "idle"}}
    return {"code": 0, "data": data}
