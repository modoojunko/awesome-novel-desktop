"""全局异常处理器。"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.interfaces.guards import IdentifierRejected

logger = logging.getLogger("api.errors")


def register_handlers(app):
    @app.exception_handler(IdentifierRejected)
    async def _identifier_rejected_handler(request: Request, exc: IdentifierRejected):
        """标识参数危险形态：400 + {code,msg} 信封（门户拦截器读 msg 展示，勿用 detail 形状）。"""
        logger.info("event=identifier_rejected path=%s param=%s", request.url.path, exc.name)
        return JSONResponse(status_code=400, content={"code": 1, "msg": exc.msg})

    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "event=unhandled_error path=%s method=%s err=%s",
            request.url.path, request.method, exc,
        )
        return JSONResponse(
            status_code=500,
            content={"code": -1, "msg": "内部错误，请查看服务器日志"},
        )
