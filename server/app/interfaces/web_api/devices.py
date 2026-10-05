"""门户设备 API：devices/my, devices/remove（复数对齐 client 面；旧单数路径为过渡别名）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.application.devices.list_devices import list_devices
from app.application.devices.remove_device import remove_device
from app.infrastructure.repositories.factory import code_repo, device_repo, grant_repo
from app.interfaces.deps import Db, get_current_user_or_none, get_db
from app.interfaces.dto import DeviceRemoveRequest, fail

# 持有自己的 APIRouter，由 web_api/router.py 显式 include（理由同 account.py）。
r = APIRouter(tags=["web"])


@r.get("/api/devices/my")
async def api_devices_my(db: Db = Depends(get_db), username: str = Depends(get_current_user_or_none)):
    if not username:
        return fail(code=1, msg="未登录")
    return list_devices(device_repo(db), code_repo(db), username, db=db)


@r.post("/api/devices/remove")
async def api_devices_remove(req: DeviceRemoveRequest, db: Db = Depends(get_db), username: str = Depends(get_current_user_or_none)):
    if not username:
        return fail(code=1, msg="未登录")
    result = remove_device(device_repo(db), grant_repo(db), username, req.id)
    db.commit()
    return result
