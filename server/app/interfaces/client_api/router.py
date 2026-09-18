"""C端 API 路由注册。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["client"])

import app.interfaces.client_api.account
import app.interfaces.client_api.authorize  # 副作用注册路由
import app.interfaces.client_api.devices
import app.interfaces.client_api.pairing
import app.interfaces.client_api.verify  # noqa: F401
