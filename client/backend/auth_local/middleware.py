# backend/auth_local/middleware.py
"""C/S 模式下从本地 config.json 读取登录状态"""

import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)

CONFIG_FILE = os.environ.get("DATA_ROOT", "./data") + "/config.json"


def get_local_config() -> dict:
    try:
        import json

        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    except OSError:
        pass
    return {}


def get_user_or_local(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """免登数据出口的身份依赖（loginless-data-exit）。

    有合法会话 → {"id": username}（与 get_current_user 同口径）；
    无会话/不合法 → {"id": None}——免登端点以 None 走整库无主化口径，
    不 401（数据出口不设墙：登录保护的是生成服务，不是用户硬盘上的文件）。
    """
    if credentials is None:
        return {"id": None}
    cfg = get_local_config()
    stored_token = cfg.get("token", "")
    if not stored_token or credentials.credentials != stored_token:
        return {"id": None}
    username = cfg.get("username", "")
    return {"id": username if username else None}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """验证本地 OAuth 会话，返回用户标识。

    C端 不自行验签 JWT —— token 由 S端 OAuth 授权流程签发并存入 config.json，
    这里只核对请求头携带的 token 与本地 OAuth 会话 token 是否一致，身份取
    S端 授权时下发的 username。校验失败视为未登录。
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供认证信息")

    cfg = get_local_config()
    stored_token = cfg.get("token", "")
    if not stored_token or credentials.credentials != stored_token:
        raise HTTPException(status_code=401, detail="登录状态无效，请重新登录")

    # 会话新鲜度（S端 OAuth 下发时写入）：超期则强制重新登录。
    # 注意 expires_at 是套餐/试用到期日（产品口径：过期降免费待遇，限 1 项目，
    # 由 S端 verify + 前端横幅呈现），不是会话有效性，不得据此 401——
    # 否则过期用户会陷入「check-auth 成功 ↔ 业务 401 踢回登录页」死循环。
    from datetime import UTC, datetime, timedelta

    last_login = cfg.get("last_login_at", "")
    if last_login:
        try:
            login_time = datetime.fromisoformat(last_login)
            if login_time.tzinfo is None:
                login_time = login_time.replace(tzinfo=UTC)
            if datetime.now(UTC) - login_time > timedelta(days=30):
                raise HTTPException(status_code=401, detail="登录已超过 30 天，请重新登录")
        except ValueError:
            pass

    username = cfg.get("username", "")
    if not username:
        raise HTTPException(status_code=401, detail="未获取到登录用户")

    # 确保本地存在该用户（OAuth 授权时已创建；此处兜底）
    try:
        from sqlalchemy import select as _select

        from db import async_session as _session
        from models.user import User as _User

        async with _session() as s:
            r = await s.execute(_select(_User).where(_User.id == username))
            if not r.scalar_one_or_none():
                s.add(
                    _User(
                        id=username,
                        email=f"{username}@s.local",
                        password_hash="*",
                        display_name=username,
                    )
                )
                await s.commit()
    except Exception:  # noqa: S110
        pass

    return {"id": username}
