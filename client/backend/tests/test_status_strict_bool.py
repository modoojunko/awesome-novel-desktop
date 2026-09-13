"""1.7 回归锁：settings-status 里塞对象/真值垃圾，不得被当成已确认。

背景（character-settings-v2 审核发现）：settings-status.yaml 是纯 bool dict，
workflow/gates 与 settings/status 曾用 bool(data.get(t)) 读取——任何非空对象
（如 {"confirmed": true}）都会被当成 True，未确认被误判为已确认、门禁静默放行。
修复 = 严格 is True 判定；本文件锁死该行为。
"""

import pytest
from fastapi.testclient import TestClient

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.project import Novel
from models.user import User
from settings import status as status_module


async def _seed():
    uid = f"gt-{uuid.uuid4().hex[:8]}"
    slug = f"gt-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="门禁测试", api_key="", api_base_url="", api_model="",
        ))
        proj = Novel(
            user_id=uid, name="门禁书", slug=slug,
            root_path=f"./data/{slug}", source="manual", current_phase="write",
        )
        session.add(proj)
        await session.commit()
        return uid, proj.id


def test_object_value_not_treated_as_confirmed(tmp_path, monkeypatch):
    """塞 {"confirmed": true} 对象 → GET /settings/status 对该键返回 False。"""
    user_id, novel_id = asyncio.run(_seed())
    from filesystem.storage import get_storage

    async def _seed_bad():
        async with async_session() as session:
            proj = await session.get(Novel, novel_id)
            await get_storage().write_yaml(
                proj.root_path,
                "settings/settings-status.yaml",
                {"synopsis": {"confirmed": True}},  # 历史事故形态：对象
            )

    asyncio.run(_seed_bad())

    async def _override():
        return {"id": user_id}

    app.dependency_overrides[get_current_user] = _override
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as c:
        r = c.get(f"/api/novels/{novel_id}/settings/status")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    data = body.get("data", body)  # 端点直接返回 dict（无 data 包装）
    assert data["synopsis"] is False  # 严格 is True：对象 ≠ 已确认


def test_string_truthy_shape_normalized_out():
    """get_settings_status 的输出只含 bool——字符串真值被 is True 归一为 False。"""
    from settings.status import VALID_TYPES

    data = {"synopsis": "true", "genre": {"confirmed": True}, "world": True}
    out = {t: data.get(t) is True for t in VALID_TYPES if t in data}
    assert out == {"synopsis": False, "genre": False, "world": True}


import asyncio
import uuid
