from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.middleware import get_current_user
from db import get_db
from filesystem.storage import get_storage
from novels.service import get_novel
from workflow.readiness import READINESS_CHECKERS, READINESS_KEYS

router = APIRouter(prefix="/api/novels/{project_id}/settings", tags=["settings"])

# 可确认完成的设定类型 = readiness 判定集 ∪ ai-model（ai-model 可确认但不判定内容）。
# 从 READINESS_KEYS 推导，避免与 readiness.py 重复维护。
VALID_TYPES = READINESS_KEYS | {"ai-model"}
STATUS_FILE = "settings/settings-status.yaml"


@router.get("/status")
async def get_settings_status(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    data = await get_storage().read_yaml(project.root_path, STATUS_FILE)
    if not data:
        return {t: False for t in VALID_TYPES}
    return {t: bool(data.get(t, False)) for t in VALID_TYPES}


@router.put("/status/{type}")
async def confirm_settings_type(
    project_id: str,
    type: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if type not in VALID_TYPES:
        raise HTTPException(400, f"Invalid settings type: {type}")

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    # 产品决策：点「完成设定」时判定该项内容是否为空——为空则拒绝确认并提示。
    # ai-model 不参与判定（模型配置不是创作设定），跳过内容校验。
    if type in READINESS_KEYS:
        checker = next(c for k, _l, _j, c in READINESS_CHECKERS if k == type)
        ok = await checker(project.root_path, project.id)  # type: ignore[operator]
        if not ok:
            raise HTTPException(
                400, "该项设定还未填写内容，请先填写后再标记完成"
            )

    data = await get_storage().read_yaml(project.root_path, STATUS_FILE) or {}
    data[type] = True
    await get_storage().write_yaml(project.root_path, STATUS_FILE, data)
    return {"ok": True, "type": type, "confirmed": True}
